#!/usr/bin/env python3
"""
xhs-psychology-publisher — 小红书心理产品运营技能

功能:
  1. PDP产品长文：热点人物 → 新闻 → PDP分析 → ADB发布（含商品组件+公开可见）
  2. MBTI产品长文（待实现）

命令行:
  # PDP完整流程（推荐）
  python3 xhs_psychology_publisher.py --pdp --publish

  # PDP指定人物
  python3 xhs_psychology_publisher.py --pdp --person "董宇辉" --publish

  # PDP仅生成不发布
  python3 xhs_psychology_publisher.py --pdp --dry-run

  # MBTI（待实现）
  python3 xhs_psychology_publisher.py --mbti --publish
"""
import argparse, json, logging, sys, os
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

log_file = DATA_DIR / f"publisher_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(str(log_file), encoding="utf-8")],
)

sys.path.insert(0, str(SCRIPT_DIR / "scripts"))


def banner():
    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║   小红书心理产品运营技能                  ║")
    print("  ║   PDP长文 | MBTI长文（待实现）            ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()


def cmd_pdp(args):
    """PDP产品长文: 热点人物 → 新闻 → PDP分析 → ADB发布"""
    from pdp_article_publisher import run_publish
    result = run_publish(
        person_name=args.person,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_mbti(args):
    """MBTI产品长文（待实现）"""
    print("⏳ MBTI产品长文模块待实现")
    return {"status": "not_implemented", "module": "mbti"}


def main():
    banner()
    parser = argparse.ArgumentParser(description="小红书心理产品运营技能")

    # PDP 模式
    parser.add_argument("--pdp", action="store_true", help="PDP产品长文发布")
    parser.add_argument("--person", "-p", help="指定分析人物（可选，不指定则自动搜索热点）")

    # MBTI 模式
    parser.add_argument("--mbti", action="store_true", help="MBTI产品长文（待实现）")

    # 通用参数
    parser.add_argument("--publish", action="store_true", help="生成并发布")
    parser.add_argument("--dry-run", action="store_true", help="仅生成不发布")

    args = parser.parse_args()

    if args.pdp:
        result = cmd_pdp(args)
    elif args.mbti:
        result = cmd_mbti(args)
    else:
        parser.print_help()
        return

    # 结果摘要
    if isinstance(result, dict):
        status = result.get("status", "unknown")
        articles = result.get("articles", [])
        published = result.get("published", [])
        if status == "dry_run":
            print(f"\n📋 干运行完成，生成了 {len(articles)} 篇文章（未发布）")
        elif status == "published":
            print(f"\n✅ 成功发布 {len(published)} 篇PDP长文")
        elif status == "failed":
            print(f"\n❌ 发布失败: {result.get('error', '未知错误')}")
        elif status == "not_implemented":
            print(f"\n⏳ 该模块待实现")


if __name__ == "__main__":
    main()
