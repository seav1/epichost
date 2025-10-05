import os
import time
from playwright.sync_api import sync_playwright, Cookie, TimeoutError as PlaywrightTimeoutError

def handle_consent_popup(page, timeout=10000):
    """
    处理 Cookie 同意弹窗
    """
    try:
        consent_button_selector = 'button.fc-cta-consent.fc-primary-button'
        print("检查是否有 Cookie 同意弹窗...")
        page.wait_for_selector(consent_button_selector, state='visible', timeout=timeout)
        print("发现 Cookie 同意弹窗，正在点击'同意'按钮...")
        page.click(consent_button_selector)
        print("已点击'同意'按钮。")
        time.sleep(2)
        return True
    except Exception:
        print("未发现 Cookie 同意弹窗或已处理过")
        return False

def safe_goto(page, url, wait_until="domcontentloaded", timeout=90000):
    """
    安全的页面导航,带重试机制
    """
    max_retries = 2
    for attempt in range(max_retries):
        try:
            print(f"正在访问: {url} (尝试 {attempt + 1}/{max_retries})")
            page.goto(url, wait_until=wait_until, timeout=timeout)
            print(f"页面加载成功: {page.url}")
            handle_consent_popup(page, timeout=5000)
            return True
        except PlaywrightTimeoutError:
            print(f"页面加载超时 (尝试 {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                print("等待 5 秒后重试...")
                time.sleep(5)
            else:
                print("达到最大重试次数")
                return False
        except Exception as e:
            print(f"页面导航出错: {e}")
            return False
    return False

def parse_cookies_from_env(cookie_string):
    """
    从环境变量中解析 cookie 字符串
    格式: "name1=value1; name2=value2"
    """
    cookies = []
    if not cookie_string:
        return cookies
    cookie_pairs = cookie_string.split('; ')
    for pair in cookie_pairs:
        if '=' in pair:
            name, value = pair.split('=', 1)
            cookies.append({
                'name': name.strip(),
                'value': value.strip(),
                'domain': '.epichost.pl',
                'path': '/',
                'expires': time.time() + 3600 * 24 * 365,
                'httpOnly': True,
                'secure': True,
                'sameSite': 'Lax'
            })
    return cookies

def add_server_time(server_url="https://panel.epichost.pl/server/f7f7d38a"):
    """
    尝试登录 epichost.pl 并点击 "ADD 8 HOUR(S)" 按钮。
    优先使用 REMEMBER_WEB_COOKIE，会话失败则回退邮箱密码登录。
    """
    remember_web_cookie = os.environ.get('REMEMBER_WEB_COOKIE')
    login_email = os.environ.get('LOGIN_EMAIL')
    login_password = os.environ.get('LOGIN_PASSWORD')

    if not (remember_web_cookie or (login_email and login_password)):
        print("错误: 缺少登录凭据。请设置 REMEMBER_WEB_COOKIE 或 LOGIN_EMAIL 和 LOGIN_PASSWORD 环境变量。")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        try:
            # --- 优先使用 cookie 登录 ---
            if remember_web_cookie:
                print("尝试使用 REMEMBER_WEB_COOKIE 会话登录...")
                cookies = parse_cookies_from_env(remember_web_cookie)
                if cookies:
                    context.add_cookies(cookies)
                    print(f"已设置 {len(cookies)} 个 cookies。正在访问 {server_url}")
                    if not safe_goto(page, server_url):
                        print("使用 REMEMBER_WEB_COOKIE 访问失败。")
                        remember_web_cookie = None
                    else:
                        time.sleep(3)
                        if "login" in page.url or "auth" in page.url:
                            print("REMEMBER_WEB_COOKIE 无效，尝试邮箱密码登录。")
                            context.clear_cookies()
                            remember_web_cookie = None
                        else:
                            print("REMEMBER_WEB_COOKIE 登录成功。")

            # --- 邮箱密码登录 ---
            if not remember_web_cookie:
                if not (login_email and login_password):
                    print("错误: REMEMBER_WEB_COOKIE 无效，且未提供邮箱密码。")
                    return False

                login_url = "https://epichost.pl/auth/login"
                if not safe_goto(page, login_url):
                    print("访问登录页失败。")
                    page.screenshot(path="login_page_load_fail.png")
                    return False

                page.fill('input[name="email"]', login_email)
                page.fill('input[name="password"]', login_password)
                page.click('button[type="submit"]')

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=60000)
                    time.sleep(3)
                    if "login" in page.url or "auth" in page.url:
                        print("邮箱密码登录失败。")
                        page.screenshot(path="login_fail.png")
                        return False
                    else:
                        print("邮箱密码登录成功。")
                        if page.url != server_url:
                            if not safe_goto(page, server_url):
                                print("导航到服务器页面失败。")
                                return False
                except Exception as e:
                    print(f"登录后处理失败: {e}")
                    page.screenshot(path="post_login_error.png")
                    return False

            # --- 已经进入服务器页面 ---
            print(f"当前页面URL: {page.url}")
            time.sleep(3)
            page.screenshot(path="step1_page_loaded.png")

            # --- 查找并点击 ADD 8 HOUR(S) 按钮 ---
            add_button_selector = 'button:has-text("ADD 8 HOUR(S)"), a:has-text("ADD 8 HOUR(S)"), [role="button"]:has-text("ADD 8 HOUR(S)")'
            print("正在查找 'ADD 8 HOUR(S)' 按钮...")

            try:
                page.wait_for_selector(add_button_selector, timeout=30000)
                button = page.query_selector(add_button_selector)

                if not button:
                    print("按钮查询失败。")
                    page.screenshot(path="extend_button_not_found.png")
                    return False

                # ⚡ 修正点：检查 class 属性是否包含 disabled
                button_class = button.get_attribute("class") or ""
                print(f"按钮 class 属性: {button_class}")

                if "disabled" in button_class:
                    print("按钮已禁用，无需续期。")
                    return True

                print("按钮可点击，正在点击...")
                button.click()
                print("成功点击 'ADD 8 HOUR(S)' 按钮，已续期。")
                time.sleep(5)
                return True

            except Exception as e:
                print(f"操作过程中发生错误: {e}")
                page.screenshot(path="extend_button_error.png")
                return False

        except Exception as e:
            print(f"执行过程中发生未知错误: {e}")
            try:
                page.screenshot(path="general_error.png")
            except:
                pass
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    print("开始执行添加服务器时间任务...")
    success = add_server_time()
    if success:
        print("任务执行成功。")
        exit(0)
    else:
        print("任务执行失败。")
        exit(1)
