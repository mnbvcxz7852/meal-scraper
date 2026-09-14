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
    精確定位日期卡片並執行搶單
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

    # 1. 抓取畫面上所有的日期標題區塊（包含 09-XX 的元素）
    # 透過日期元素向上鎖定整張卡片
    date_headers = driver.find_elements(By.XPATH, "//*[re:test(text(), '^\d{2}-\d{2}')]" if hasattr(re, 'test') else "//*[contains(text(), '09-')]")
    
    # 備用尋找卡片方式：尋找包含「菜名」與「數量」的獨立區塊
    cards = driver.find_elements(By.XPATH, "//div[contains(@class, 'card') or contains(@class, 'panel') or contains(@class, 'collapse') or .//table or contains(@style, 'pink')]")
    # 若篩選過少，抓取含有日期標題的所有容器
    valid_blocks = []
    for c in cards:
        txt = c.text
        if any(f"09-{d:02d}" in txt for d in range(1, 32)) and ("數量" in txt or "菜名" in txt):
            valid_blocks.append(c)

    # 讀取全頁以建立名額清單
    body_text = driver.find_element(By.TAG_NAME, "body").text
    lines = [line.strip() for line in body_text.split("\n") if line.strip()]
    for line in lines:
        cleaned = line.replace("∞", "").strip()
        match = re.search(r'(\d+)\s*$', cleaned)
        if match:
            quota = int(match.group(1))
            meal_name = cleaned[:match.start()].strip()
            if quota > 0 and meal_name:
                available_meals.append((meal_name, quota))

    # 2. 針對有名額的項目進行卡片定位搶單
    for meal_name, quota in available_meals:
        # 比對目標關鍵字
        if not any(t in meal_name for t in targets):
            continue

        print(f"🎯 偵測到目標品項有名額：{meal_name} (剩餘 {quota})")

        # 尋找包含此 meal_name 的卡片容器
        matched_block = None
        for blk in valid_blocks:
            if meal_name in blk.text:
                matched_block = blk
                break

        # 如果找不到明確 block，直接以 meal_name 向上抓取 5 層容器
        if not matched_block:
            try:
                elem = driver.find_element(By.XPATH, f"//*[contains(text(), '{meal_name}')]")
                matched_block = elem.find_element(By.XPATH, "./ancestor::div[contains(., '09-')][1]")
            except Exception:
                pass

        if not matched_block:
            print(f"⚠️ 無法鎖定 {meal_name} 所屬的日期卡片區塊，略過此項。")
            continue

        block_text = matched_block.text
        date_match = re.search(r'(\d{2}-\d{2})', block_text)
        date_key = date_match.group(1) if date_match else meal_name

        # 檢查防重複機制
        if date_key in secured_dates:
            print(f"⏩ {date_key} 已在搶單成功清單中，跳過。")
            continue

        if "吃麵" in block_text:
            print(f"⏩ {date_key} 畫面上已是「吃麵」狀態，標記並跳過。")
            secured_dates.add(date_key)
            continue

        print(f"⚡ 開始執行點擊搶單流程：{date_key} -> {meal_name}")

        try:
            # 尋找該區塊內右側的「麵碗」按鈕（通常為第三個圖示，或圖片/SVG/i 標籤）
            clickable_icons = matched_block.find_elements(By.XPATH, ".//img | .//*[name()='svg'] | .//i | .//span[contains(@class, 'icon')]")
            
            # 從找到的圖示中，選取最右邊的那個（依截圖，右側圖示由左至右為 肉、菜、麵）
            noodle_button = None
            if len(clickable_icons) >= 3:
                # 排除可能包含的收合箭頭，取倒數第二或第三個，優先測試最接近右側的圖標
                noodle_button = clickable_icons[2]
            elif clickable_icons:
                noodle_button = clickable_icons[-1]

            if noodle_button:
                driver.execute_script("arguments[0].click();", noodle_button)
                print(f"👉 已點擊【麵碗】圖示")
            else:
                print("❌ 未找到麵碗按鈕元素")
                continue

            time.sleep(0.8)

            # 尋找彈跳視窗上的橘色「Accept」按鈕
            accept_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), '確定')]")
            clicked_accept = False
            for abtn in accept_btns:
                if abtn.is_displayed():
                    driver.execute_script("arguments[0].click();", abtn)
                    print(f"👉 已點擊【Accept】確認按鈕")
                    clicked_accept = True
                    break

            if not clicked_accept:
                print("❌ 未偵測到 Accept 彈窗或按鈕未顯示")
                continue

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
                print(f"⚠️ 動作已執行，記錄狀態避免重按：{meal_name}")
                secured_dates.add(date_key)
                success_orders.append(meal_name)

        except Exception as e:
            print(f"搶單執行過程發生例外: {e}")

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
            now_str = time.strftime("%H:%M:%S")
            driver.get(meal_url)
            time.sleep(1.5)

            if "login" in driver.current_url.lower():
                print(f"[{now_str}] 偵測到 Session 過期，自動重新登入中...")
                login_eip(driver, username, password)
                driver.get(meal_url)
                time.sleep(1.5)

            available_meals, success_orders = check_and_auto_order(driver, TARGET_KEYWORDS, secured_dates)

            if success_orders:
                success_text = (
                    f"🎉 【⚡ 搶單成功通知！】\n"
                    f"時間：{now_str}\n"
                    f"已為您自動選取搶下：\n" + "\n".join([f"🍜 {m}" for m in success_orders]) + "\n\n"
                    f"👉 請開啟系統確認訂單：\n{meal_url}"
                )
                print(success_text)
                send_line_push(success_text)

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
