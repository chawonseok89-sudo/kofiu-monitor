import requests
from bs4 import BeautifulSoup
import hashlib
import os
 
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TARGET_URL = "https://www.kofiu.go.kr/kor/finance/limitList.do"
HASH_FILE = "last_hash.txt"
 
 
def get_page_hash(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        return hashlib.md5(content.encode()).hexdigest()
    except Exception as e:
        print(f"페이지 조회 오류: {e}")
        return None
 
 
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=data)
 
 
def main():
    current_hash = get_page_hash(TARGET_URL)
    if not current_hash:
        print("페이지 조회 실패")
        return
 
    try:
        with open(HASH_FILE, "r") as f:
            last_hash = f.read().strip()
    except FileNotFoundError:
        last_hash = None
 
    if last_hash is None:
        print("최초 실행 - 기준값 저장")
        send_telegram("✅ koFIU 모니터링 시작되었습니다!")
    elif current_hash != last_hash:
        message = (
            "🚨 <b>koFIU 금융거래등 제한대상자 명단 업데이트 감지!</b>\n\n"
            "📋 공중협박자금조달 관련 명단이 변경되었습니다.\n"
            f"🔗 확인하기: {TARGET_URL}\n\n"
            "⏰ 즉시 확인하여 시스템에 반영해 주세요."
        )
        send_telegram(message)
        print("변경 감지 - 알림 전송!")
    else:
        print("변경 없음")
 
    with open(HASH_FILE, "w") as f:
        f.write(current_hash)
 
 
if __name__ == "__main__":
    main()
