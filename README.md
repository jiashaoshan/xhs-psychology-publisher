# 🧠 xhs-psychology-publisher

> 小红书心理产品运营技能 — PDP性格分析长文自动生成与发布

基于 **trendradar MCP 热点引擎 + LLM 性格分析 + ADB 手机操控** 的全自动小红书内容运营工具。

---

## 功能矩阵

| 功能 | 状态 | 说明 |
|------|------|------|
| 📊 **热点挖掘** | ✅ | MCP trendradar全平台 → 降级百度热搜 → 兜底从标题提人名搜新闻，三层保障不空跑，排除政治人物 |
| 🧠 **人物评分筛选** | ✅ | 4维评分模型（热度30%+受众35%+话题25%+可分析10%），过滤低分人物 |
| ✍️ **长文生成** | ✅ | 1200-1800字，"新闻分析→产品引导"结构，标题不提PDP类型 |
| 📱 **ADB自动发布** | ✅ | 写长文 → 一键排版 → 添加商品组件（PDP性格测试）→ 公开可见 → 发布 |
| 🔮 **MBTI产品运营** | ⏳ 待实现 | - |

---

## 数据流

## 三层兜底热搜挖掘策略

```
[1. 热点获取] 三层兜底
   ├ ① trendradar MCP 全平台 → LLM提取人物+4维评分
   ├ ② 失败则降级百度热搜30条 → LLM提取人物+4维评分
   └ ③ 都失败则最终兜底：
         → 从热搜标题直接提取人名（排除政治人物）
         → search_person_news() 搜索该人物真实新闻资料
       ↓
[2. 去重] → 排除今天已发过的人物
       ↓
[3. 匹配真实新闻标题]
  ★ 直接从热搜数据中匹配该人物的原始标题（不靠LLM编造）
  → 例如: [weibo] 孙颖莎3:2逆转金娜英（真实热搜）
  ★ 兜底路径走 search_person_news() 获取新闻素材
       ↓
[4. PDP分析 + 文章生成]
  LLM 基于真实事件标题 + 公开知识，分析人物性格
  → 结构: 事件拆解→性格分析→转回读者→引导测试
  → editor_body(1200-1800字, 分析+产品钩子)
  → xhs_body(正文前段 + 产品CTA, ≤600字)
       ↓
[5. ADB发布]
  uiautomator2 操控手机:
  ├ 写长文 → 输入标题+正文 → 一键排版
  ├ 预览页 → 输入xhs正文
  ├ 添加组件 → 商品 → 选"PDP性格测试揭示天赋秘密"
  ├ 确认 → 点屏幕中间
  ├ 设置公开可见
  └ 发布笔记
```

---

## 人物评分模型

### 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 热度分 | 30% | 基于热搜原始热度指数 |
| 受众匹配度 | 35% | 小红书用户兴趣：明星>网红>企业家>运动员>...>政治人物(0分排除) |
| 话题新鲜度 | 25% | 争议事件>恋情/婚变>大新闻>常规动态 |
| PDP可分析性 | 10% | 性格鲜明>言论丰富>信息中等 |

### 人物排除规则

- **政治人物自动过滤**（评分=0 + LLM prompt明确排除）
- **群体名称排除**（如"中国队"）
- **模糊指代排除**（如"某CEO"无具体姓名）

---

## 文章生成策略

### 标题要求
- **≤20字**，不提PDP/性格测试/产品名
- 围绕「人物 + 事件」制造好奇心
- 5种标题公式：反差反转/爆料揭秘/金句暴击/情绪共鸣/结果先行

### 正文结构（1200-1800字）

```
一、热点钩子（150-200字）
   直接热点事件切入，制造悬念

二、性格分析——事件深度拆解（700-1000字）
   ★ 格式：事件1 → 性格分析 → 事件2 → 性格分析 → 事件3 → 性格分析
   ★ 至少3个具体事件，每个逐条拆解
   ★ "这个人做了什么 → 为什么这反映XX性格"

三、转回读者 + 产品钩子（200-300字）
   ★ "看完TA的分析，你呢？"
   ★ "你遇到这种情况会怎么选？"
   ★ "你知道自己是什么类型吗？"

四、Hashtag（3-5个）
```

---

## MCP 集成

热点头数据通过 **MCP Streamable HTTP 协议** 从 trendradar-news 获取：

```python
# MCP 协议流程
1. POST /mcp → initialize → 获取 session-id
2. POST /mcp → notifications/initialized
3. POST /mcp → tools/call (get_latest_news / search_news)

# 代理说明
远程服务器地址: http://100.111.235.91:3333/mcp
需绕过本地代理（proxies={'http': None, 'https': None}）
```

---

## 安装与依赖

### 硬件依赖

- **Android 手机**（已开启 USB 调试）
- **USB 数据线** 连接电脑
- **ATX Keyboard** 设为默认输入法（用于 ADB 文本输入）

### 系统依赖

```bash
# ADB (Android Debug Bridge)
brew install android-platform-tools

# Python 依赖
pip install -r requirements.txt
```

`requirements.txt`:
```
uiautomator2>=0.18.0
requests>=2.28.0
```

### 环境变量

```bash
export ANDROID_SERIAL="FAS84PQ45T8HTOTK"  # ADB 设备串号
export DEEPSEEK_API_KEY="sk-xxx"          # LLM API Key
```

### 外部服务

| 服务 | 用途 |
|------|------|
| **DeepSeek API** | LLM 文章生成 |
| **trendradar-news** (MCP) | 热点数据源，降级到百度热搜 |

---

## 快速开始

```bash
# 1. 全自动流程
ANDROID_SERIAL=FAS84PQ45T8HTOTK python3 xhs_psychology_publisher.py --pdp --publish

# 2. 指定人物手动分析
ANDROID_SERIAL=FAS84PQ45T8HTOTK python3 xhs_psychology_publisher.py --pdp --person "孙颖莎" --publish

# 3. 仅生成不发布（测试用）
python3 xhs_psychology_publisher.py --pdp --dry-run
```

---

## 文件结构

```
xhs-psychology-publisher/
├── SKILL.md
├── xhs_psychology_publisher.py        ← CLI 入口
├── requirements.txt
├── scripts/
│   ├── phone_controller.py            ← ADB 手机操控
│   ├── pdp_article_publisher.py       ← PDP文章生成（评分排序+标题校验+字数控制）
│   ├── hotspot_news_search.py         ← 热点挖掘（MCP/百度热搜+评分+匹配真实标题）
│   └── xhs_llm.py                     ← LLM API 封装（DeepSeek）
├── templates/
│   └── pdp-article-prompt.md          ← 文章提示词（新闻分析→产品引导结构）
├── config/
│   └── publish.json
├── data/
│   └── published-articles.json
└── .gitignore
```

---

## License

MIT
