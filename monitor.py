import requests
from bs4 import BeautifulSoup
import hashlib
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# 업데이트된 koFIU URL
TARGET_URL = "https://www.kofiu.go.kr/kor/main.do"
LIMIT_PAGE_URL = "https://www.kofiu.go.kr/kor/finance/limitList.do"
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

        return page_hash, update_date, response.status_code
    except Exception as e:
        print("페이지 조회 오류: {}".format(e))
        return None, None, None


def send_telegram(message):
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=data)


def main():
    today = datetime.now().strftime("%Y년 %m월 %d일")

    # 먼저 제한대상자 명단 페이지 접근 시도
    current_hash, update_date, status_code = get_page_info(LIMIT_PAGE_URL)

    # 페이지가 없으면 메인 페이지로 대체
    if not current_hash or status_code == 404:
        current_hash, update_date, status_code = get_page_info(TARGET_URL)
        used_url = TARGET_URL
    else:
        used_url = LIMIT_PAGE_URL

    if not current_hash:
        send_telegram("[{}] koFIU 페이지 조회에 실패했습니다. 잠시 후 다시 시도합니다.".format(today))
        return

    try:
        with open(HASH_FILE, "r") as f:
            last_hash = f.read().strip()
    except FileNotFoundError:
        last_hash = None

    if last_hash is None:
        message = (
            "[koFIU 모니터링 시작]\n"
            "시작일: {}\n"
            "모니터링 URL: {}"
        ).format(today, used_url)
        send_telegram(message)

    elif current_hash != last_hash:
        message = (
            "[긴급] koFIU 금융거래등 제한대상자 명단 업데이트 감지!\n\n"
            "감지일: {}\n"
            "공중협박자금조달 관련 명단이 변경되었습니다.\n"
            "최근 개정 정보: {}\n\n"
            "링크: {}\n\n"
            "즉시 확인하여 시스템에 반영해 주세요!"
        ).format(today, update_date, used_url)
        send_telegram(message)

    else:
        message = (
            "[{}] koFIU 명단 변경사항 없음\n\n"
            "금융거래등 제한대상자 명단이 전일과 동일합니다.\n"
            "최근 개정 정보: {}\n\n"
            "링크: {}"
        ).format(today, update_date, used_url)
        send_telegram(message)

    with open(HASH_FILE, "w") as f:
        f.write(current_hash)


if __name__ == "__main__":
    main()
