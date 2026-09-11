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

    # 設定無頭 Chrome (完全在背景執行)
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
        # 1. 前往登入頁
        login_url = "https://eip2.sag.tw/SAGWeb/pages/authentication/login-v1"
        print(f"前往登入頁: {login_url}")
        driver.get(login_url)
        time.sleep(3)

        # 2. 自動尋找帳號、密碼欄位並輸入
        print("正在輸入帳號密碼...")
        user_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[name*='user'], input[id*='user']")
        if user_inputs:
            user_inputs[0].send_keys(username)

        pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if pass_inputs:
            pass_inputs[0].send_keys(password)

        # 3. 點擊登入按鈕
        print("點擊登入按鈕...")
        buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button, input[type='submit']")
        for btn in buttons:
            txt = btn.text.strip()
            if "登入" in txt or "Login" in txt or btn.get_attribute("type") == "submit":
                btn.click()
                break

        time.sleep(5)

        # 4. 前往點餐頁面
        meal_url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"
        print(f"前往點餐系統: {meal_url}")
        driver.get(meal_url)
        time.sleep(5)

        print(f"當前停留網址: {driver.current_url}")

        # 5. 儲存截圖
        driver.save_screenshot("screenshot_meal.png")
        print("已成功儲存畫面截圖: screenshot_meal.png")

        # 6. 印出畫面文字
        body_text = driver.find_element(By.TAG_NAME, "body").text
        print("【點餐頁面文字預覽】：")
        print(body_text[:500])

    except Exception as e:
        print(f"執行過程發生異常: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
