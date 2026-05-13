# 🧠 xhs-psychology-publisher

> 小红书心理产品运营技能 — PDP性格分析 + 自测类内容自动生成与发布

基于 **LLM + ADB 手机操控** 的全自动小红书内容运营工具。支持双模式运营：

- **模式A** 🧠 PDP名人分析：热点人物 → 新闻 → PDP性格分析 → 长文发布
- **模式B** 🎯 自测类文章：5种内容类型轮换 → LLM生成 → 读者互动引流

---

## 功能矩阵

| 功能 | 状态 | 说明 |
|------|------|------|
| 🧠 **PDP名人分析** | ✅ 可用 | 热点人物 → 新闻 → PDP性格分析 → 长文发布（含商品组件）|
| 🎯 **自测类文章** | ✅ 可用 | 5种读者代入型内容轮换发布，私信引流转化 |
| 📊 **热点挖掘** | ✅ | MCP trendradar全平台 → 降级百度热搜 → 兜底搜新闻 |
| 🧠 **人物评分筛选** | ✅ | 4维评分模型，过滤低分/政治人物 |
| ✍️ **长文生成** | ✅ | LLM生成小红书风格长文，含排版+标题校验+字数控制 |
| 📱 **ADB自动发布** | ✅ | 写长文 → 一键排版 → 添加商品组件/私信引导 → 公开可见 → 发布 |
| 🔮 **MBTI产品运营** | ⏳ 待实现 | - |

---

## 双模式运营策略

两种内容模式可配合使用：奇数日跑PDP名人分析，偶数日跑自测类文章，交替冲流量。

### 模式A: PDP名人分析

利用热点人物新闻事件，分析其PDP性格类型，引导读者对自己产生好奇。

**数据流:**
```
[1. 热点获取] 三层兜底
   ├ ① trendradar MCP 全平台 → LLM提取人物+4维评分
   ├ ② 降级百度热搜30条 → LLM提取人物+4维评分
   └ ③ 兜底：从标题提取人名 → search_person_news()
       ↓
[2. 去重] → 排除今天已发过的人物
       ↓
[3. 匹配真实新闻标题] → 不靠LLM编造
       ↓
[4. PDP分析 + 文章生成] → editor_body + xhs_body
       ↓
[5. ADB发布] → 商品组件 + 公开可见
```

**正文结构（1200-1800字）:**
```
一、热点钩子（150-200字）
二、性格分析——事件深度拆解（700-1000字）至少3个具体事件
三、转回读者 + 产品钩子（200-300字）
四、Hashtag
```

### 模式B: 自测类文章

不分析名人，而是让读者代入自己。5种内容类型轮换，疲劳度低。

**5种内容类型:**

| 类型 | 说明 | 标题示例 | 转化路径 |
|------|------|----------|----------|
| ① 职场性格对比 | 对比两种PDP性格的职场表现 | "老虎型 vs 孔雀型，职场谁更吃得开？" | 商品组件 |
| ② 互动测试帖 | 3-5个问题测性格 | "3个问题测出你的隐藏性格" | 商品组件 |
| ③ 情侣/关系帖 | 不同性格在关系中的表现 | "老虎型女友 vs 考拉型男友" | 商品组件 |
| ④ 故事型 | 第一人称发现自我的故事 | "面试官一眼看出我是孔雀型" | 商品组件 |
| ⑤ 评论区引流帖 | 评论区互动引导（不加商品组件） | "评论区留下答案帮你分析" | 私信引流 |

**每个类型差异:**
- ①②③④ → 商品组件 + 公开可见
- ⑤ → 无商品组件，靠评论区互动→私信→免费测试链接转化

---

## 快速开始

```bash
# 1. PDP名人分析（自动搜热点）
ANDROID_SERIAL=FAS84PQ45T8HTOTK python3 xhs_psychology_publisher.py --pdp --publish

# 2. PDP指定人物
ANDROID_SERIAL=FAS84PQ45T8HTOTK python3 xhs_psychology_publisher.py --pdp --person "孙颖莎"

# 3. 自测类文章
ANDROID_SERIAL=FAS84PQ45T8HTOTK python3 xhs_psychology_publisher.py --self-test --publish

# 4. 自动交替（奇数日PDP，偶数日自测）
python3 xhs_psychology_publisher.py --auto --publish

# 5. 仅生成不发布
python3 xhs_psychology_publisher.py --pdp --dry-run
python3 xhs_psychology_publisher.py --self-test --dry-run
```

---

## 安装与依赖

### 硬件依赖

- **Android 手机**（已开启 USB 调试）
- **USB 数据线** 连接电脑
- **ATX Keyboard** 设为默认输入法（用于 ADB 文本输入）

### 系统依赖

```bash
brew install android-platform-tools
pip install -r requirements.txt
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

## 文件结构

```
xhs-psychology-publisher/
├── SKILL.md
├── README.md
├── xhs_psychology_publisher.py        ← CLI 入口（--pdp / --self-test / --auto）
├── requirements.txt
├── scripts/
│   ├── phone_controller.py            ← ADB 手机操控（商品组件+公开可见）
│   ├── pdp_article_publisher.py       ← PDP文章生成（评分排序+标题校验+字数控制）
│   ├── self_test_publisher.py         ← 自测类文章生成（5种类型轮换+交替）
│   ├── hotspot_news_search.py         ← 热点挖掘（MCP/百度热搜+评分+匹配真实标题）
│   └── xhs_llm.py                     ← LLM API 封装（DeepSeek）
├── templates/
│   ├── pdp-article-prompt.md          ← PDP文章提示词
│   └── self-test-article-prompt.md    ← 自测类文章提示词（5种类型）
├── config/
│   └── publish.json                   ← 配置（产品名、标签、等待时间等）
├── data/
│   └── published-articles.json        ← 发布记录
└── .gitignore
```

---

## License

MIT
