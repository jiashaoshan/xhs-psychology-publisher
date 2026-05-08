"""
热点人物挖掘 + 新闻搜索模块

数据来源（按优先级）:
  1. trendradar 热点聚合
  2. Agent 传入的热搜数据
  3. 百度热搜榜爬取
  4. 小红书 MCP 搜索

人物筛选评分模型:
  - 热度分 (30%): 热搜原始热度
  - 受众匹配度 (35%): 明星/网红 > 企业家 > 运动员 > 专家
  - 话题新鲜度 (25%): 争议事件 > 大新闻 > 常规动态 > 无动态
  - PDP可分析性 (10%): 性格鲜明 > 言论丰富 > 信息少
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
# 人物评分配置
# ============================================================

# 受众匹配度评分（小红书用户兴趣）
AUDIENCE_SCORE = {
    "明星": 35,
    "网红": 33,
    "演员": 32,
    "歌手": 32,
    "主播": 30,
    "KOL": 30,
    "知识博主": 28,
    "企业家": 25,
    "商人": 23,
    "运动员": 20,
    "体育明星": 20,
    "电竞选手": 22,
    "政治人物": 0,  # 政治人物直接排除（不符合 PDP 分析调性）
    "专家学者": 10,
    "医生": 10,
    "其他": 15,
}

# 话题新鲜度评分
FRESHNESS_SCORE = {
    "有争议事件": 25,
    "负面新闻": 23,
    "恋情/婚变": 24,
    "近期大新闻": 20,
    "职业变动": 18,
    "获奖/成就": 15,
    "常规动态": 8,
    "无新动态": 3,
}

# PDP可分析性评分
ANALYZABILITY_SCORE = {
    "性格鲜明": 10,
    "言论丰富": 8,
    "有公开采访": 7,
    "有争议言论": 9,
    "信息中等": 5,
    "信息较少": 3,
}

# ============================================================
# 评分计算函数
# ============================================================

def calculate_person_score(person: Dict, hot_score: int = 0) -> int:
    """
    计算人物综合评分（0-100）
    
    评分维度：
    - 热度分 (30%): 基于热搜原始热度
    - 受众匹配度 (35%): 小红书用户兴趣
    - 话题新鲜度 (25%): 事件新鲜程度
    - PDP可分析性 (10%): 性格分析可行性
    """
    score = 0
    
    # 确保 hot_score 是整数
    try:
        hot_score = int(hot_score) if hot_score else 0
    except (ValueError, TypeError):
        hot_score = 0
    
    # 1. 热度分 (0-30)
    if hot_score > 5000000:
        score += 30
    elif hot_score > 1000000:
        score += 25
    elif hot_score > 500000:
        score += 20
    elif hot_score > 100000:
        score += 15
    else:
        score += max(5, int(hot_score / 20000))
    
    # 2. 受众匹配度 (0-35)
    category = person.get("category", "其他")
    score += AUDIENCE_SCORE.get(category, 10)
    
    # 3. 话题新鲜度 (0-25)
    freshness_tags = person.get("freshness_tags", [])
    for tag in freshness_tags:
        score += FRESHNESS_SCORE.get(tag, 5)
    if not freshness_tags:
        score += 5  # 默认中等
    
    # 4. PDP可分析性 (0-10)
    analyzability_tags = person.get("analyzability_tags", [])
    for tag in analyzability_tags:
        score += ANALYZABILITY_SCORE.get(tag, 3)
    if not analyzability_tags:
        score += 3  # 默认较少信息
    
    return min(score, 100)


# ============================================================
# 数据源层
# ============================================================

def _mcp_trendradar_call(tool_name: str, params: dict) -> Optional[dict]:
    """
    通过 MCP Streamable HTTP 协议调用 trendradar 工具
    """
    TRENDRADAR_MCP_URL = "http://100.111.235.91:3333/mcp"
    
    try:
        # 1. Initialize （获取 session）
        init_req = {
            "jsonrpc": "2.0", "id": "init", "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "xhs-publisher", "version": "1.0"},
            }
        }
        # 不经过代理直连（100.111.x.x 是内网地址）
        no_proxy = {"http": None, "https": None}
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        r = requests.post(TRENDRADAR_MCP_URL, json=init_req, headers=h, proxies=no_proxy, timeout=10)
        if r.status_code != 200:
            return None
        
        sess_id = r.headers.get("mcp-session-id")
        if not sess_id:
            return None
        h["Mcp-Session-Id"] = sess_id
        
        # 2. Send initialized notification
        requests.post(TRENDRADAR_MCP_URL,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=h, proxies=no_proxy, timeout=5)
        
        # 3. Call tool
        call_req = {
            "jsonrpc": "2.0", "id": "call", "method": "tools/call",
            "params": {"name": tool_name, "arguments": params}
        }
        r2 = requests.post(TRENDRADAR_MCP_URL, json=call_req, headers=h, proxies=no_proxy, timeout=30)
        if r2.status_code != 200:
            return None
        
        # 4. Parse SSE: "event: message\r\ndata: {json}\r\n\r\n"
        # 强制使用 UTF-8 解码（content-type: text/event-stream 不含 charset）
        raw_text = r2.content.decode("utf-8") if hasattr(r2, 'content') else r2.text
        for line in raw_text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                json_str = line[6:]
                try:
                    raw = json.loads(json_str)
                except json.JSONDecodeError:
                    continue
                if "error" not in raw:
                    content = raw.get("result", {}).get("content", [])
                    for item in content:
                        text = item.get("text", "")
                        try:
                            return json.loads(text)
                        except:
                            pass
                return None  # error 或 content 为空
                
    except Exception as e:
        logger.debug(f"trendradar MCP 调用失败 ({tool_name}): {e}")
    
    return None


def fetch_trendradar_news(limit: int = 30) -> List[Dict]:
    """
    通过 MCP 协议从 trendradar 获取热点新闻
    Returns: [{"word": "标题", "hotScore": 热度, "platform": "平台"}]
    """
    def _parse_items(items: list) -> list:
        """解析 trendradar 返回的数据项"""
        results = []
        for item in items:
            title = item.get("title", "")
            platform = item.get("platform", "")
            rank = item.get("rank", 0)
            weight = item.get("weight", 0)
            if title:
                results.append({
                    "word": title,
                    "hotScore": max(
                        int(5000000 / max(rank, 1)),
                        int(weight * 10000),
                        100000
                    ),
                    "platform": platform,
                })
        return results
    
    # 方法1: 优先从娱乐向平台获取（微博+抖音+B站），量大才能筛出明星
    result = _mcp_trendradar_call("get_latest_news", {
        "limit": min(limit * 3, 100),  # 多取一些
        "include_url": False,
        "platforms": ["weibo", "douyin", "bilibili-hot-search"]
    })
    
    if result and isinstance(result, dict) and result.get("success"):
        items = result.get("data", [])
        results = _parse_items(items)
        if results:
            logger.info(f"✅ trendradar 娱乐平台热点获取成功: {len(results)} 条")
            return results[:limit]
    
    # 方法2: 降级到全平台
    result = _mcp_trendradar_call("get_latest_news", {
        "limit": limit, "include_url": False
    })
    
    if result and isinstance(result, dict) and result.get("success"):
        items = result.get("data", [])
        results = _parse_items(items)
        if results:
            logger.info(f"✅ trendradar 全平台热点获取成功: {len(results)} 条")
            return results[:limit]
    
    logger.info("ℹ️ trendradar 不可用，将使用百度热搜作为降级方案")
    return []


def fetch_baidu_hotsearch(max_items: int = 20) -> List[Dict]:
    """抓取百度热搜实时榜单"""
    url = "https://top.baidu.com/board?tab=realtime"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = "utf-8"
        m = re.search(r'<!--s-data:(.*?)-->', r.text, re.DOTALL)
        if not m:
            logger.warning("百度热搜数据未找到")
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
        logger.info(f"✅ 百度热搜抓取成功: {len(results)} 条")
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
        except Exception as e:
            logger.debug(f"MCP搜索 [{kw}] 不可用: {e}")
        if len(results) >= max_notes:
            break
    return results[:max_notes]


# ============================================================
# 分析层
# ============================================================

def extract_people_from_trending(trending_data: List[Dict]) -> List[Dict]:
    """
    用 LLM 分析热搜数据，提取人物类热点并评分
    Returns: [{"name": "...", "score": 85, "hotScore": 1234567, ...}]
    """
    if not trending_data:
        return []

    words_with_score = []
    for i, item in enumerate(trending_data):
        hot = item.get('hotScore', 0)
        hot_text = f"[热度{hot}]" if hot else ""
        words_with_score.append(f"{i+1}. {item['word']} {hot_text}")
    words_text = "\n".join(words_with_score)

    prompt = f"""分析以下热搜榜单，提取**人物类**热点并评估质量。

热搜列表：
{words_text}

要求：
1. 提取明确涉及具体人物的词条（明星/企业家/网红/知识博主/运动员/电竞选手等）
2. **排除政治人物**（不提取任何国家元首、政府官员、政治领袖）
3. 排除群体名称（如"中国队"）、模糊指代
4. 对每个人物，评估以下维度：

评估维度：
- category: 类别（明星/网红/演员/歌手/主播/企业家/运动员/电竞选手/政治人物/专家学者/其他）
- freshness_tags: 话题标签数组，可选：
  * "有争议事件" - 有争议、负面、讨论度高
  * "恋情/婚变" - 感情相关
  * "近期大新闻" - 重大职业变动、大事件
  * "获奖/成就" - 获得奖项、成就认可
  * "常规动态" - 一般性新闻
  * "无新动态" - 缺乏新鲜话题
- analyzability_tags: PDP分析可行性，可选：
  * "性格鲜明" - 性格特征明显、有代表性
  * "言论丰富" - 公开采访、发言多
  * "有争议言论" - 有标志性争议言论
  * "信息中等" - 有一定公开信息
  * "信息较少" - 公开信息有限

返回JSON格式：
{{
  "people": [
    {{
      "name": "董宇辉",
      "reason": "与辉同行直播带货创新高，展现孔雀型特质",
      "category": "知识博主",
      "freshness_tags": ["近期大新闻"],
      "analyzability_tags": ["言论丰富", "性格鲜明"]
    }}
  ]
}}

注意：只返回评分潜力高的人物（有话题度、有分析价值）。"""
    try:
        result = call_llm_json(
            system_prompt="你是小红书内容运营专家，擅长筛选适合性格分析话题的热点人物。",
            user_prompt=prompt,
            temperature=0.3,
        )
        people = result.get("people", [])
        
        # 过滤并计算评分
        filtered_people = []
        for p in people:
            if len(p.get("name", "")) < 2:
                continue
            
            # 找到对应的热搜热度
            hot_score = 0
            for item in trending_data:
                if item is None:
                    continue
                word = item.get("word", "")
                if not word:
                    continue
                if p["name"] in word or word in p.get("reason", ""):
                    hot_score = item.get("hotScore", 0)
                    break
            
            p["hotScore"] = hot_score
            p["score"] = calculate_person_score(p, hot_score)
            filtered_people.append(p)
        
        # 按评分降序
        filtered_people.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        logger.info(f"📊 从热搜中提取到 {len(filtered_people)} 个人物（已评分排序）")
        for p in filtered_people[:5]:
            tags = p.get('freshness_tags', [])
            tag_str = f" [{','.join(tags[:2])}]" if tags else ""
            logger.info(f"  [{p['score']}分] {p['name']} ({p.get('category','未知')}){tag_str}")
        
        return filtered_people
    except Exception as e:
        logger.error(f"人物提取失败: {e}")
        return []


def extract_people_from_xhs_notes(notes: List[Dict]) -> List[Dict]:
    """从XHS笔记中提取人物（备用方案）"""
    if not notes:
        return []
    text = "\n".join([f"- {n.get('title','')} | {n.get('desc','')}" for n in notes])
    prompt = f"""分析以下小红书笔记，提取可能涉及的热点人物：

{text}

提取人物并评估：
- category: 类别
- freshness_tags: ["常规动态"]
- analyzability_tags: ["信息中等"]

返回JSON：{{"people": [...]}}"""
    try:
        result = call_llm_json(
            system_prompt="你是一个小红书内容分析师。",
            user_prompt=prompt,
            temperature=0.3,
        )
        people = result.get("people", [])
        for p in people:
            p["score"] = calculate_person_score(p, 50000)
        people.sort(key=lambda x: x.get("score", 0), reverse=True)
        return people
    except:
        return []


# ============================================================
# 新闻搜索层
# ============================================================

def search_person_news(person_name: str) -> str:
    """搜索指定人物的公开新闻资料"""
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
}}"""
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
{result.get('summary', '暂无')}"""
        logger.info(f"✅ 获取 {person_name} 新闻资料成功")
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
    
    优先级：
    1. 如果传入了 external_data，直接使用
    2. 否则先尝试 trendradar
    3. trendradar 失败则使用百度热搜
    """
    # ---- 步骤1: 获取热搜数据 ----
    trending_data = external_data
    
    if not trending_data:
        # 优先使用 trendradar
        logger.info("📡 步骤1/3: 从 trendradar 获取热点...")
        trending_data = fetch_trendradar_news(30)
        
        # trendradar 失败则降级到百度
        if not trending_data:
            logger.info("📡 步骤1/3: trendradar 不可用，降级到百度热搜...")
            trending_data = fetch_baidu_hotsearch(30)
        
        logger.info(f"  获取到 {len(trending_data)} 条热搜")

    # ---- 步骤2: 提取人物类热点 ----
    logger.info("🔍 步骤2/3: 提取人物类热点并评分...")
    people = extract_people_from_trending(trending_data)
    
    # 总是取最高分人物，不硬性过滤
    # 如果有评分≥60的，取top N；如果没有，也取评分最高的
    high_score = [p for p in people if p.get("score", 0) >= 60]
    
    if high_score:
        people = high_score[:max_people]
        logger.info(f"📊 取评分≥60的人物: {len(people)} 个")
    else:
        # 即使评分低也取最高分（不能空跑）
        people = people[:1]
        logger.warning(f"⚠️ 所有人评分<60，取最高分: {people[0]['name']}({people[0].get('score',0)}分)")
    
    if not people:
        logger.warning("❌ 未提取到任何人物")
        return []

    # ---- 步骤3: 匹配人物到原始新闻标题 ----
    logger.info("📰 步骤3/3: 匹配真实新闻标题...")
    results = []
    for person in people:
        # 从热搜中找到提及该人物的真实标题
        matched_news = []
        for item in trending_data:
            word = item.get("word", "")
            if person["name"] in word:
                platform = item.get("platform", "")
                matched_news.append(f"[{platform}] {word}")
        
        # 用真实新闻标题作为素材，不要 LLM 编造
        news_text = "\n".join(matched_news) if matched_news else f"热点人物：{person['name']}（{person.get('reason', '')}）"
        logger.info(f"  {person['name']}: 匹配到 {len(matched_news)} 条真实新闻")
        
        results.append({
            "name": person["name"],
            "reason": person.get("reason", ""),
            "category": person.get("category", ""),
            "score": person.get("score", 0),
            "hotScore": person.get("hotScore", 0),
            "freshness_tags": person.get("freshness_tags", []),
            "analyzability_tags": person.get("analyzability_tags", []),
            "news": news_text,
        })

    logger.info(f"✅ 热点挖掘完成: {[r['name'] for r in results]}")
    return results


def format_agent_search_query() -> str:
    """返回 Agent 应使用的搜索查询"""
    return "2026年 热搜人物 热点人物 今日热搜人物"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = run(max_people=3)
    print(json.dumps(results, ensure_ascii=False, indent=2))
