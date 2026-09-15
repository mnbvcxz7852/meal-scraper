import os
import time
import re
import requests
from datetime import datetime, timezone, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 台灣時區 (UTC+8)
TAIPEI_TZ = timezone(timedelta(hours=8))

# ==================== 🎯 搶單目標設定 ====================
# 1. 菜名關鍵字：設為 [""] 代表「只要是麵食通殺全部搶」
TARGET_KEYWORDS = [""]

# 2. 允許搶單的日期白名單（只鎖定目標日期，其餘日期有名額也一律跳過不搶）
ALLOWED_DATES = ["10-05", "10-06", "10-07", "10-08", "10-09"]
# ========================================================

def send_discord_push(text):
    """發送訊息至 Discord Webhook 頻道"""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        print("[Discord略過] 未設定 DISCORD_WEBHOOK_URL")
        return

    payload = {
        "content": text
    }
    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        if res.status_code in [200, 204]:
            print("[Discord 推播成功] 訊息已發送至頻道")
        else:
            print(f"[Discord 推播失敗] 狀態碼: {res.status_code}, 原因: {res.text}")
    except Exception as e:
        print(f"[Discord 推播異常]: {e}")

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

def check_and_auto_order(driver, targets, allowed_dates, secured_dates):
    """
    精確透過日期與麵碗按鈕搶單，具備日期白名單保護
    """
    noodle_tabs = driver.find_elements(By.XPATH, "//*[text()='麵食' or contains(text(), '麵食')]")
    for tab in noodle_tabs:
        if tab.is_displayed():
            try:
                driver.execute_script("arguments[0].click();", tab)
            except Exception:
                pass
            break
    time.sleep(1.2)

    body_text = driver.find_element(By.TAG_NAME, "body").text
    lines = [line.strip() for line in body_text.split("\n") if line.strip()]

    current_date = ""
    parsed_items = []
    available_meals = []
    success_orders = []

    for line in lines:
        cleaned = line.replace("∞", "").strip()
        
        date_match = re.search(r'(\d{2}-\d{2})\s*[一二三四五]', cleaned)
        if date_match:
            current_date = date_match.group(1)
            continue

        match = re.search(r'(\d+)\s*$', cleaned)
        if match:
            quota = int(match.group(1))
            meal_name = cleaned[:match.start()].strip()
            if meal_name:
                parsed_items.append((current_date, meal_name, quota))
                if quota > 0:
                    available_meals.append((f"{current_date} {meal_name}", quota))

    for date_str, meal_name, quota in parsed_items:
        if quota <= 0:
            continue

        if allowed_dates and not any(allowed in date_str for allowed in allowed_dates):
            continue

        if not any(t in meal_name for t in targets):
            continue

        target_date_key = date_str if date_str else meal_name
        print(f"\n[搶單觸發] 🎯 鎖定：{target_date_key} {meal_name} (名額: {quota})")

        if target_date_key in secured_dates:
            print(f"[搶單略過] ⏩ {target_date_key} 已經成功搶過，跳過。")
            continue

        clicked_bowl = False

        # 策略 A
        try:
            date_rows = driver.find_elements(By.XPATH, f"//*[contains(text(), '{date_str}')]")
            for d_elem in date_rows:
                row_container = d_elem.find_element(
                    By.XPATH, 
                    "./ancestor::div[contains(@class, 'card-header') or contains(@class, 'header') or contains(@style, 'pink') or count(.//button | .//svg | .//img) >= 3][1]"
                )
                clickables = row_container.find_elements(By.XPATH, ".//button | .//*[name()='svg'] | .//img | .//i | .//span[contains(@class, 'btn')]")
                
                if len(clickables) >= 3:
                    noodle_icon = clickables[2]
                    driver.execute_script("arguments[0].click();", noodle_icon)
                    print(f"[點擊成功] 👉 已點擊 {date_str} 的麵碗按鈕")
                    clicked_bowl = True
                    break
        except Exception as e1:
            print(f"[策略A未命中]: {e1}")

        # 策略 B
        if not clicked_bowl and date_str:
            try:
                noodle_icon = driver.find_element(
                    By.XPATH, 
                    f"(//*[contains(text(), '{date_str}')]/following::*[(self::button or self::img or name()='svg') and not(contains(@class, 'arrow'))])[3]"
                )
                driver.execute_script("arguments[0].click();", noodle_icon)
                print(f"[點擊成功-策略B] 👉 已點擊 {date_str} 後方之麵碗")
                clicked_bowl = True
            except Exception as e2:
                print(f"[策略B未命中]: {e2}")

        if not clicked_bowl:
            print(f"[錯誤] ❌ 無法定位到 {date_str} 的麵碗按鈕。")
            continue

        time.sleep(0.8)

        # 點擊 Accept
        try:
            accept_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), '確定')]")
            clicked_accept = False
            for abtn in accept_btns:
                if abtn.is_displayed():
                    driver.execute_script("arguments[0].click();", abtn)
                    print("[點擊成功] 👉 已點擊彈窗【Accept】按鈕")
                    clicked_accept = True
                    break

            if not clicked_accept:
                print("[錯誤] ❌ 彈跳視窗未跳出或找不到 Accept 按鈕！")
                continue

            time.sleep(1.2)
            page_after = driver.find_element(By.TAG_NAME, "body").text

            if "數量不足" in page_after:
                print(f"❌ 搶單失敗：{date_str} {meal_name} 名額已被搶走。")
            elif "吃麵" in page_after:
                print(f"🎉 搶單成功！右上角確認顯示吃麵：{date_str} {meal_name}")
                secured_dates.add(target_date_key)
                success_orders.append(f"{date_str} {meal_name}")
            else:
                print(f"⚠️ 動作已執行完畢：{date_str} {meal_name}")
                secured_dates.add(target_date_key)
                success_orders.append(f"{date_str} {meal_name}")

        except Exception as e:
            print(f"[下單流程異常]: {e}")

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
        secured_dates = set()

        for i in range(1, max_checks + 1):
            now_str = datetime.now(TAIPEI_TZ).strftime("%H:%M:%S")
            driver.get(meal_url)
            time.sleep(1.5)

            if "login" in driver.current_url.lower():
                print(f"[{now_str}] 偵測到 Session 過期，自動重新登入中...")
                login_eip(driver, username, password)
                driver.get(meal_url)
                time.sleep(1.5)

            available_meals, success_orders = check_and_auto_order(driver, TARGET_KEYWORDS, ALLOWED_DATES, secured_dates)

            # 搶單成功推播
            if success_orders:
                success_text = (
                    f"🎉 **【⚡ 搶單成功通知！】**\n"
                    f"時間：`{now_str}`\n"
                    f"已為您自動選取搶下：\n" + "\n".join([f"> 🍜 **{m}**" for m in success_orders]) + "\n\n"
                    f"👉 [點此開啟系統確認訂單]({meal_url})"
                )
                print(success_text)
                send_discord_push(success_text)

            # 常規名額變動推播
            available_desc = [f"🍜 {m} (剩餘: {q})" for m, q in available_meals]
            current_set = set(available_desc)

            if available_desc and current_set != last_notified_items:
                alert_text = (
                    f"🔥 **【麵食名額釋出通知！】**\n"
                    f"時間：`{now_str}`\n"
                    f"釋出項目：\n" + "\n".join([f"> {item}" for item in available_desc]) + "\n\n"
                    f"👉 [點此開啟訂餐連結]({meal_url})"
                )
                print(alert_text)
                send_discord_push(alert_text)
                last_notified_items = current_set

            elif not available_desc:
                if i % 10 == 0:
                    print(f"[{now_str}] 第 {i}/{max_checks} 次檢查：暫無名額。")
            else:
                if i % 10 == 0:
                    print(f"[{now_str}] 第 {i}/{max_checks} 次檢查：名額未變更。")

            time.sleep(check_interval)

    except Exception as e:
        print(f"監控異常: {e}")
        send_discord_push(f"⚠️ **訂餐搶單腳本異常**: `{e}`")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
