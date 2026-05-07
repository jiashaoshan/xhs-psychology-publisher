"""
热点人物挖掘 + 新闻搜索模块

数据来源（按优先级）:
  1. Agent 传入的热搜数据（顶层 Agent 用 web_search / web_fetch 搜索后传入）
  2. 百度热搜榜爬取
  3. 小红书 MCP 搜索（如果 MCP 运行中）
  4. 最终 fallback: LLM 基于训练数据做分析

流程:
  Agent搜索/百度热搜 → LLM提取人物类热点 → 提取人物名 → 搜索人物新闻
"""
import json, logging, os, sys, re, requests
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

SCRIPT_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm_json, call_llm

logger = logging.getLogger("hotspot-news")

# ============================================================
# 数据源层：从真实渠道获取热搜/热点数据
# ============================================================

def fetch_baidu_hotsearch(max_items: int = 20) -> List[Dict]:
    """
    抓取百度热搜实时榜单
    Returns: [{"word": "热搜词", "hotScore": 热度, "category": "类别"}]
    """
    url = "https://top.baidu.com/board?tab=realtime"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = "utf-8"
        # 百度热搜数据在 HTML 注释中 <!--s-data:{"data":{}}-->
        import re
        m = re.search(r'<!--s-data:(.*?)-->', r.text, re.DOTALL)
        if not m:
            logger.warning("百度热搜数据未找到，可能是页面结构变化")
            return []

        raw = json.loads(m.group(1))
        cards = raw.get("data", {}).get("cards", [])
        results = []
        for card in cards:
            items = card.get("content", [])
            for item in items[:max_items]:
                results.append({
                    "word": item.get("word", ""),
                    "hotScore": item.get("hotScore", 0),
                    "category": item.get("category", ""),
                })
        logger.info(f"百度热搜抓取成功: {len(results)} 条")
        return results[:max_items]
    except Exception as e:
        logger.warning(f"百度热搜抓取失败: {e}")
        return []


def fetch_xhs_personality_notes(max_notes: int = 10) -> List[Dict]:
    """通过 xiaohongshu-mcp 搜索性格/人物相关笔记"""
    mcp_url = os.environ.get("XHS_MCP_URL", "http://localhost:18060")
    keywords = ["性格分析", "人物分析", "名人故事", "热点人物", "性格类型"]
    results = []
    for kw in keywords:
        try:
            r = requests.post(
                f"{mcp_url}/api/v1/feeds/search",
                json={"keyword": kw, "page": 1, "page_size": 5},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                notes = data.get("data", {}).get("items", []) or data.get("items", [])
                for note in notes:
                    results.append({
                        "keyword": kw,
                        "title": note.get("title", ""),
                        "desc": note.get("desc", "") or note.get("description", ""),
                        "author": note.get("author", {}).get("nickname", ""),
                    })
                logger.info(f"MCP搜索 [{kw}] 成功: {len(notes)} 条")
        except Exception as e:
            logger.debug(f"MCP搜索 [{kw}] 不可用: {e}")
        if len(results) >= max_notes:
            break
    return results[:max_notes]


# ============================================================
# 分析层：从原始数据中提取人物类热点
# ============================================================

def extract_people_from_trending(trending_data: List[Dict]) -> List[Dict]:
    """
    用 LLM 分析热搜数据，提取人物类热点
    Args:
        trending_data: [{"word": "...", "hotScore": ...}]
    Returns:
        [{"name": "董宇辉", "reason": "...", "category": "..."}]
    """
    if not trending_data:
        return []

    words_text = "\n".join([
        f"{i+1}. {item['word']}" + (f" (热度:{item.get('hotScore','')})" if item.get('hotScore') else "")
        for i, item in enumerate(trending_data)
    ])

    prompt = f"""以下是当前百度热搜榜单的热搜词条：

{words_text}

请分析这些热搜词条，找出其中**人物类**的热点——即与某个具体公众人物相关的词条。
包括：明星、企业家、网红、知识博主、运动员、政治人物等。

对于每个人物，请提供：
- name: 人物姓名
- reason: 为什么上热搜（一句话，基于热搜词条分析）
- category: 类别（明星/企业家/网红/知识博主/运动员/其他）

注意：
- 只提取明确涉及具体人物的词条
- 如果某个词条提及的人名是群体名称（如"中国队"），则忽略
- 如果某个词条隐晦涉及人物（如"某某公司股价暴跌"可能涉及某CEO），尝试关联具体人物

返回JSON格式：
{{
  "people": [
    {{"name": "董宇辉", "reason": "与辉同行直播带货创新高", "category": "知识博主"}}
  ]
}}
"""
    try:
        result = call_llm_json(
            system_prompt="你是一个中文互联网热点分析师，擅长从热搜数据中提取人物类热点。",
            user_prompt=prompt,
            temperature=0.3,
        )
        people = result.get("people", [])
        # 过滤掉非具体人物
        people = [p for p in people if len(p.get("name", "")) >= 2]
        logger.info(f"从热搜中提取到 {len(people)} 个人物: {[p['name'] for p in people]}")
        return people
    except Exception as e:
        logger.error(f"人物提取失败: {e}")
        return []


# ============================================================
# 新闻搜索层：搜索人物的新闻资料
# ============================================================

def search_person_news(person_name: str) -> str:
    """
    搜索指定人物的公开新闻资料。
    使用 LLM 基于训练数据 + 已知公开信息生成新闻摘要。
    （实际可扩展为对接新闻API或 web_search 传入结果）
    """
    prompt = f"""你是一个新闻研究员。请提供以下人物的公开信息和近期动态。

人物：{person_name}

要求：
1. 只基于该人物的**公开已知信息**，不要编造
2. 如果信息不确定，标注"据公开报道"或"据网络信息"
3. 聚焦该人物的：职业背景、近期事件、性格特征（来自公开言行）

请按以下格式返回JSON：
{{
  "person": "{person_name}",
  "basic_info": "职业、背景等基本信息",
  "recent_events": "近期公开事件（逐条简要列出）",
  "personality_traits": "媒体采访或公开言行中表现出的性格特征",
  "key_quotes": "标志性言论（如有）",
  "summary": "综合摘要（300字以内）"
}}
"""
    try:
        result = call_llm_json(
            system_prompt=f"你熟悉{person_name}的公开资料，请基于已知事实回答。",
            user_prompt=prompt,
            temperature=0.3,
        )
        summary = f"""【{person_name} 基本信息】
{result.get('basic_info', '暂无')}

【近期事件】
{result.get('recent_events', '暂无')}

【性格特征（公开资料）】
{result.get('personality_traits', '暂无')}

【标志性言论】
{result.get('key_quotes', '暂无')}

【综合摘要】
{result.get('summary', '暂无')}
"""
        logger.info(f"获取 {person_name} 新闻资料成功")
        return summary.strip()
    except Exception as e:
        logger.error(f"新闻搜索失败 ({person_name}): {e}")
        return f"{person_name} 的公开资料暂时无法获取。"


# ============================================================
# 编排层
# ============================================================

def run(max_people: int = 3, external_data: Optional[List[Dict]] = None) -> List[Dict]:
    """
    完整流程：数据获取 → 人物提取 → 新闻搜索

    Args:
        max_people: 最多提取几个人物
        external_data: 由顶层Agent传入的热搜数据
            [{"word": "热搜词", "hotScore": 热度}]
            如果传入，跳过百度热搜抓取

    Returns:
        [{"name": str, "reason": str, "category": str, "news": str}]
    """
    # ---- 步骤1: 获取热搜数据 ----
    trending_data = external_data
    if not trending_data:
        logger.info("步骤1/3: 抓取百度热搜...")
        trending_data = fetch_baidu_hotsearch(30)
        logger.info(f"  获取到 {len(trending_data)} 条热搜")

    # ---- 步骤2: 提取人物类热点 ----
    logger.info("步骤2/3: 提取人物类热点...")
    people = extract_people_from_trending(trending_data)
    if not people:
        logger.warning("未从热搜中提取到人物，尝试MCP搜索...")
        xhs_notes = fetch_xhs_personality_notes(10)
        if xhs_notes:
            # 从XHS笔记中提取人物
            people = extract_people_from_xhs_notes(xhs_notes)
        if not people:
            logger.warning("所有数据源均未提取到人物")
            return []

    people = people[:max_people]

    # ---- 步骤3: 搜索人物新闻 ----
    results = []
    for person in people:
        logger.info(f"步骤3/3: 搜索 {person['name']} 的新闻...")
        news = search_person_news(person["name"])
        results.append({
            "name": person["name"],
            "reason": person.get("reason", ""),
            "category": person.get("category", ""),
            "news": news,
        })

    logger.info(f"热点挖掘完成: {[r['name'] for r in results]}")
    return results


def extract_people_from_xhs_notes(notes: List[Dict]) -> List[Dict]:
    """从XHS笔记中提取人物（备用方案）"""
    if not notes:
        return []
    text = "\n".join([f"- {n.get('title','')} | {n.get('desc','')}" for n in notes])
    prompt = f"""以下是从小红书搜索到的人物/性格相关笔记标题：

{text}

请分析这些笔记可能涉及哪些热点人物（明星、企业家、网红等），
提取人物名称和对应的话题。

返回JSON：
{{"people": [{{"name": "...", "reason": "...", "category": "..."}}]}}
"""
    try:
        result = call_llm_json(
            system_prompt="你是一个小红书内容分析师。",
            user_prompt=prompt,
            temperature=0.3,
        )
        return result.get("people", [])
    except:
        return []


# ============================================================
# Agent 辅助函数：供顶层 Agent 调用（不在脚本内执行）
# ============================================================

def format_agent_search_query() -> str:
    """
    返回 Agent 应使用的搜索查询。
    Agent 用 web_search 搜索后将结果传给 run(external_data=...)
    """
    return "2026年5月 热搜人物 热点人物 今日热搜人物"


if __name__ == "__main__":
    # 测试运行
    logging.basicConfig(level=logging.INFO)
    results = run(max_people=3)
    print(json.dumps(results, ensure_ascii=False, indent=2))
