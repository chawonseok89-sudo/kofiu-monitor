import requests
from bs4 import BeautifulSoup
import hashlib
import time
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TARGET_URL = "https://www.kofiu.go.kr/kor/finance/limitList.do"
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
print("koFIU 모니터링 시작...")
send_telegram("✅ koFIU 모니터링 봇이 시작되었습니다.")
last_hash = get_page_hash(TARGET_URL)
while True:
time.sleep(3600)
current_hash = get_page_hash(TARGET_URL)
if current_hash and current_hash != last_hash:
message = (
"🚨 <b>koFIU 금융거래등 제한대상자 명단 업데이트 감지!</b>\n\n"
"📋 공중협박자금조달 관련 명단이 변경되었습니다.\n"
f"🔗 확인하기: {TARGET_URL}\n\n"
"⏰ 즉시 확인하여 시스템에 반영해 주세요."
)
send_telegram(message)
last_hash = current_hash
print("변경 감지 - 알림 전송 완료")
else:
print("변경 없음")
if name == "main":
main()
