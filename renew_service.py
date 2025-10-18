import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 全局配置 ---
HIDENCLOUD_COOKIE = os.environ.get('HIDENCLOUD_COOKIE')
HIDENCLOUD_EMAIL = os.environ.get('HIDENCLOUD_EMAIL')
HIDENCLOUD_PASSWORD = os.environ.get('HIDENCLOUD_PASSWORD')

# 目标网页 URL
BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"
SERVICE_URL = f"{BASE_URL}/service/71309/manage"

# Cookie 名称
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"

def log(message):
    """打印带时间戳的日志"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def login(page):
    """
    处理登录逻辑。
    1. 优先尝试使用 Cookie 登录。
    2. 如果 Cookie 失效或不存在，则使用账号密码进行登录。
    """
    log("开始登录流程...")

    # --- 方案一：Cookie 登录 ---
    if HIDENCLOUD_COOKIE:
        log("检测到 HIDENCLOUD_COOKIE，尝试使用 Cookie 登录。")
        try:
            page.context.add_cookies([{
                'name': COOKIE_NAME, 'value': HIDENCLOUD_COOKIE,
                'domain': 'dash.hidencloud.com', 'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365,
                'httpOnly': True, 'secure': True, 'sameSite': 'Lax'
            }])
            log("Cookie 已设置。正在访问服务管理页面...")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)

            if "auth/login" in page.url:
                log("Cookie 登录失败或会话已过期，将回退到账号密码登录。")
                page.context.clear_cookies()
            else:
                log("✅ Cookie 登录成功！")
                return True
        except Exception as e:
            log(f"使用 Cookie 访问时发生错误: {e}")
            log("将回退到账号密码登录。")
            page.context.clear_cookies()
    else:
        log("未提供 HIDENCLOUD_COOKIE，直接使用账号密码登录。")

    # --- 方案二：账号密码登录 ---
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        log("❌ 错误: Cookie 无效/未提供，且未提供邮箱和密码。无法继续登录。")
        return False

    log("正在尝试使用邮箱和密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        log("登录页面已加载。")

        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        log("邮箱和密码已填写。")

        log("正在处理 Cloudflare Turnstile 人机验证...")
        turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        checkbox = turnstile_frame.locator('input[type="checkbox"]')
        
        checkbox.wait_for(state="visible", timeout=30000)
        checkbox.click()
        log("已点击人机验证复选框，等待验证结果...")
        
        page.wait_for_function(
            "() => document.querySelector('[name=\"cf-turnstile-response\"]') && document.querySelector('[name=\"cf-turnstile-response\"]').value",
            timeout=60000
        )
        log("✅ 人机验证成功！")

        page.click('button[type="submit"]:has-text("Sign in to your account")')
        log("已点击登录按钮，等待页面跳转...")

        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=60000)

        if "auth/login" in page.url:
            log("❌ 账号密码登录失败，请检查凭据是否正确。")
            page.screenshot(path="login_failure.png")
            return False

        log("✅ 账号密码登录成功！")
        return True
    except PlaywrightTimeoutError as e:
        log(f"❌ 登录过程中超时: {e}")
        page.screenshot(path="login_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ 登录过程中发生未知错误: {e}")
        page.screenshot(path="login_general_error.png")
        return False

def renew_service(page):
    """执行续费流程"""
    try:
        log("开始执行续费任务...")
        if page.url != SERVICE_URL:
            log(f"当前不在目标页面，正在导航至: {SERVICE_URL}")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
        
        log("服务管理页面已加载。")

        log("步骤 1: 正在查找并点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")')
        renew_button.wait_for(state="visible", timeout=30000)
        renew_button.click()
        log("✅ 'Renew' 按钮已点击。")
        
        # --- 等待 0.9 秒 ---
        log("等待 0.9 秒...")
        time.sleep(0.9)

        # +++ 解决方案：(方案十一) 模拟物理鼠标坐标点击 +++
        log("步骤 2: 正在查找 'Create Invoice' 按钮...")
        create_invoice_button = page.locator('button:has-text("Create Invoice")')
        
        create_invoice_button.wait_for(state="visible", timeout=30000)
        
        log("✅ 'Create Invoice' 按钮已可见，正在获取其坐标...")
        
        # 1. 获取按钮的边界框 (x, y, width, height)
        box = create_invoice_button.bounding_box()
        if not box:
            log("❌ 错误：无法获取 'Create Invoice' 按钮的坐标。")
            raise Exception("Failed to get bounding box for 'Create Invoice' button.")
            
        # 2. 计算按钮中心点
        center_x = box['x'] + box['width'] / 2
        center_y = box['y'] + box['height'] / 2
        
        log(f"按钮中心坐标为: X={center_x}, Y={center_y}。模拟物理鼠标移动并点击...")
        
        # 3. 模拟鼠标移动到中心点
        page.mouse.move(center_x, center_y, steps=5) # steps=5 模拟一个平滑移动
        page.wait_for_timeout(100) # 暂停
        
        # 4. 模拟物理点击 (按下 -> 抬起)
        page.mouse.click(center_x, center_y, delay=60)
        
        log("按钮已点击 (物理模拟)。正在等待发票页面内容加载...")
        
        # 5. 等待结果：我们仍然等待页面上的关键内容
        try:
            success_message_locator = page.locator(':text-matches("Success! Invoice")')
            success_message_locator.wait_for(state="visible", timeout=30000)
            
            log(f"🎉 成功跳转到发票页面 (检测到Success消息)。")
            log(f"当前 URL: {page.url}")
            
        except PlaywrightTimeoutError:
            log("❌ 错误：点击 'Create Invoice' 后，未在30秒内检测到 'Success!' 消息。")
            page.screenshot(path="invoice_content_timeout.png")
            raise Exception("Failed to find success message after clicking 'Create Invoice'.")
        
        # +++ 步骤 3：在 *当前* 发票页面上操作 +++
        log("步骤 3: 正在查找可见的 'Pay' 按钮...")
        
        pay_button = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_button.wait_for(state="visible", timeout=10000) 
        
        log("✅ 'Pay' 按钮已找到，正在点击...")
        pay_button.click() # Pay 按钮通常不会有这么强的反制
        log("✅ 'Pay' 按钮已点击。")
        
        time.sleep(5)
        log("续费流程似乎已成功触发。请登录网站确认续费状态。")
        page.screenshot(path="renew_success.png")
        
        return True
    
    except PlaywrightTimeoutError as e:
        log(f"❌ <b>续费任务超时:</b> 未在规定时间内找到元素。请检查选择器或页面是否已更改。错误: {e}")
        page.screenshot(path="renew_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ <b>续费任务执行过程中发生未知错误:</b> {e}")
        page.screenshot(path="renew_general_error.png")
        return False

def main():
    """主函数，编排整个自动化流程"""
    if not HIDENCLOUD_COOKIE and not (HIDENCLOUD_EMAIL and HIDENCLOUD_PASSWORD):
        log("❌ 致命错误: 必须提供 HIDENCLOUD_COOKIE 或 (HIDENCLOUD_EMAIL 和 HIDENCLOUD_PASSWORD) 环境变量。")
        sys.exit(1)

    with sync_playwright() as p:
        browser = None
        try:
            log("启动浏览器...")
            # 添加启动参数以规避检测
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            if not login(page):
                log("登录失败，程序终止。")
                sys.exit(1)

            if not renew_service(page):
                log("续费失败，程序终止。")
                # +++ 语法错误修复 +++
                sys.exit(1) # <--- 这里之前是 'sys.exit。'

            log("🎉🎉🎉 自动化续费任务成功完成！ 🎉🎉🎉")
        except Exception as e:
            log(f"💥 主程序发生严重错误: {e}")
            if 'page' in locals() and page:
                page.screenshot(path="main
