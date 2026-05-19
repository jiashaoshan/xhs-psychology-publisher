"""
LLM API 封装 — 复用 xhs-adb-publisher 的配置加载逻辑
主用千帆（qianfan-code-latest），429限流自动切 deepseek
"""
import json, logging, os, requests
from typing import Optional

logger = logging.getLogger(__name__)

# ── LLM 配置 ────
LLM_API_URL = None
LLM_API_KEY = None
DEFAULT_MODEL = "qianfan-code-latest"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT = 300
LLM_RETRY_DELAY = 15

# 备选 Provider（主用不通时自动切换）
FALLBACK_API_URL = None
FALLBACK_API_KEY = None
FALLBACK_MODEL = "deepseek-v4-flash"
FALLBACK_PROVIDER_IDS = ["deepseek"]


def _load_llm_config():
    """从 openclaw.json 读取 LLM 配置（主用千帆，自动备选 deepseek）"""
    global LLM_API_URL, LLM_API_KEY, DEFAULT_MODEL
    global FALLBACK_API_URL, FALLBACK_API_KEY, FALLBACK_MODEL
    if LLM_API_URL and LLM_API_KEY:
        return
    try:
        cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                data = json.load(f)
            providers = data.get("models", {}).get("providers", {})

            for provider_id, p in providers.items():
                pid = provider_id.lower()

                # 主用：千帆
                if "qianfan" in pid or "baidu" in pid:
                    LLM_API_URL = p.get("baseUrl", "") + "/chat/completions"
                    LLM_API_KEY = p.get("apiKey", "")
                    models = p.get("models", [])
                    if models:
                        DEFAULT_MODEL = models[0].get("id", "qianfan-code-latest")
                    logger.info(f"主用: {LLM_API_URL} | 模型: {DEFAULT_MODEL}")

                # 备选：deepseek
                elif any(fid in pid for fid in FALLBACK_PROVIDER_IDS):
                    if not FALLBACK_API_URL:
                        FALLBACK_API_URL = p.get("baseUrl", "") + "/chat/completions"
                        FALLBACK_API_KEY = p.get("apiKey", "")
                        fb_models = p.get("models", [])
                        if fb_models:
                            FALLBACK_MODEL = fb_models[0].get("id", "deepseek-v4-flash")
                        logger.info(f"备选: {FALLBACK_API_URL} | 模型: {FALLBACK_MODEL}")
    except Exception as e:
        logger.debug(f"读取 openclaw.json LLM 配置失败: {e}")

    # fallback: 环境变量（兜底用 deepseek）
    if not LLM_API_URL:
        LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/chat/completions")
        LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


def get_api_key() -> str:
    _load_llm_config()
    if not LLM_API_KEY:
        raise EnvironmentError(
            "未找到 LLM API Key。\n"
            "请在 ~/.openclaw/openclaw.json 的 models.providers 中配置千帆，"
            "或设置环境变量 DEEPSEEK_API_KEY"
        )
    return LLM_API_KEY


def call_llm(system_prompt: str, user_prompt: str, model: str = None,
             temperature: float = 0.7, max_tokens: int = None,
             timeout: int = DEFAULT_TIMEOUT) -> str:
    _load_llm_config()
    api_key = LLM_API_KEY
    api_url = LLM_API_URL
    if model is None:
        model = DEFAULT_MODEL
    if max_tokens is None:
        max_tokens = DEFAULT_MAX_TOKENS

    # max_tokens 限制，超过 8192 容易失败
    if max_tokens > 8192:
        max_tokens = 8192

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], "temperature": temperature, "max_tokens": max_tokens}

    logger.info(f"LLM 调用: {api_url} | 模型: {model} | max_tokens: {max_tokens}")
    import time as _time
    for attempt in range(3):
        try:
            resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < 2:
                delay = LLM_RETRY_DELAY * (2 ** attempt)
                logger.warning(f"429 限流，{delay}秒后重试 ({attempt+1}/3)...")
                _time.sleep(delay)
                continue
            # 429 重试耗尽，切备选
            if e.response.status_code == 429 and FALLBACK_API_URL:
                logger.warning(f"千帆限流，切换到备选: {FALLBACK_MODEL}")
                fb_headers = {"Authorization": f"Bearer {FALLBACK_API_KEY}", "Content-Type": "application/json"}
                fb_payload = dict(payload, model=FALLBACK_MODEL)
                try:
                    fb_resp = requests.post(FALLBACK_API_URL, headers=fb_headers, json=fb_payload, timeout=timeout)
                    fb_resp.raise_for_status()
                    return fb_resp.json()["choices"][0]["message"]["content"].strip()
                except Exception as fb_e:
                    logger.error(f"备选也失败: {fb_e}")
                    raise
            logger.error(f"LLM 调用失败: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise


def call_llm_json(*args, **kwargs) -> dict:
    content = call_llm(*args, **kwargs)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            raw = m.group()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                if '"body"' in raw and not raw.strip().endswith('}'):
                    body_match = re.search(r'"body"\s*:\s*"([^"]*)$', raw, re.DOTALL)
                    if body_match:
                        fixed = raw[:raw.rfind('"body"')] + '"body": "（内容截断）"}'
                        try: return json.loads(fixed)
                        except: pass
                    try: return json.loads(raw + '"}')
                    except:
                        try: return json.loads(raw + '"\n}')
                        except: pass
        raise ValueError(f"LLM 返回非 JSON: {content[:200]}")
