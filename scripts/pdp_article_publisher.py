"""
PDP产品长文发布模块

流程:
  1. 搜索小红书人物热点
  2. 搜索该人物新闻
  3. LLM PDP性格分析 + 长文生成
  4. ADB发布（商品组件+公开可见）

基于 xhs-adb-publisher 的 xhs_article_publisher.py 改造
"""
import json, logging, os, sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm_json
from phone_controller import xie_chang_wen
from hotspot_news_search import run as search_hotspot_news, search_person_news

logger = logging.getLogger("pdp-publisher")

TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
PUBLISHED_FILE = DATA_DIR / "published-articles.json"
PDP_PROMPT = TEMPLATES_DIR / "pdp-article-prompt.md"

MIN_BODY_LEN = 1000
MAX_BODY_LEN = 1500
MAX_TITLE_LEN = 20
MAX_XHS_BODY = 600
MAX_RETRIES = 3

def load_prompt() -> str:
    fp = PDP_PROMPT
    return fp.read_text(encoding="utf-8") if fp.exists() else ""

def load_config() -> dict:
    fp = CONFIG_DIR / "publish.json"
    return json.loads(fp.read_text()) if fp.exists() else {}

def load_published() -> list:
    if PUBLISHED_FILE.exists():
        return json.loads(PUBLISHED_FILE.read_text())
    return []

def save_published(entry: dict):
    records = load_published()
    records.append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))

def _enforce_limits(title: str) -> str:
    """强制标题 ≤ 20个Python字符（含Emoji）
    Emoji占2个字符，中文占1个
    超长时从末尾截断，保留开头完整
    """
    if len(title) <= MAX_TITLE_LEN:
        return title.strip()
    
    # 超长则从末尾截断，保留开头
    title = title[:MAX_TITLE_LEN].strip()
    
    # 如果截断后最后一个字符不完整（如emoji被切半），去掉
    while len(title) > 0 and ord(title[-1]) > 0xFFFF:
        title = title[:-1]
    
    return title.strip()


def _generate_xhs_body(editor_body: str, person_name: str, pdp_name: str) -> str:
    """
    LLM 生成精炼的 xhs 发布确认页正文（≤1000字）
    不是截断，而是重新组织精简版本 + 产品CTA
    """
    product_cta = f"\n\n🔥【你也想解密自己的隐藏天赋？】\n想知道自己是什么性格类型？\n👉 {pdp_name}"
    cta_len = len(product_cta)
    target_len = MAX_XHS_BODY - cta_len

    prompt = f"""你是一个小红书内容精简专家。

请根据以下长文，写一段精简版的小红书正文（不超过{target_len}字）。

要求：
- 保留核心观点和最具吸引力的内容
- 语言口语化、有画面感
- 不要出现产品推广或链接（产品信息后续会单独添加）
- 独立成文，不要用"上文提到"或"如下"等引导语
- 控制在{target_len}字以内

原文摘要：
分析人物：{person_name}
{editor_body[:800]}...

输出纯JSON格式：
{{"body": "精简版正文"}}
"""
    try:
        from xhs_llm import call_llm_json
        result = call_llm_json(
            system_prompt=f"你是一个小红书内容精简专家。输出精简正文，不超过{target_len}字。",
            user_prompt=prompt,
            temperature=0.4,
            max_tokens=4000,
        )
        xhs_prefix = result.get("body", "").strip()
        if len(xhs_prefix) > target_len:
            xhs_prefix = xhs_prefix[:target_len]
        return xhs_prefix + product_cta
    except Exception as e:
        logger.warning(f"xhs正文生成失败，使用编辑器正文前段: {e}")
        body_prefix = editor_body[:MAX_XHS_BODY - 100].strip()
        return body_prefix + product_cta

def _retry_llm(prompt_template: str, person_name: str, person_news: str,
               pdp_url: str, pdp_name: str) -> dict:
    """带重试的 LLM 调用，确保标题含全名+正文长度符合要求"""
    # 提取人物全名的核心字段
    name_core = person_name
    for ch in ['（', '）', '(', ')']:
        name_core = name_core.replace(ch, ' ')
    name_core = name_core.split()[0] if name_core.strip() else person_name[:2]

    prompt = prompt_template.replace("{{person_name}}", person_name)
    prompt = prompt.replace("{{person_news}}", person_news)
    prompt = prompt.replace("{{pdp_url}}", pdp_url)
    prompt = prompt.replace("{{pdp_name}}", pdp_name)

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"LLM 生成第 {attempt}/{MAX_RETRIES} 次...")

        length_hint = ""
        if attempt == 2:
            length_hint = "\n⚠️ 正文必须在1000-1500字！精简！且标题必须包含人物全名！上次超长了或格式不对，请修正！"
        elif attempt == 3:
            length_hint = "\n⚠️ 标题必须含人物全名！正文必须在1000-1500字！精简！舍弃多余分析！严格JSON格式！"

        try:
            result = call_llm_json(
                system_prompt=f"你是一个PDP性格分析师兼小红书内容创作者。{length_hint}严格按照JSON格式输出，不要换行。",
                user_prompt=prompt + length_hint,
                max_tokens=384000,
            )
        except ValueError as e:
            logger.warning(f"LLM JSON 解析失败: {e}")
            if attempt < MAX_RETRIES:
                continue
            raise

        title = result.get("title", "")
        body = result.get("body", "")
        total_len = len(body.strip())
        logger.info(f"  LLM返回: 标题{len(title)}字 正文{total_len}字")

        # 校验标题长度（含emoji不超过20字）
        over_len = False
        if len(title) > MAX_TITLE_LEN:
            logger.warning(f"  标题{len(title)}字，超过{MAX_TITLE_LEN}字上限，重试...")
            over_len = True
        
        # 校验标题是否包含人物全名
        has_name = name_core[:2] in title
        if not has_name:
            logger.warning(f"  标题未包含人物全名 '{name_core}'，重试...")
            if attempt < MAX_RETRIES:
                continue
        
        if over_len and attempt < MAX_RETRIES:
            continue

        # 校验正文长度
        if MIN_BODY_LEN <= total_len <= MAX_BODY_LEN:
            return {"title": title, "body": body, "retries": attempt}

        if attempt < MAX_RETRIES:
            if total_len < MIN_BODY_LEN:
                logger.warning(f"  正文仅{total_len}字符，不足{MIN_BODY_LEN}，重试...")
            else:
                logger.warning(f"  正文{total_len}字符，超过{MAX_BODY_LEN}字上限，重试...")

    logger.warning(f"  已重试{MAX_RETRIES}次，使用当前结果")
    return {"title": title, "body": body, "retries": MAX_RETRIES}

def generate_pdp_article(person_name: str, person_news: str,
                         pdp_url: str, pdp_name: str) -> dict:
    """LLM 生成PDP性格分析长文"""
    prompt_template = load_prompt()
    if not prompt_template:
        raise FileNotFoundError(f"提示词模板未找到: {PDP_PROMPT}")

    gen = _retry_llm(prompt_template, person_name, person_news, pdp_url, pdp_name)
    title = _enforce_limits(gen["title"])
    editor_body = gen["body"].strip()
    xhs_body = _generate_xhs_body(editor_body, person_name, pdp_name)

    return {
        "title": title,
        "editor_body": editor_body,
        "xhs_body": xhs_body,
        "person_name": person_name,
        "generated_at": datetime.now().isoformat(),
        "llm_retries": gen["retries"],
        "total_chars": len(editor_body),
    }

def run_publish(person_name: str = None, dry_run: bool = False) -> dict:
    """
    完整 PDP 长文发布流程
    
    Args:
        person_name: 指定人物（为空则自动搜索热点）
        dry_run: 仅生成不发布
    
    Returns:
        dict: 发布结果
    """
    config = load_config()
    pdp_url = config.get("product", {}).get("pdp_url",
        "https://huixin.interwestinfo.com/custweb/home/pdpEntry/gb?td_channelid=wx")
    pdp_name = config.get("product", {}).get("pdp_name",
        "PDP性格测试揭示天赋秘密")
    max_people = config.get("hotspot", {}).get("max_people_per_run", 3)
    max_news = config.get("hotspot", {}).get("max_news_per_person", 5)

    result = {"status": "started", "steps": []}

    # 步骤1: 获取热点人物+新闻
    logger.info("步骤1/3: 获取热点人物和新闻...")
    if person_name:
        # 指定人物，直接搜新闻
        news = search_person_news(person_name)
        people_data = [{"name": person_name, "news": news}]
    else:
        people_data = search_hotspot_news(max_people=max_people)

    if not people_data:
        result["status"] = "failed"
        result["error"] = "未找到热点人物"
        return result

    result["hot_people"] = [{"name": p["name"], "reason": p.get("reason", "")}
                            for p in people_data]
    result["steps"].append({"step": "hotspot_search", "status": "ok",
                            "people_count": len(people_data)})

    # 按评分排序，取评分最高的第一个人物
    people_data.sort(key=lambda x: x.get("score", 0), reverse=True)
    best_person = people_data[0]
    score = best_person.get("score", 0)
    category = best_person.get("category", "未知")
    tags = best_person.get("freshness_tags", [])
    logger.info(f"🎯 选中人物: {best_person['name']} ({score}分, {category}, 标签:{tags})")

    # 步骤2: 生成文章
    logger.info(f"步骤2/3: 生成 {best_person['name']} 的PDP分析文章...")
    article = generate_pdp_article(
        person_name=best_person["name"],
        person_news=best_person["news"],
        pdp_url=pdp_url,
        pdp_name=pdp_name,
    )
    article["person_reason"] = best_person.get("reason", "")
    logger.info(f"  标题: {article['title']} | 正文: {article['total_chars']}字")

    result["articles"] = [article]
    result["steps"].append({"step": "llm_generate", "status": "ok",
                            "article_count": 1})

    if dry_run:
        result["status"] = "dry_run"
        return result

    # 步骤3: ADB发布
    logger.info("步骤3/3: ADB发布到小红书...")
    published = []
    for article in result["articles"]:
        try:
            logger.info(f"发布笔记: {article['title']} (人物: {article['person_name']})")
            xie_chang_wen(
                editor_body=article["editor_body"],
                publish_body=article["xhs_body"],
                title=article["title"],
                product_name=pdp_name,
            )
            record = {
                "title": article["title"],
                "person_name": article["person_name"],
                "product_name": pdp_name,
                "published_at": datetime.now().isoformat(),
                "type": "PDP长文",
                "total_chars": article["total_chars"],
            }
            save_published(record)
            published.append(record)
            logger.info(f"✅ 发布成功: {article['title']}")
        except Exception as e:
            logger.error(f"❌ 发布失败: {article['title']} - {e}")
            result["steps"].append({
                "step": f"publish_{article['person_name']}",
                "status": "failed",
                "error": str(e),
            })

    result["published"] = published
    result["status"] = "published" if published else "failed"
    return result
