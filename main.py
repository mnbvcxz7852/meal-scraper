import os
import requests

url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

try:
    print(f"嘗試連線至: {url}")
    response = requests.get(url, headers=headers, timeout=15)
    print(f"連線狀態碼: {response.status_code}")
    print("網頁標題或部分內容預覽:")
    print(response.text[:300])
except Exception as e:
    print(f"連線失敗: {e}")
