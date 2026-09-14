import os
import time
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==================== 🎯 搶單目標設定 ====================
# 當釋出名額符合以下關鍵字時，自動執行搶單！
# 若要「只要釋出任何麵都搶」，可設為 TARGET_KEYWORDS = [""]
TARGET_KEYWORDS = ["牛肉麵", "肉骨茶", "魷魚肉羹", "瘦肉粥"]
# ========================================================

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

def check_and_auto_order(driver, targets, secured_dates):
    """
    掃描名額，符合目標時自動下單。
    具備雙重防重複下單防護：
    1. secured_dates 記憶體比對（已搶到的日期直接跳過）。
    2. DOM 節點底色/狀態比對（若卡片已為亮黃色或顯示吃麵則跳過）。
    """
    # 確保切換至「麵食」分頁
    noodle_tabs = driver.find_elements(By.XPATH, "//*[text()='麵食' or contains(text(), '麵食')]")
    for tab in noodle_tabs:
        if tab.is_displayed():
            try:
                driver.execute_script("arguments[0].click();", tab)
            except Exception:
                pass
            break
    time.sleep(1.2)

    available_meals = []
    success_orders = []

    body_text = driver.find_element(By.TAG_NAME, "body").text
    lines = [line.strip() for line in body_text.split("\n") if line.strip()]

    # 讀取目前釋出的餐點與剩餘數量
    for line in lines:
        cleaned = line.replace("∞", "").strip()
        match = re.search(r'(\d+)\s*$', cleaned)
        if match:
            quota = int(match.group(1))
            meal_name = cleaned[:match.start()].strip()
            if quota > 0 and meal_name:
                available_meals.append((meal_name, quota))

    # 逐一檢查是否執行搶單
    for meal_name, quota in available_meals:
        if any(t in meal_name for t in targets):
            try:
                target_element = driver.find_element(By.XPATH, f"//*[contains(text(), '{meal_name}')]")
                container = target_element.find_element(
                    By.XPATH, 
                    "./ancestor::div[contains(@class, 'card') or contains(@class, 'panel') or contains(@style, 'pink') or preceding-sibling::div]"
                )

                # 提取區塊內的日期文字（例如 09-23）
                container_text = container.text
                date_match = re.search(r'(\d{2}-\d{2})', container_text)
                date_key = date_match.group(1) if date_match else meal_name

                # 防護 1：若該日期已記錄在搶單成功名單中，跳過
                if date_key in secured_dates:
                    continue

                # 防護 2：檢查 UI 樣式是否已經呈現亮黃色或已選中（避免多次扣名額）
                container_style = (container.get_attribute("style") or "").lower()
                container_class = (container.get_attribute("class") or "").lower()
                if "yellow" in container_style or "rgb(255, 255" in container_style or "吃麵" in container_text:
                    secured_dates.add(date_key)
                    continue

                print(f"🎯 鎖定目標釋出：{meal_name} (剩餘 {quota})，開始下單...")

                # 點擊該卡片右側的第 3 個圖示（麵碗）
                icons = container.find_elements(By.XPATH, ".//img | .//*[name()='svg'] | .//i")
                if icons:
                    driver.execute_script("arguments[0].click();", icons[-1])
                else:
                    driver.execute_script("arguments[0].click();", target_element)

                time.sleep(0.8)

                # 點擊彈窗上的「Accept」確認鈕
                accept_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), '確定')]")
                for abtn in accept_btns:
                    if abtn.is_displayed():
                        driver.execute_script("arguments[0].click();", abtn)
                        break

                # 等待並讀取右上角 Toast 結果
                time.sleep(1.2)
                page_after = driver.find_element(By.TAG_NAME, "body").text

                if "數量不足" in page_after:
                    print(f"❌ 搶單失敗：{meal_name} 數量已被搶先扣光！")
                elif "吃麵" in page_after:
                    print(f"🎉 搶單成功！右上角已確認跳出吃麵通知：{meal_name}")
                    secured_dates.add(date_key)
                    success_orders.append(meal_name)
                else:
                    # 寬鬆判定：若無數量不足且流程完成，標記為成功避免重複點擊
                    print(f"⚠️ 未明確捕捉到 Toast，但已完成 Accept 動作：{meal_name}")
                    secured_dates.add(date_key)
                    success_orders.append(meal_name)

            except Exception as e:
                print(f"搶單點擊流程發生例外: {e}")

    return available_meals, success_orders

def main():
    username = os.getenv("EIP_USER")
    password = os.getenv("EIP_PASS")

    if not username or not password:
        print("錯誤：未讀取到帳號密碼，請確認 GitHub Secrets 設定。")
        return

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
        login_eip(driver, username, password)

        meal_url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"
        print(f"登入成功，開始自動搶單巡檢: {meal_url}")

        max_checks = 1600
        check_interval = 5
        last_notified_items = set()
        secured_dates = set()  # 存放已搶到成功的日期（如 "09-23"），避免重複點擊

        for i in range(1, max_checks + 1):
            now_str = time.strftime("%H:%M:%S")
            driver.get(meal_url)
            time.sleep(1.5)

            # Session 逾時保護
            if "login" in driver.current_url.lower():
                print(f"[{now_str}] 偵測到 Session 過期，自動重新登入中...")
                login_eip(driver, username, password)
                driver.get(meal_url)
                time.sleep(1.5)

            available_meals, success_orders = check_and_auto_order(driver, TARGET_KEYWORDS, secured_dates)

            # 搶單成功推播
            if success_orders:
                success_text = (
                    f"🎉 【⚡ 搶單成功通知！】\n"
                    f"時間：{now_str}\n"
                    f"已為您自動選取搶下：\n" + "\n".join([f"🍜 {m}" for m in success_orders]) + "\n\n"
                    f"👉 請開啟系統確認訂單：\n{meal_url}"
                )
                print(success_text)
                send_line_push(success_text)

            # 一般釋出名額推播（名單改變時通知，防止洗版）
            available_desc = [f"🍜 {m} (剩餘: {q})" for m, q in available_meals]
            current_set = set(available_desc)

            if available_desc and current_set != last_notified_items:
                alert_text = (
                    f"【🔥 麵食名額釋出通知！】\n"
                    f"時間：{now_str}\n"
                    f"釋出項目：\n" + "\n".join(available_desc) + "\n\n"
                    f"👉 訂餐連結：\n{meal_url}"
                )
                print(alert_text)
                send_line_push(alert_text)
                last_notified_items = current_set

            elif not available_desc:
                last_notified_items = set()
                if i % 10 == 0:
                    print(f"[{now_str}] 第 {i}/{max_checks} 次檢查：暫無名額。")
            else:
                if i % 10 == 0:
                    print(f"[{now_str}] 第 {i}/{max_checks} 次檢查：名額未變更。")

            time.sleep(check_interval)

    except Exception as e:
        print(f"監控異常: {e}")
        send_line_push(f"⚠️ 訂餐搶單腳本異常: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
