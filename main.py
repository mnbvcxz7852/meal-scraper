import os
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def send_line_push(text):
    """發送訊息至指定 LINE 個人或群組"""
    token = os.getenv("LINE_CHANNEL_TOKEN")
    target_id = os.getenv("LINE_TARGET_ID")
    
    if not token or not target_id:
        print("[推播略過] 未設定 LINE_CHANNEL_TOKEN 或 LINE_TARGET_ID")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": target_id,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"[LINE 推播成功] 訊息已發送至群組/用戶 {target_id}")
        else:
            print(f"[LINE 推播失敗] 狀態碼: {res.status_code}, 原因: {res.text}")
    except Exception as e:
        print(f"[LINE 推播異常]: {e}")

def login_eip(driver, username, password):
    """登入 EIP 系統"""
    login_url = "https://eip2.sag.tw/SAGWeb/pages/authentication/login-v1"
    driver.get(login_url)
    time.sleep(3)

    user_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[name*='user'], input[id*='user']")
    if user_inputs:
        user_inputs[0].clear()
        user_inputs[0].send_keys(username)

    pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    if pass_inputs:
        pass_inputs[0].clear()
        pass_inputs[0].send_keys(password)

    buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button, input[type='submit']")
    for btn in buttons:
        if any(w in btn.text for w in ["登入", "Login"]) or btn.get_attribute("type") == "submit":
            btn.click()
            break
    time.sleep(5)

def check_available_noodles(driver):
    """切換至麵食並比對是否有非 0 的剩餘名額"""
    noodle_tabs = driver.find_elements(By.XPATH, "//*[text()='麵食' or contains(text(), '麵食')]")
    for tab in noodle_tabs:
        if tab.is_displayed():
            try:
                driver.execute_script("arguments[0].click();", tab)
            except Exception:
                pass
            break
    time.sleep(2)

    body_text = driver.find_element(By.TAG_NAME, "body").text
    lines = [line.strip() for line in body_text.split("\n") if line.strip()]

    capture = False
    available_list = []
    
    for line in lines:
        if "菜名" in line or "數量" in line:
            capture = True
            continue
        if capture:
            if any(kw in line for kw in ["確定", "送出", "取消", "注意事項", "Copyright", "SAG", "Hand-crafted"]):
                break

            cleaned = line.replace("∞", "").strip()
            match = re.search(r'(\d+)\s*$', cleaned)
            if match:
                quota = int(match.group(1))
                meal_name = cleaned[:match.start()].strip()
                if quota > 0:
                    available_list.append(f"🍜 {meal_name} (剩餘: {quota})")
            else:
                if " 0" not in cleaned and any(char in cleaned for char in ["麵", "粥", "粉"]):
                    available_list.append(f"🍜 {cleaned}")

    return available_list

def main():
    username = os.getenv("EIP_USER")
    password = os.getenv("EIP_PASS")

    if not username or not password:
        print("錯誤：未讀取到帳號密碼，請確認 GitHub Secrets 設定。")
        return

    # 若每 4 小時啟動一次不想被頻繁打擾，可將下面這行開頭加 # 註解掉
    send_line_push("🟢 【訂餐監控系統】已在雲端啟動，開始巡檢麵食退訂名額...")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,800")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # 初次登入
        login_eip(driver, username, password)

        meal_url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"
        print(f"登入成功，開始高頻巡檢: {meal_url}")

       # === 調整為高頻快速巡檢 (間隔 5 秒) ===
        max_checks = 2000          # 因為頻率變快，總次數可以增加以維持總時長
        check_interval = 5         # 每次檢查完休息 5 秒
        last_notified_items = set()

        for i in range(1, max_checks + 1):
            now_str = time.strftime("%H:%M:%S")
            driver.get(meal_url)
            time.sleep(1.5)        # 縮短網頁載入等待

            # 防呆保護：若 Session 逾時被踢回登入頁，自動補登入
            if "login" in driver.current_url.lower():
                print(f"[{now_str}] 偵測到 Session 過期，自動重新登入中...")
                login_eip(driver, username, password)
                driver.get(meal_url)
                time.sleep(1.5)

            # 切換分頁並解析
            noodle_tabs = driver.find_elements(By.XPATH, "//*[text()='麵食' or contains(text(), '麵食')]")
            for tab in noodle_tabs:
                if tab.is_displayed():
                    try:
                        driver.execute_script("arguments[0].click();", tab)
                    except Exception:
                        pass
                    break
            time.sleep(1)          # 縮短切換分頁等待

            available = check_available_noodles(driver)
            current_set = set(available)

            # 偵測到名額且與上次通知名單不同時觸發通知
            if available and current_set != last_notified_items:
                alert_text = (
                    f"【🔥 麵食名額釋出通知！】\n"
                    f"時間：{now_str}\n"
                    f"釋出項目：\n" + "\n".join(available) + "\n\n"
                    f"👉 請盡快開啟網頁訂餐：\n{meal_url}"
                )
                print(alert_text)
                driver.save_screenshot("screenshot_available.png")
                send_line_push(alert_text)
                last_notified_items = current_set
                print("通知已送出，繼續執行後續監控...")

            elif not available:
                # 庫存歸零或被搶光時重置記錄
                last_notified_items = set()
                if i % 10 == 0:
                    print(f"[{now_str}] 第 {i}/{max_checks} 次檢查：暫無名額。")
            else:
                if i % 10 == 0:
                    print(f"[{now_str}] 第 {i}/{max_checks} 次檢查：名額未變更，略過重複推播。")

            time.sleep(check_interval)

    except Exception as e:
        print(f"監控異常: {e}")
        send_line_push(f"⚠️ 訂餐監控異常報錯: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
