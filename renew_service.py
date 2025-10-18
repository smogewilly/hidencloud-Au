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

        # +++ 解决方案：处理新标签页 (New Tab) 导航 +++
        log("步骤 2: 正在查找 'Create Invoice' 按钮...")
        create_invoice_button = page.locator('button:has-text("Create Invoice")')
        create_invoice_button.wait_for(state="visible", timeout=30000)
        
        log("✅ 'Create Invoice' 按钮已找到，正在点击并等待新标签页打开...")

        # 核心修改：
        # 1. 在点击前，准备 "监听" new page 事件
        # 2. page.context.expect_page() 会返回一个 "PageEventInfo"
        try:
            with page.context.expect_page() as new_page_info:
                create_invoice_button.click()  # 点击操作会触发新页面
            
            # 3. 从 PageEventInfo 中获取新的 page 对象
            invoice_page = new_page_info.value
            log(f"🎉 成功在新的标签页中打开页面: {invoice_page.url}")

        except PlaywrightTimeoutError:
            log("❌ 错误：点击 'Create Invoice' 后，没有新的标签页弹出。")
            page.screenshot(path="invoice_new_tab_timeout.png")
            raise Exception("Failed to open new tab after clicking 'Create Invoice'.")

        # 4. (重要) 等待新页面加载完成并验证URL
        try:
            # 等待新标签页的URL变为发票URL
            invoice_page.wait_for_url(
                "**/payment/invoice/**", 
                timeout=30000, 
                wait_until="networkidle"
            )
            log(f"✅ 新的发票页面已加载: {invoice_page.url}")
        except PlaywrightTimeoutError:
            log("❌ 错误：新标签页已打开，但 URL 不是预期的发票页面，或加载超时。")
            invoice_page.screenshot(path="invoice_page_wrong_url.png")
            raise Exception("New tab opened, but it was not the expected invoice page URL.")
        
        # +++ 步骤 3：在新的发票页面上操作 +++
        log("步骤 3: 正在查找可见的 'Pay' 按钮...")
        
        # 关键: 必须在新的 'invoice_page' 上查找按钮，而不是在旧的 'page' 上
        pay_button = invoice_page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_button.wait_for(state="visible", timeout=10000) 
        
        log("✅ 'Pay' 按钮已找到，正在点击...")
        pay_button.click()
        log("✅ 'Pay' 按钮已点击。")
        
        time.sleep(5)
        log("续费流程似乎已成功触发。请登录网站确认续费状态。")
        
        # 截取新页面的成功截图
        invoice_page.screenshot(path="renew_success.png")
        
        # 别忘了关闭新打开的页面
        invoice_page.close()
        
        return True
    
    except PlaywrightTimeoutError as e:
        log(f"❌ 续费任务超时: 未在规定时间内找到元素。请检查选择器或页面是否已更改。错误: {e}")
        page.screenshot(path="renew_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ 续费任务执行过程中发生未知错误: {e}")
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
                sys.exit(1)

            log("🎉🎉🎉 自动化续费任务成功完成！ 🎉🎉🎉")
        except Exception as e:
            log(f"💥 主程序发生严重错误: {e}")
            if 'page' in locals() and page:
                page.screenshot(path="main_critical_error.png")
            sys.exit(1)
        finally:
            log("关闭浏览器。")
            if browser:
                browser.close()

if __name__ == "__main__":
    main()
