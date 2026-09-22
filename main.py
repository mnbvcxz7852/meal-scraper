import os
import time
import re
import requests
from datetime import datetime, timezone, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

TAIPEI_TZ = timezone(timedelta(hours=8))

# ==================== 🎯 搶單目標設定 ====================
TARGET_KEYWORDS = [""]
ALLOWED_DATES = ["10-05", "10-06", "10-07", "10-08", "10-09"]
# ========================================================

def send_discord_push(text):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"content": text}, timeout=5)
    except Exception:
        pass

def safe_click(driver, element):
    try:
        driver.execute_script("""
            var elem = arguments[0];
            if (elem.click) {
                elem.click();
            } else if (elem.parentElement && elem.parentElement.click) {
                elem.parentElement.click();
            } else {
                var evt = new MouseEvent('click', { bubbles: true, cancelable: true, view: window });
                elem.dispatchEvent(evt);
            }
        """, element)
        return True
    except Exception:
        try:
            element.click()
            return True
        except Exception:
            return False

def login_eip(driver, username, password):
    login_url = "https://eip2.sag.tw/SAGWeb/pages/authentication/login-v1"
    driver.get(login_url)
    
    wait = WebDriverWait(driver, 10)
    user_inputs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input[type='text'], input[name*='user'], input[id*='user']")))
    user_inputs[0].clear()
    user_inputs[0].send_keys(username)

    pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    pass_inputs[0].clear()
    pass_inputs[0].send_keys(password)

    buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button, input[type='submit']")
    for btn in buttons:
        if any(w in btn.text for w in ["登入", "Login"]) or btn.get_attribute("type") == "submit":
            safe_click(driver, btn)
            break
    time.sleep(2) # 登入跳轉需要一點固定時間

def check_and_auto_order(driver, targets, allowed_dates, secured_dates):
    # 切換麵食分頁，最多等 2 秒
    try:
        noodle_tabs = WebDriverWait(driver, 2).until(
            EC.presence_of_all_elements_located((By.XPATH, "//*[text()='麵食' or contains(text(), '麵食')]"))
        )
        for tab in noodle_tabs:
            if tab.is_displayed():
                safe_click(driver, tab)
                break
    except Exception:
        pass
    
    # 動態等待麵食內容載入 (小休眠確保 DOM 更新)
    time.sleep(0.3)
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
        if target_date_key in secured_dates:
            continue

        print(f"\n[搶單觸發] 🎯 極速鎖定：{target_date_key} {meal_name} (名額: {quota})")
        clicked_bowl = False

        # 鎖定麵碗並點擊
        try:
            date_rows = driver.find_elements(By.XPATH, f"//*[contains(text(), '{date_str}')]")
            for d_elem in date_rows:
                row_container = d_elem.find_element(
                    By.XPATH, 
                    "./ancestor::div[contains(@class, 'card-header') or contains(@class, 'header') or contains(@style, 'pink') or count(.//button | .//svg | .//img) >= 3][1]"
                )
                clickables = row_container.find_elements(By.XPATH, ".//button | .//*[name()='svg'] | .//img | .//i | .//span[contains(@class, 'btn')]")
                if len(clickables) >= 3:
                    if safe_click(driver, clickables[2]):
                        clicked_bowl = True
                        break
        except Exception:
            pass

        if not clicked_bowl and date_str:
            try:
                noodle_icon = driver.find_element(By.XPATH, f"(//*[contains(text(), '{date_str}')]/following::*[(self::button or self::img or name()='svg') and not(contains(@class, 'arrow'))])[3]")
                if safe_click(driver, noodle_icon):
                    clicked_bowl = True
            except Exception:
                pass

        if not clicked_bowl:
            continue

        # ⚡ 動態攔截彈窗 (拔除 sleep，最快 0.01 秒觸發)
        try:
            wait = WebDriverWait(driver, 3)
            accept_btns = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), '確定')]")))
            for abtn in accept_btns:
                if abtn.is_displayed():
                    safe_click(driver, abtn)
                    break

            # ⚡ 高頻檢查結果 (不再死等 1.2 秒)
            for _ in range(15):
                page_after = driver.find_element(By.TAG_NAME, "body").text
                if "數量不足" in page_after:
                    print(f"❌ 搶單失敗：{date_str} 名額被極限秒殺。")
                    break
                elif "吃麵" in page_after:
                    print(f"🎉 搶單成功：{date_str} {meal_name}")
                    secured_dates.add(target_date_key)
                    success_orders.append(f"{date_str} {meal_name}")
                    break
                time.sleep(0.1)

        except Exception as e:
            print(f"[下單異常]: {e}")

    return available_meals, success_orders

def main():
    username = os.getenv("EIP_USER")
    password = os.getenv("EIP_PASS")

    if not username or not password:
        return

    # ⚡ 效能最佳化啟動參數
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,800")
    # 阻擋圖片與無用資源，極大化載入速度
    prefs = {"profile.managed_default_content_settings.images": 2, "profile.default_content_setting_values.notifications": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.page_load_strategy = 'eager' # 不等完整資源載入完畢即開始執行

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        login_eip(driver, username, password)
        meal_url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"
        print("⚡ 極速模式啟動中...")

        max_checks = 5000
        check_interval = 1.5 # ⚡ 巡檢間隔從 5 秒降至 1.5 秒
        last_notified_items = set()
        secured_dates = set()

        for i in range(1, max_checks + 1):
            now_str = datetime.now(TAIPEI_TZ).strftime("%H:%M:%S")
            driver.get(meal_url)

            if "login" in driver.current_url.lower():
                login_eip(driver, username, password)
                driver.get(meal_url)

            available_meals, success_orders = check_and_auto_order(driver, TARGET_KEYWORDS, ALLOWED_DATES, secured_dates)

            if success_orders:
                success_text = f"🎉 **【⚡ 極速搶單成功！】**\n時間：`{now_str}`\n已為您搶下：\n" + "\n".join([f"> 🍜 **{m}**" for m in success_orders])
                send_discord_push(success_text)

            available_desc = [f"🍜 {m} (剩餘: {q})" for m, q in available_meals]
            current_set = set(available_desc)

            if available_desc and current_set != last_notified_items:
                alert_text = f"🔥 **【名額釋出】**\n時間：`{now_str}`\n釋出項目：\n" + "\n".join([f"> {item}" for item in available_desc])
                send_discord_push(alert_text)
                last_notified_items = current_set
            elif not available_desc:
                if i % 20 == 0:
                    print(f"[{now_str}] 巡檢正常運作中...")

            time.sleep(check_interval)

    except Exception as e:
        print(f"異常: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
