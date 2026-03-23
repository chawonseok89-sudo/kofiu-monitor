import requests
from bs4 import BeautifulSoup
import hashlib
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TARGET_URL = "https://www.kofiu.go.kr/kor/finance/limitList.do"
HASH_FILE = "last_hash.txt"


def get_page_info(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        page_hash = hashlib.md5(content.encode()).hexdigest()

        update_date = "확인 불가"
        date_candidates = soup.find_all(string=lambda t: t and ("개정" in t or "최종" in t or "갱신" in t or "update" in t.lower()))
        if date_candidates:
            update_date = date_candidates[0].strip()

        return page_hash, update_date
    except Exception as e:
        print(f"페이지 조회 오류: {e}")
        return None, None


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=data)


def main():
    today = datetime.now().strftime("%Y년 %m월 %d일")
    current_hash, update_date = get_page_info(TARGET_URL)

    if not current_hash:
        send_telegram(f"⚠️ [{today}] koFIU 페이지 조회에 실패했습니다.\n잠시 후 다시 시도합니다.")
        return

    try:
        with open(HASH_FILE, "r") as f:
            last_hash = f.read().strip()
    except FileNotFoundError:
        last_hash = None

    if last_hash is None:
        message = (
            f"✅ <b>koFIU 모니터링 시작!</b>\n"
            f"📅 시작일: {today}\n"
            f"🔗 <a href='{TARGET_URL}'>koFIU 제한대상자 명단 바로가기</a>"
        )
        send_telegram(message)

    elif current_hash != last_hash:
        message = (
            f"🚨 <b>koFIU 금융거래등 제한대상자 명단 업데이트 감지!</b>\n\n"
            f"📅 감지일: {today}\n"
            f"📋 공중협박자금조달 관련 명단이 변경되었습니다.\n"
            f"🗓 최근 개정 정보: {update_date}\n\n"
            f"🔗 <a href='{TARGET_URL}'>koFIU 제한대상자 명단 바로가기</a>\n\n"
            f"⏰ 즉시 확인하여 시스템에 반영해 주세요!"
        )
        send_telegram(message)

    else:
        message = (
            f"✅ <b>[{today}] koFIU 명단 변경사항 없음</b>\n\n"
            f"📋 금융거래등 제한대상자 명단이 전일과 동일합니다.\n"
            f"🗓 최근 개정 정보: {update_date}\n\n"
            f"🔗 <a href='{TARGET_URL}'>koFIU 제한대상자 명단 바로가기</a>"
        )
        send_telegram(message)

    with open(HASH_FILE, "w") as f:
        f.write(current_hash)


if __name__ == "__main__":
    main()
```

---

## 📱 텔레그램 알림 예시

**변경사항 없을 때:**
```
✅ [2026년 03월 23일] koFIU 명단 변경사항 없음

📋 금융거래등 제한대상자 명단이 전일과 동일합니다.
🗓 최근 개정 정보: 2026.03.20

🔗 koFIU 제한대상자 명단 바로가기
```

**변경 감지 시:**
```
🚨 koFIU 금융거래등 제한대상자 명단 업데이트 감지!

📅 감지일: 2026년 03월 23일
📋 공중협박자금조달 관련 명단이 변경되었습니다.
🗓 최근 개정 정보: 2026.03.23

🔗 koFIU 제한대상자 명단 바로가기

⏰ 즉시 확인하여 시스템에 반영해 주세요!
