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
from selenium.common.exceptions import TimeoutException

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
    time.sleep(2)

def check_and_auto_order(driver, targets, allowed_dates, secured_dates):
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
    
    time.sleep(0.4) 
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

        time.sleep(0.5) 

        # 鎖定麵碗並進行【視覺防禦】判定
        try:
            date_rows = driver.find_elements(By.XPATH, f"//*[contains(text(), '{date_str}')]")
            for d_elem in date_rows:
                row_container = d_elem.find_element(
                    By.XPATH, 
                    "./ancestor::div[contains(@class, 'card-header') or contains(@class, 'header') or contains(@style, 'pink') or count(.//button | .//svg | .//img) >= 3][1]"
                )
                
                # 🌟 視覺判定：讀取瀏覽器渲染的 CSS 背景色，檢查是否為黃色
                is_yellow = driver.execute_script(r"""
                    function isY(node) {
                        if (!node) return false;
                        var rgba = window.getComputedStyle(node).backgroundColor;
                        var m = rgba.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
                        if (m) {
                            var r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
                            // 黃色特徵：紅、綠色值高於 190，且藍色值明顯偏低
                            return (r > 190 && g > 190 && (r - b > 15));
                        }
                        return false;
                    }
                    var elem = arguments[0];
                    return isY(elem) || isY(elem.parentElement) || (elem.firstElementChild ? isY(elem.firstElementChild) : false);
                """, row_container)

                if is_yellow:
                    print(f"⏩ [視覺判定] {date_str} 呈現黃色底（已有訂單），自動略過！")
                    secured_dates.add(target_date_key)
                    clicked_bowl = "SKIP"
                    break

                # 若不是黃色，正常點擊
                clickables = row_container.find_elements(By.XPATH, ".//button | .//*[name()='svg'] | .//img | .//i | .//span[contains(@class, 'btn')]")
                if len(clickables) >= 3:
                    if safe_click(driver, clickables[2]):
                        clicked_bowl = True
                        print(f"[步驟 1] 👉 成功點擊 {date_str} 麵碗，等待彈窗...")
                        break
        except Exception:
            pass

        if clicked_bowl == "SKIP":
            continue

        if not clicked_bowl and date_str:
            try:
                noodle_icon = driver.find_element(By.XPATH, f"(//*[contains(text(), '{date_str}')]/following::*[(self::button or self::img or name()='svg') and not(contains(@class, 'arrow'))])[3]")
                if safe_click(driver, noodle_icon):
                    clicked_bowl = True
                    print(f"[步驟 1] 👉 成功點擊 {date_str} 麵碗，等待彈窗...")
            except Exception:
                pass

        if not clicked_bowl:
            continue

        # ⚡ 動態攔截彈窗與防退訂機制 (第二道防線)
        try:
            wait = WebDriverWait(driver, 3)
            wait.until(EC.presence_of_all_elements_located((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), '確定') or contains(text(), 'Cancel')]")))
            
            time.sleep(0.3) 
            modal_text = driver.find_element(By.TAG_NAME, "body").text
            
            if "是否取消" in modal_text or "確定要取消" in modal_text:
                print(f"🛑 [防禦攔截] 發現 {date_str} 已有訂單 (跳出取消視窗)！立即中斷操作並關閉視窗。")
                cancel_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Cancel') or contains(text(), '取消')]")
                for cbtn in cancel_btns:
                    if cbtn.is_displayed():
                        safe_click(driver, cbtn)
                        break
                secured_dates.add(target_date_key)
                continue
            
            accept_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), '確定')]")
            for abtn in accept_btns:
                if abtn.is_displayed():
                    safe_click(driver, abtn)
                    print(f"[步驟 2] 👉 成功點擊彈窗【Accept】按鈕")
                    break

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

        except TimeoutException:
            print("[下單異常]: TimeoutException - 系統彈跳視窗未跳出，可能網頁反應延遲。")
        except Exception as e:
            error_type = type(e).__name__
            print(f"[下單異常]: {error_type} - {e}")

    return available_meals, success_orders

def main():
    username = os.getenv("EIP_USER")
    password = os.getenv("EIP_PASS")

    if not username or not password:
        return

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,800")
    prefs = {"profile.managed_default_content_settings.images": 2, "profile.default_content_setting_values.notifications": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.page_load_strategy = 'eager' 

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        login_eip(driver, username, password)
        meal_url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"
        print("⚡ 極速模式啟動中 (已載入視覺防禦與彈窗防護)...")

        max_checks = 5000
        check_interval = 1.5 
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
