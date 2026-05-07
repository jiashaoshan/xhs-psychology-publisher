# 🧠 xhs-psychology-publisher

> 小红书心理产品运营技能 — PDP性格分析长文自动生成与发布

基于 **trendradar 热点引擎 + LLM 性格分析 + ADB 手机操控** 的全自动小红书内容运营工具。

---

## 功能矩阵

| 功能 | 状态 | 说明 |
|------|------|------|
| 📊 **热点挖掘** | ✅ | 自动爬取百度热搜/trendradar热点，提取人物类话题 |
| 🧠 **PDP性格分析** | ✅ | LLM 根据人物新闻分析其 PDP 性格类型（老虎/孔雀/考拉/猫头鹰/变色龙） |
| ✍️ **长文生成** | ✅ | 2000-2500字小红书风格性格分析长文 |
| 📱 **ADB自动发布** | ✅ | 操控 Android 手机完成：写长文 → 一键排版 → 添加商品组件 → 公开可见 → 发布 |
| 🔮 **MBTI产品运营** | ⏳ 待实现 | - |

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    Agent 编排层                       │
│  web_search ↓ 热搜数据 ↓ result                      │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│               hotspot_news_search.py                  │
│  数据源: trendradar / 百度热搜 / Agent传入             │
│  功能: 热搜抓取 → LLM人物提取 → 新闻搜索               │
└─────────────────────────────────────────────────────┘
                          │ (人物名+新闻资料)
                          ▼
┌─────────────────────────────────────────────────────┐
│               pdp_article_publisher.py                │
│  功能: LLM PDP分析 → 长文生成 → 校验(含标题+字数)     │
│  ├ editor_body: 纯PDP分析(2000-2500字, 无产品引导)     │
│  └ xhs_body: 正文前段 + 产品CTA(≤1000字)              │
└─────────────────────────────────────────────────────┘
                          │ (标题+正文+xhs正文)
                          ▼
┌─────────────────────────────────────────────────────┐
│                  phone_controller.py                  │
│  功能: ADB操控Android手机发布                          │
│  流程:                                                │
│  1. 打开小红书 → 写文字 → 写长文                        │
│  2. 输入标题 + 编辑器正文                               │
│  3. 一键排版(等待24s)                                   │
│  4. 下一步 → 处理模板选择页                              │
│  5. 输入xhs正文(含产品CTA)                              │
│  6. 添加组件 → 商品 → 选PDP产品                         │
│  7. 确认 → 点屏幕中间 → 公开可见                         │
│  8. 发布笔记                                            │
└─────────────────────────────────────────────────────┘
```

---

## 数据流

### PDP长文发布全流程

```
[1. 热点获取]
  trendradar / 百度热搜 → 获取实时热搜榜单
       ↓
[2. 人物提取]
  LLM 从热搜词条中分析提提取人物类热点
  → 输出: {"name": "Faker李相赫", "reason": "退役从政", ...}
       ↓
[3. 新闻搜索]
  LLM 基于训练数据 + 公开信息生生成人物新闻摘要
  → 输出: 人物的职业背景、近期事件、性格特征
       ↓
[4. PDP分析 + 文章生成]
  LLM 根据PDP性格模型分析人物类型
  → editor_body(2000-2500字, 纯分析, 无产品引导)
  → xhs_body(正文前段 + 产品CTA)
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

### PDP性格模型

PDP（Professional Dynametric Programs）将人的性格分为5种类型：

| 类型 | 代号 | 特质 |
|------|------|------|
| 🦁 老虎型 | 支配型 | 权威导向，果断自信，目标感强 |
| 🦚 孔雀型 | 表达型 | 社交达人，热情乐观，善于感染他人 |
| 🐨 考拉型 | 耐心型 | 温和稳健，善于倾听，团队和谐 |
| 🦉 猫头鹰型 | 精确型 | 追求完美，数据导向，条理清晰 |
| 🦎 变色龙型 | 整合型 | 灵活变通，适应力强，善于协调 |

---

## 安装与依赖

### 硬件依赖

- **Android 手机**（已开启 USB 调试）
- **USB 数据线** 连接电脑
- **ATX Keyboard** 设为默认输入法（用于 ADB 文本输入）

### 系统依赖

```bash
# ADB (Android Debug Bridge)
# macOS 通常已自带，如没有:
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

或配置在 `~/.openclaw/openclaw.json`：
```json
{
  "env": {
    "DEEPSEEK_API_KEY": "sk-xxx",
    "ANDROID_SERIAL": "FAS84PQ45T8HTOTK"
  }
}
```

### 外部服务

| 服务 | 用途 | 获取方式 |
|------|------|----------|
| **DeepSeek API** | LLM 文章生成 | https://platform.deepseek.com |
| **trendradar-news** (MCP) | 热点数据源 | 可选，不启动则降级为百度热搜爬取 |

---

## 配置

`config/publish.json`:

```json
{
  "product": {
    "pdp_url": "https://huixin.interwestinfo.com/custweb/home/pdpEntry/gb?td_channelid=wx",
    "pdp_name": "PDP性格测试揭示天赋秘密",
    "mbti_url": "",
    "mbti_name": ""
  },
  "publish": {
    "visibility": "公开可见",
    "product_component": true,
    "xhs_body_max_chars": 1000,
    "editor_body_target_chars": 2500
  },
  "hotspot": {
    "max_people_per_run": 3,
    "max_news_per_person": 5
  }
}
```

---

## 快速开始

```bash
# 1. 全自动流程（热点挖掘 → PDP分析 → ADB发布）
python3 xhs_psychology_publisher.py --pdp --publish

# 2. 指定人物手动分析
python3 xhs_psychology_publisher.py --pdp --person "董宇辉" --publish

# 3. 仅生成不发布（测试用）
python3 xhs_psychology_publisher.py --pdp --dry-run

# 4. MBTI模块（待实现）
python3 xhs_psychology_publisher.py --mbti --publish
```

---

## 文件结构

```
xhs-psychology-publisher/
├── SKILL.md                           ← OpenClaw 技能元描述
├── xhs_psychology_publisher.py        ← CLI 入口
├── requirements.txt                   ← Python 依赖
├── scripts/
│   ├── phone_controller.py            ← ADB 手机操控核心（商品组件+公开可见）
│   ├── pdp_article_publisher.py       ← PDP文章生成与发布（校验+重试）
│   ├── hotspot_news_search.py         ← 热点挖掘（trendradar/百度热搜）
│   └── xhs_llm.py                     ← LLM API 封装（DeepSeek）
├── templates/
│   └── pdp-article-prompt.md          ← PDP分析文章提示词模板
├── config/
│   └── publish.json                   ← 发布配置
├── data/
│   └── published-articles.json        ← 发布历史记录
└── .gitignore
```

---

## 验收标准（QA Checklist）

- [x] trendradar/百度热搜能正确获取实时热点
- [x] LLM 能从热搜中提取人物类关键词
- [x] 文章标题不超过20字，含人物全名
- [x] 编辑器正文在2000-2500字范围内
- [x] 编辑器正文不出现产品引导链接
- [x] xhs正文含产品CTA（PDP性格测试链接）
- [x] ADB 能正确完成写长文→一键排版→下一步
- [x] 预览页能添加"商品"组件并选择指定产品
- [x] 可见范围设置为"公开可见"
- [x] 发布成功并记录到 published-articles.json

---

## License

MIT
