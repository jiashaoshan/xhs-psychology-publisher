---
name: xhs-psychology-publisher
description: |
  小红书心理产品运营技能。
  功能：
    - PDP产品长文：搜索小红书人物热点 → 搜索该人物新闻 → LLM结合PDP性格分析 → ADB发布长文（含商品组件+公开可见）
    - MBTI产品长文（待实现）
  基于 uiautomator2 (ADB) + LLM + Web 搜索
metadata:
  openclaw:
    emoji: "🧠"
    requires:
      env: ["DEEPSEEK_API_KEY", "ANDROID_SERIAL"]
    category: "acquisition"
    tags: ["xiaohongshu", "psychology", "pdp", "mbti", "adb", "publish"]
---

# 小红书心理产品运营技能 (xhs-psychology-publisher)

## 功能矩阵

| 功能 | 状态 | 说明 |
|------|------|------|
| 🧠 PDP产品长文 | ✅ 可用 | 热点人物 → 新闻 → PDP性格分析 → 长文发布（含商品组件+公开可见）|
| 🔮 MBTI产品长文 | ⏳ 待实现 | - |

## PDP产品长文发布流程

```
[1. 热搜挖掘] 三层兜底：
   ├ ① trendradar MCP（全平台）→ LLM提取人物并评分
   ├ ② 降级百度热搜 → LLM提取人物并评分
   └ ③ 最终兜底：从标题直接提取人名 → search_person_news() 搜真实新闻
      ↓
[2. 去重] → 排除今天已发过的人物
      ↓
[3. 新闻匹配] → 从热搜中匹配该人物的原始标题（不靠LLM编造）
      ↓
[4. PDP分析]  → LLM 根据新闻+PDP理论分析人物性格类型
      ↓
[5. 文章生成] → LLM 生成小红书风格长文（性格分析+产品引导）
      ↓
[6. ADB发布]  → ADB 操控手机发布长文
      │          ├ 预览页：添加"商品组件" → 选择"PDP性格测试揭示天赋秘密"
      │          └ 可见范围：公开可见
      ↓
[7. 记录]     → 持久化已发布文章
```

## 快速使用

```bash
# 完整流程：自动爬百度热搜 → 提取人物 → PDP分析 → 发布
python3 xhs_psychology_publisher.py --pdp --publish

# 仅生成文章不发布（测试用）
python3 xhs_psychology_publisher.py --pdp --dry-run

# 指定人物手动分析（跳过热搜搜索）
python3 xhs_psychology_publisher.py --pdp --person "董宇辉"

# 发MBTI长文（待实现）
python3 xhs_psychology_publisher.py --mbti --publish
```

### Agent 编排模式（推荐）

当顶层Agent调用此技能时，先用 web_search 搜索热搜，再将结果传给人物的Python脚本：

```python
# Agent层代码（示意）
from hotspot_news_search import run as analyze_hotspot

# 步骤1: Agent 用 web_search 搜索
search_results = web_search("2026年5月热搜人物 热点人物")
# 格式化为 [{word, hotScore}, ...]
trending_data = parse_search_results(search_results)

# 步骤2: 传给脚本做分析
people = analyze_hotspot(external_data=trending_data)
```

## 配置项

`config/publish.json`:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| product_url | https://huixin.interwestinfo.com/custweb/home/pdpEntry/gb?td_channelid=wx | PDP产品链接 |
| product_name | PDP性格测试揭示天赋秘密 | 商品组件中选择的产品名 |
| publish_visibility | 公开可见 | 发布可见范围 |
| max_hot_people | 3 | 每次扫描最多候选人物 |
| max_news_per_person | 5 | 每人最多搜索新闻条数 |

## 依赖

- Android 手机 + USB 连接
- ATX Keyboard 设为默认输入法
- 环境变量: `DEEPSEEK_API_KEY`, `ANDROID_SERIAL`
- pip: `uiautomator2`, `requests`

## 文件结构

```
xhs-psychology-publisher/
├── SKILL.md
├── xhs_psychology_publisher.py    ← CLI 入口
├── scripts/
│   ├── phone_controller.py        ← ADB 手机操控（公开可见+商品组件）
│   ├── pdp_article_publisher.py   ← PDP文章生成与发布
│   ├── hotspot_news_search.py     ← 热点挖掘+新闻搜索
│   └── xhs_llm.py                 ← LLM API 封装
├── templates/
│   └── pdp-article-prompt.md      ← PDP文章生成提示词
├── config/
│   └── publish.json               ← 配置
└── data/                          ← 运行时数据
```
