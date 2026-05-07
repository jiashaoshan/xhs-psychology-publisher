"""
LLM API 封装 — 从 xhs-adb-publisher 复用
"""
import json, logging, os, requests
from typing import Optional

logger = logging.getLogger(__name__)

LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/chat/completions")
DEFAULT_MAX_TOKENS = 384000
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TIMEOUT = 180

def _find_api_key() -> Optional[str]:
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        return env_key
    try:
        cfg = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(cfg):
            with open(cfg) as f:
                env = json.load(f).get("env", {})
                if isinstance(env, dict):
                    return env.get("DEEPSEEK_API_KEY")
    except:
        pass
    return None

def get_api_key() -> str:
    key = _find_api_key()
    if not key:
        raise EnvironmentError("未找到 DEEPSEEK_API_KEY。请配置环境变量或 ~/.openclaw/openclaw.json 的 env")
    return key

def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL,
             temperature: float = 0.7, max_tokens: int = DEFAULT_MAX_TOKENS,
             timeout: int = DEFAULT_TIMEOUT) -> str:
    api_key = get_api_key()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        resp = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
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
            return json.loads(m.group())
        raise ValueError(f"LLM 返回非 JSON: {content[:100]}")
