#!/usr/bin/env python3
"""
测试：Pexels 搜图 → ADB推图 → 小红书长文选图发布
先跑测试版（只走到预览页不发布），验证流程是否顺畅。

用法:
  python3 test_images_publish.py              # 测试模式（不发布）
  python3 test_images_publish.py --real       # 真实发布
  python3 test_images_publish.py --topic 大自然  # 指定搜图主题
"""
import argparse, json, logging, os, sys, time
from pathlib import Path
from datetime import datetime

# 添加脚本目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / "scripts"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("test-images-publish")

# ── 测试图片下载（无API key时用免费图源） ──

def download_test_images(topic: str = "nature", count: int = 3) -> list:
    """
    下载测试图片（无需API key）。
    使用免费图源 picsum.photos / lorempixel。
    返回本地路径列表。
    """
    import requests
    out_dir = SCRIPT_DIR / "data" / "test_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded = []
    for i in range(count):
        # 每次取不同的随机图片，强制不同seed
        seed = int(time.time()) + i
        url = f"https://picsum.photos/seed/{seed}/800/1200"
        filepath = out_dir / f"test_{topic}_{i+1}.jpg"
        
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            logger.info(f"✅ 下载测试图 {i+1}: {filepath} ({len(resp.content)} bytes)")
            downloaded.append(str(filepath))
        except Exception as e:
            logger.error(f"❌ 下载失败: {e}")
            # fallback: 用 simple 图片
            try:
                url2 = f"https://picsum.photos/{800}/{1200}?random={seed}"
                resp2 = requests.get(url2, timeout=30)
                resp2.raise_for_status()
                filepath.write_bytes(resp2.content)
                logger.info(f"✅ fallback下载: {filepath}")
                downloaded.append(str(filepath))
            except:
                logger.error("所有图源都失败了")
    
    return downloaded


# ── 主流程 ──

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="真实发布（默认只走到预览页）")
    parser.add_argument("--topic", default="nature", help="图片主题")
    parser.add_argument("--count", type=int, default=2, help="图片数量")
    args = parser.parse_args()

    print("=" * 60)
    print("  小红书自定义图片发布测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模式: {'✅ 真实发布' if args.real else '🔍 预览测试（不发布）'}")
    print(f"  主题: {args.topic}")
    print(f"  图片: {args.count}张")
    print("=" * 60)

    # Step 1: 下载测试图片
    print("\n📥 Step 1: 下载测试图片...")
    images = download_test_images(args.topic, args.count)
    if not images:
        logger.error("❌ 没有可用的图片，终止")
        return
    print(f"   已下载 {len(images)} 张: {[os.path.basename(p) for p in images]}")

    # Step 2: 推送图片 + 小红书长文编辑（测试/发布）
    print(f"\n{'📲' if args.real else '🔬'} Step 2: {'发布' if args.real else '预览测试（不发布）'}")
    
    from phone_controller import xie_chang_wen, xie_chang_wen_preview
    
    if args.real:
        # 真实发布
        xie_chang_wen(
            editor_body="这是一条通过AI自动发布的测试笔记。\n\n"
                        "测试功能：\n1. Pexels图片搜索\n2. ADB推送到手机相册\n"
                        "3. 小红书长文编辑器选图\n4. 一键排版\n5. 自动发布\n\n"
                        "#测试 #自动化 #AI #小红书",
            publish_body="这是一条测试笔记，验证自定义图片推送+选图+发布的全流程是否通畅。",
            title="测试自定义配图发布",
            product_name="PDP性格测试揭示天赋秘密",
            image_paths=images,
        )
        print("\n✅ 发布完成")
    else:
        # 预览测试（不发布）
        xie_chang_wen_preview(
            editor_body="这是一条测试内容，验证自定义图片推送到手机并在长文中发布的效果。",
            title="测试自定义配图",
            image_paths=images,
        )
        print("\n✅ 预览测试完成。请查看手机屏幕确认效果。")
    
    print("=" * 60)


if __name__ == "__main__":
    # 快速清理旧测试图片
    test_dir = SCRIPT_DIR / "data" / "test_images"
    if test_dir.exists():
        for f in test_dir.glob("*.jpg"):
            if time.time() - f.stat().st_mtime > 3600:
                f.unlink()
    main()
