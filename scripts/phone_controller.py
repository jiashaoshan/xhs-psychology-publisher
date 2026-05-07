"""
Phone Controller — 通过 ADB 操控 Android 手机发布小红书长文
基于 xhs-adb-publisher 的 phone_controller.py 改造

✅ 修改点:
  1. 可见范围: 默认"公开可见"（非"仅自己可见"）
  2. 预览页添加"商品组件"并选择指定产品
  3. 所有 time.sleep 加入了随机抖动 (±20%)
"""
import uiautomator2 as u2
import time, os, random, logging, threading

logger = logging.getLogger(__name__)

_device_pool = {}
_device_pool_lock = threading.Lock()

def jitter(sec: float, ratio: float = 0.2) -> float:
    actual = sec * (1 + random.uniform(-ratio, ratio))
    time.sleep(max(actual, 0.1))
    return actual

REF_W, REF_H = 1080, 2400

def _scale(d: u2.Device, x: int, y: int) -> tuple:
    info = d.info
    sw = info.get('displayWidth', REF_W)
    sh = info.get('displayHeight', REF_H)
    return int(x * sw / REF_W), int(y * sh / REF_H)

def get_device(serial: str = None) -> u2.Device:
    global _device_pool, _device_pool_lock
    serial = serial or os.environ.get("ANDROID_SERIAL")
    key = serial or "__default__"
    with _device_pool_lock:
        if key not in _device_pool:
            d = u2.connect(serial) if serial else u2.connect()
            _device_pool[key] = d
            logger.info(f"连接设备 {key} | 分辨率 {d.info.get('displayWidth')}x{d.info.get('displayHeight')}")
        return _device_pool[key]

def home(device: u2.Device = None):
    (device or get_device()).press("home"); jitter(0.3)

def send_text(text: str, device: u2.Device = None):
    (device or get_device()).send_keys(text)

def open_xhs(device: u2.Device = None) -> u2.Device:
    d = device or get_device()
    d.press("home"); jitter(0.5)
    d.app_start("com.xingin.xhs"); jitter(3, 0.1)
    for txt in ["存草稿", "不保存"]:
        el = d(textContains=txt)
        if el.exists(timeout=1):
            el.click(); jitter(1)
            break
    sw = int(d.info.get("displayWidth", 1080))
    sh = int(d.info.get("displayHeight", 2400))
    d.click(sw / 2, sh * 0.95)
    jitter(2)
    return d

def click_xie_wenzi(device: u2.Device = None):
    d = device or get_device()
    el = d(text="写文字")
    if el.exists(timeout=1):
        el.click()
    else:
        sw = int(d.info.get("displayWidth", REF_W))
        sh = int(d.info.get("displayHeight", REF_H))
        d.click(sw / 2, sh * 0.86)
    jitter(1.5)

def wait_for_next_button(d, timeout=10):
    """等待'下一步'按钮出现"""
    for _ in range(timeout * 2):
        btns = list(d(text="下一步"))
        if btns:
            return btns[-1]
        jitter(0.5)
    return None

def add_product_component(product_name: str, device: u2.Device = None):
    """
    在发布预览页添加商品组件
    流程:
      1. 点击"添加组件"
      2. 弹出组件选择层 → 点击"商品"分类
      3. 在商品列表中点击匹配的产品名
      4. 等待1s
      5. 点击底部"确认"按钮
      6. 点击屏幕正中间（关闭弹出层返回预览页）
    """
    d = device or get_device()
    logger.info(f"添加商品组件: {product_name}")

    # 上滑让组件区域露出
    d.swipe(400, 1800, 400, 600, duration=0.2)
    jitter(0.5)

    # 1. 点击"添加组件"区域
    el = d(textContains="添加组件")
    if el.exists(timeout=2):
        el.click()
        logger.info("点击: 添加组件")
    else:
        sw = int(d.info.get("displayWidth", REF_W))
        sh = int(d.info.get("displayHeight", REF_H))
        d.click(sw * 0.5, sh * 0.35)
        logger.info("坐标点击组件区域")
    jitter(2)

    # 2. 在弹出的组件选择层中，点击"商品"分类
    el = d(text="商品")
    if el.exists(timeout=2):
        el.click()
        logger.info("点击分类: 商品")
        jitter(1.5)
    else:
        logger.info("未找到'商品'分类，尝试直接选产品")

    # 3. 在商品列表中点击匹配的产品名
    el = d(textContains=product_name[:8])
    if el.exists(timeout=3):
        el.click()
        logger.info(f"选择商品: {product_name}")
    else:
        # 尝试较短匹配
        el = d(textContains=product_name[:4])
        if el.exists(timeout=2):
            el.click()
            logger.info(f"选择商品(短匹配): {product_name[:4]}")
        else:
            # 点第一个可选结果
            sw = int(d.info.get("displayWidth", REF_W))
            sh = int(d.info.get("displayHeight", REF_H))
            d.click(sw * 0.5, sh * 0.35)
            logger.info("坐标选择第一个商品")
    jitter(1)

    # 4. 等待1s
    jitter(1, 0.05)

    # 5. 点击底部"确认"按钮
    el = d(textContains="确认")
    if el.exists(timeout=2):
        el.click()
        logger.info("点击: 确认")
    else:
        for txt in ["确定", "完成", "添加"]:
            el = d(text=txt)
            if el.exists(timeout=1):
                el.click()
                logger.info(f"点击: {txt}")
                break
    jitter(1)

    # 6. 点击屏幕正中间（关闭弹出层/返回预览页）
    sw = int(d.info.get("displayWidth", REF_W))
    sh = int(d.info.get("displayHeight", REF_H))
    d.click(sw // 2, sh // 2)
    logger.info("点击屏幕正中间")
    jitter(1)

    logger.info("商品组件添加完成")

def set_visibility_to_public(device: u2.Device = None):
    """
    设置可见范围为'公开可见'
    注：小红书默认就是公开可见，此函数用于确认/修复可见性
    """
    d = device or get_device()
    logger.info("确认可见范围: 公开可见")

    # 检查当前可见性标签
    for text in ["仅自己可见", "仅我可见"]:
        el = d(textContains=text)
        if el.exists(timeout=1):
            # 当前是私密状态，需要改为公开
            el.click()
            logger.info(f"当前为{text}，点击修改")
            jitter(1.5)
            # 选择"公开可见"
            for pub_text in ["公开可见", "公开", "所有人可见"]:
                pub_el = d(text=pub_text)
                if pub_el.exists(timeout=1):
                    pub_el.click()
                    logger.info(f"选择: {pub_text}")
                    jitter(0.5)
                    break
            break

    # 如果已经是"公开可见"则无需操作
    for text in ["公开可见", "公开"]:
        if d(textContains=text).exists(timeout=0.5):
            logger.info("已是公开可见")
            break

def publish_note(device: u2.Device = None):
    """点击'发布笔记'按钮"""
    d = device or get_device()
    el = d(text="发布笔记")
    if el.exists(timeout=2):
        el.click()
        logger.info("点击: 发布笔记")
    else:
        sw = int(d.info.get('displayWidth', REF_W))
        sh = int(d.info.get('displayHeight', REF_H))
        d.click(int(sw * 0.65), int(sh * 0.92))
        logger.info("坐标点击发布")
    jitter(8)
    for _ in range(3):
        d.press("home"); jitter(0.3)

def xie_chang_wen(editor_body: str, publish_body: str = "", title: str = "",
                  product_name: str = "PDP性格测试揭示天赋秘密",
                  serial: str = None):
    """
    写长文（含商品组件+公开可见）
    
    Args:
        editor_body: 编辑器正文（长文编辑器的完整内容）
        publish_body: 发布确认页正文（前1000字摘要）
        title: 标题
        product_name: 商品组件中选择的产品名
        serial: ADB设备串号
    """
    d = get_device(serial)
    open_xhs(d)
    click_xie_wenzi(d)

    # 点击"写长文"
    el = d(text="写长文")
    if el.exists(timeout=2):
        el.click()
    else:
        for txt in ["长文"]:
            el = d(textContains=txt)
            if el.exists(timeout=1):
                el.click(); break
    jitter(2)

    # 输入标题
    if title:
        el = d(text="输入标题")
        if el.exists(timeout=2):
            el.click(); jitter(0.3)
            d.send_keys(title); jitter(0.3)

    # 输入正文（编辑器）
    d.click(int(d.info.get("displayWidth", REF_W)) / 2,
            int(d.info.get("displayHeight", REF_H)) * 0.25)
    jitter(0.3)
    chunk_size = 500
    for i in range(0, len(editor_body), chunk_size):
        chunk = editor_body[i:i + chunk_size]
        d.send_keys(chunk); jitter(0.2)
    jitter(0.3)

    # 一键排版
    logger.info("一键排版中...")
    el = d(text="一键排版")
    if el.exists(timeout=3):
        el.click()
        logger.info("点击一键排版")
    logger.info("等待排版渲染中...")
    jitter(24, 0.1)
    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.5):
            break
        jitter(0.5)
    jitter(2)

    # 点击"下一步"
    next_btn = wait_for_next_button(d, timeout=10)
    if next_btn:
        next_btn.click()
        logger.info("点击下一步")
    jitter(2)

    # 处理模板选择页
    for _ in range(5):
        if d(textContains="选择喜欢的排版").exists(timeout=0.3):
            jitter(1)
            # 选择一个模板
            for tpl in ["涂鸦马克"]:
                el = d(text=tpl)
                if el.exists(timeout=0.3):
                    el.click(); break
            # 再点下一步
            next_btn = wait_for_next_button(d, timeout=5)
            if next_btn:
                next_btn.click()
                logger.info("模板页点击下一步")
            break
        else:
            break

    # 等待发布确认页渲染
    jitter(8, 0.1)
    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.3):
            break
        jitter(0.3)

    # 发布确认页正文
    if publish_body:
        el = d(textContains="添加正文")
        if el.exists(timeout=2):
            el.click(); jitter(0.5)
            d.send_keys(publish_body); jitter(0.5)
            logger.info(f"输入发布确认页正文: {len(publish_body)}字")
        else:
            sw = int(d.info.get('displayHeight', 2400))
            d.click(int(d.info.get('displayWidth', REF_W)) / 2, int(sw * 0.5))
            jitter(0.3)
            d.send_keys(publish_body); jitter(0.3)

    # [新增] 添加商品组件
    if product_name:
        d.swipe(400, 1600, 400, 400, duration=0.2)  # 上滑让页面露出组件区域
        jitter(0.5)
        add_product_component(product_name, d)

    # [修改] 设置可见范围为公开可见
    set_visibility_to_public(d)

    # 发布
    publish_note(d)

    d.app_stop('com.xingin.xhs')
    logger.info("关闭小红书后台")
