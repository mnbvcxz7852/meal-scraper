import os
import asyncio
from playwright.async_api import async_playwright

async def main():
    username = os.getenv("EIP_USER")
    password = os.getenv("EIP_PASS")

    if not username or not password:
        print("錯誤：未讀取到 EIP_USER 或 EIP_PASS 環境變數，請確認 GitHub Secrets 設定。")
        return

    async with async_playwright() as p:
        print("啟動背景瀏覽器...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        # 1. 前往登入頁面
        login_url = "https://eip2.sag.tw/SAGWeb/pages/authentication/login-v1"
        print(f"前往登入頁: {login_url}")
        await page.goto(login_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # 2. 自動偵測並輸入帳號、密碼
        print("正在填入登入資訊...")
        # 尋找輸入框 (依序嘗試常見的 input 屬性)
        user_input = page.locator("input[type='text'], input[name*='user'], input[id*='user'], input[placeholder*='帳號']").first
        await user_input.fill(username)

        pass_input = page.locator("input[type='password']").first
        await pass_input.fill(password)

        # 3. 點擊登入按鈕
        print("送出登入...")
        login_btn = page.locator("button[type='submit'], button:has-text('登入'), button:has-text('Login'), input[type='submit']").first
        await login_btn.click()

        # 4. 等待登入跳轉
        await page.wait_for_timeout(5000)
        await page.wait_for_load_state("networkidle")

        # 5. 直接前往點餐系統頁面
        meal_url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"
        print(f"前往點餐系統: {meal_url}")
        await page.goto(meal_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        print(f"當前停留網址: {page.url}")

        # 6. 截圖存檔以便確認是否成功登入進入點餐畫面
        await page.screenshot(path="screenshot_meal.png", full_page=True)
        print("已儲存點餐畫面截圖: screenshot_meal.png")

        # 印出前 500 個字元以供檢視文字
        body_text = await page.inner_text("body")
        print("【點餐頁面文字預覽】：")
        print(body_text[:500])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
