import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def main():
    username = os.getenv("EIP_USER")
    password = os.getenv("EIP_PASS")

    if not username or not password:
        print("錯誤：未讀取到 EIP_USER 或 EIP_PASS，請確認 GitHub Secrets 設定。")
        return

    # 設定無頭 Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,800")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # 1. 前往登入頁面
        login_url = "https://eip2.sag.tw/SAGWeb/pages/authentication/login-v1"
        print("正在前往登入頁面...")
        driver.get(login_url)
        time.sleep(3)

        # 2. 自動輸入帳號密碼
        user_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[name*='user'], input[id*='user']")
        if user_inputs:
            user_inputs[0].send_keys(username)

        pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if pass_inputs:
            pass_inputs[0].send_keys(password)

        # 3. 點擊登入
        buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button, input[type='submit']")
        for btn in buttons:
            txt = btn.text.strip()
            if "登入" in txt or "Login" in txt or btn.get_attribute("type") == "submit":
                btn.click()
                break

        time.sleep(5)

        # 4. 前往訂餐頁面
        meal_url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"
        print("前往訂餐頁面...")
        driver.get(meal_url)
        time.sleep(4)

        # 5. 點擊「麵食」標籤/按鈕
        print("嘗試切換至【麵食】...")
        # 尋找包含「麵食」文字的元素 (可能是 div, a, span, button 等)
        noodle_tabs = driver.find_elements(By.XPATH, "//*[text()='麵食' or contains(text(), '麵食')]")
        clicked = False
        for tab in noodle_tabs:
            if tab.is_displayed():
                try:
                    tab.click()
                    clicked = True
                    print("已點擊【麵食】分頁")
                    break
                except Exception:
                    # 若被其他元素阻擋，改用 JavaScript 直接觸發點擊
                    driver.execute_script("arguments[0].click();", tab)
                    clicked = True
                    print("透過 JS 點擊【麵食】分頁")
                    break

        if not clicked:
            print("警告：未找到【麵食】分頁按鈕，將讀取當前預設內容")

        time.sleep(3)

        # 6. 截圖存檔 (驗證是否成功切到麵食)
        driver.save_screenshot("screenshot_noodle.png")

        # 7. 取得並解析畫面文字
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in body_text.split("\n") if line.strip()]

        print("\n" + "="*40)
        print("           【 今日麵食餐點 】")
        print("="*40)

        # 擷取「菜名」或「數量」之後出現的項目
        noodle_items = []
        capture = False
        for line in lines:
            if "菜名" in line or "數量" in line:
                capture = True
                continue
            if capture:
                # 排除可能出現的頁尾或按鈕文字
                if any(kw in line for kw in ["確定", "送出", "取消", "注意事項", "Copyright", "SAG"]):
                    break
                # 去除特殊符號
                cleaned = line.replace("∞", "").strip()
                if cleaned and not cleaned.isdigit():
                    noodle_items.append(cleaned)

        if noodle_items:
            for idx, item in enumerate(noodle_items, 1):
                print(f"{idx}. {item}")
        else:
            print("未找到菜單清單，完整文字預覽如下：")
            print("\n".join(lines[25:50]))
        print("="*40 + "\n")

    except Exception as e:
        print(f"執行異常: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
