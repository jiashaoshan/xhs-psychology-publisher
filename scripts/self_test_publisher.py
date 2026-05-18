"""
自测类小红书内容发布模块 — Strategy A

内容类型（5种轮换）:
  1. 职场性格对比 — "老虎型 vs 孔雀型，职场谁更吃得开？"
  2. 互动测试帖 — "3个问题测出你的隐藏性格"
  3. 情侣/关系帖 — "老虎型女友 vs 考拉型男友"
  4. 故事型 — "面试官一眼看出我是孔雀型"
  5. 评论区引流帖 — "评论区留下答案帮你分析"

流程:
  1. LLM 随机选取一种生成文章（不自选类型，避免重复）
  2. 检查是否与最近发布内容类型相同（连续撞型则重试）
  3. ADB发布（商品组件+公开可见）
  4. 记录已发布
"""
import json, logging, os, random, sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm_json
from phone_controller import xie_chang_wen

logger = logging.getLogger("self-test-publisher")

TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
PUBLISHED_FILE = DATA_DIR / "published-articles.json"
PROMPT_FILE = TEMPLATES_DIR / "self-test-article-prompt.md"

MAX_TITLE_LEN = 20
MAX_RETRIES = 3
TYPE_NAMES = {
    1: "职场性格对比",
    2: "互动测试帖",
    3: "情侣/关系帖",
    4: "故事型",
    5: "评论区引流帖",
}


def load_prompt() -> str:
    fp = PROMPT_FILE
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


def get_last_article_type() -> int:
    """检查最近一篇自测文章的类型，避免连续重复"""
    records = load_published()
    self_test_records = [r for r in records if r.get("type", "").startswith("自测")]
    if not self_test_records:
        return 0
    last = self_test_records[-1]
    return last.get("article_type", 0)


def _enforce_title(title: str) -> str:
    if len(title) <= MAX_TITLE_LEN:
        return title.strip()
    title = title[:MAX_TITLE_LEN].strip()
    while len(title) > 0 and ord(title[-1]) > 0xFFFF:
        title = title[:-1]
    return title.strip()


def _select_weighted_type(last_type: int) -> int:
    """
    加权随机选择文章类型
    权重：类型⑤（评论区引流帖）2x，其余 1x
    如果选到和上次相同，重新选（最多3次）
    """
    weights = {1: 1, 2: 1, 3: 1, 4: 1, 5: 4}  # 类型⑤ 4x权重，约占50%
    available = [t for t in range(1, 6) if t != last_type or last_type == 0]
    if not available:
        available = list(range(1, 6))

    # 加权随机选3次机会
    for _ in range(3):
        pool = [t for t in available for _ in range(weights[t])]
        chosen = random.choice(pool)
        if chosen != last_type or last_type == 0:
            return chosen
    # 最终兜底：忽略撞型
    pool = [t for t in available for _ in range(weights[t])]
    return random.choice(pool)


def _generate_article(config: dict) -> dict:
    """LLM 生成自测类文章，5种类型加权轮换（类型⑤权重2x），避免连续重复"""
    prompt_template = load_prompt()
    if not prompt_template:
        raise FileNotFoundError(f"提示词模板未找到: {PROMPT_FILE}")

    last_type = get_last_article_type()

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"LLM 生成第 {attempt}/{MAX_RETRIES} 次...")

        # 预选类型（加权），通知 LLM 使用指定类型
        force_type = _select_weighted_type(last_type)
        if attempt >= 2 and last_type > 0 and force_type == last_type:
            available = [t for t in range(1, 6) if t != last_type]
            if available:
                force_type = random.choice(available)

        length_hint = ""
        if attempt == 2:
            length_hint = "\n⚠️ 上次返回不符合要求！注意字数限制和JSON格式！"
        elif attempt == 3:
            length_hint = "\n⚠️ 严格遵循JSON格式输出！不要markdown包围！"

        force_hint = f"\n⚠️ 本次必须使用文章类型{force_type}（{TYPE_NAMES[force_type]}），不能选择其他类型！"

        prompt_text = prompt_template + length_hint + force_hint

        try:
            result = call_llm_json(
                system_prompt=f"你是一个小红书爆款内容创作者，擅长制作让读者代入自己的性格类内容。{length_hint}严格JSON格式输出。",
                user_prompt=prompt_text,
                max_tokens=384000,
            )
        except ValueError as e:
            logger.warning(f"LLM JSON 解析失败: {e}")
            if attempt < MAX_RETRIES:
                continue
            raise

        title = result.get("title", "")
        body = result.get("body", "")
        xhs_body = result.get("xhs_body", "")
        article_type = result.get("article_type", 0)

        # 校验
        issues = []
        if len(title) > MAX_TITLE_LEN:
            issues.append(f"标题超长({len(title)}字)")
        if not article_type or article_type not in range(1, 6):
            issues.append(f"文章类型无效: {article_type}")

        # 强制类型不匹配
        if article_type != force_type:
            issues.append(f"类型应为{force_type}，实际为{article_type}")

        if issues:
            logger.warning(f"  校验失败: {'; '.join(issues)}")
            if attempt < MAX_RETRIES:
                continue

        if not xhs_body:
            xhs_body = _generate_xhs_body(body, article_type, config)

        title = _enforce_title(title)
        logger.info(f"  ✅ 生成成功: 类型{article_type}({TYPE_NAMES.get(article_type,'?')}) | 标题{len(title)}字 | 正文{len(body)}字")

        return {
            "title": title,
            "body": body,
            "xhs_body": xhs_body,
            "article_type": article_type,
            "generated_at": datetime.now().isoformat(),
            "llm_retries": attempt,
        }

    raise RuntimeError(f"LLM 生成失败（{MAX_RETRIES}次重试均无效）")


def _generate_xhs_body(editor_body: str, article_type: int, config: dict) -> str:
    """生成发布确认页正文"""
    config = config or load_config()
    hashtags = config.get("publish", {}).get("hashtags", [])
    max_chars = config.get("publish", {}).get("xhs_body_max_chars", 1000)

    hashtag_line = "\n" + " ".join([f"#{t}" for t in hashtags + ["识人术", "心理学"]])

    # 不同类型不同CTA
    ctas = {
        1: "\n\n💡 你是什么类型？评论区说说，或者私信我发你免费版～",
        2: "\n\n💡 说说你的答案，或者私信我做完整版测试👇",
        3: "\n\n💡 你和你对象是什么搭配？评论区聊聊～",
        4: "\n\n💡 看完我的故事，想知道自己是什么类型？私信我～",
        5: "\n\n💡 评论区留下你的答案，帮你分析～我测过这个，挺准的👇",
    }
    cta = ctas.get(article_type, "\n\n💡 想知道自己是什么性格类型？评论区或私信我～")

    xhs_text = cta + hashtag_line
    xhs_text_len = len(xhs_text)

    # 取正文前段（去掉最后200字避免和CTA重复）
    body_prefix = editor_body[:max_chars - xhs_text_len - 50].strip()
    return body_prefix + xhs_text


def run_self_test(dry_run: bool = False) -> dict:
    """
    自测类文章发布全流程

    Args:
        dry_run: 仅生成不发布

    Returns:
        dict: 发布结果
    """
    config = load_config()
    pdp_name = config.get("product", {}).get("pdp_name", "PDP性格测试揭示天赋秘密")

    result = {"status": "started", "steps": []}

    # 步骤1: LLM 生成文章
    logger.info("步骤1/2: LLM 生成自测类文章...")
    try:
        article = _generate_article(config)
    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"文章生成失败: {e}"
        logger.error(result["error"])
        return result

    result["articles"] = [article]
    result["article_type"] = article["article_type"]
    result["steps"].append({"step": "llm_generate", "status": "ok",
                            "type": TYPE_NAMES.get(article["article_type"], "?")})

    if dry_run:
        result["status"] = "dry_run"
        return result

    # 步骤2: ADB发布
    logger.info(f"步骤2/2: ADB发布自测类文章 [{TYPE_NAMES.get(article['article_type'], '?')}]...")
    published = []
    try:
        logger.info(f"发布笔记: {article['title']}")
        use_product = pdp_name  # 所有类型均加商品组件
        xie_chang_wen(
            editor_body=article["body"],
            publish_body=article["xhs_body"],
            title=article["title"],
            product_name=use_product,
        )
        record = {
            "title": article["title"],
            "article_type": article["article_type"],
            "product_name": use_product or "（无商品组件/私信引流）",
            "published_at": datetime.now().isoformat(),
            "type": f"自测-{TYPE_NAMES.get(article['article_type'], '?')}",
            "total_chars": len(article["body"]),
        }
        save_published(record)
        published.append(record)
        logger.info(f"✅ 发布成功: {article['title']}")
    except Exception as e:
        logger.error(f"❌ 发布失败: {article['title']} - {e}")
        result["steps"].append({"step": "publish", "status": "failed", "error": str(e)})

    result["published"] = published
    result["status"] = "published" if published else "failed"
    return result
