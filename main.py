import requests
from bs4 import BeautifulSoup

url = "https://eip2.sag.tw/SAGWeb/SAG/BookMeal"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=15)
    response.encoding = response.apparent_encoding  # 避免中文亂碼
    
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.string.strip() if soup.title else "無標題"
    print(f"【網頁標題】：{title}")
    
    # 印出前 500 個字元的純文字內容以供判讀
    body_text = soup.get_text(separator=" ", strip=True)
    print(f"【網頁文字預覽】：\n{body_text[:500]}")

except Exception as e:
    print(f"連線異常: {e}")
