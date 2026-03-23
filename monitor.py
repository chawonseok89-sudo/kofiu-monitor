import requests
from bs4 import BeautifulSoup
import hashlib
import os
import json
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

LIMIT_URL = "https://www.kofiu.go.kr/kor/policy/ptfps02_1.do"
ANNOUNCE_URL = "https://www.kofiu.go.kr/kor/law/announce_list.do"
HASH_FILE = "last_hash.json"


def get_limit_info(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        page_hash = hashlib.md5(content.encode()).hexdigest()

        update_date = "확인 불가"
        for tag in soup.find_all(string=True):
            t = tag.strip()
            if t and ("고시" in t or "개정" in t or "최종" in t):
                update_date = t
                break

        person_count = "확인 불가"
        group_count = "확인 불가"
        total_count = "확인 불가"

        text = soup.get_text()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in lines:
            if "개인" in line and ("명" in line or "개" in line):
                person_count = line
            if "단체" in line and ("개" in line or "명" in line):
                group_count = line
            if "총" in line and ("명" in line or "개" in line):
                total_count = line

        return page_hash, update_date, person_count, group_count, total_count
    except Exception as e:
        print("제한대상자 페이지 오류: {}".format(e))
        return None, None, None, None, None


def get_announce_info(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        page_hash = hashlib.md5(content.encode()).hexdigest()

        latest_title = "확인 불가"
        latest_date = "확인 불가"

        rows = soup.select("table tbody tr")
        if rows:
            first_row = rows[0]
            cells = first_row.find_all("td")
            if len(cells) >= 2:
                latest_title = cells[1].get_text(strip=True)
                latest_date = cells[-1].get_text(strip=True)

        if latest_title == "확인 불가":
            items = soup.select(".board-list li, .list-wrap li, .tbl-wrap tr")
            if items:
                text = items[0].get_text(strip=True)
                latest_title = text[:50] + "..." if len(text) > 50 else text

        return page_hash, latest_title, latest_date
    except Exception as e:
        print("공고/고시 페이지 오류: {}".format(e))
        return None, None, None


def send_telegram(message):
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=data)


def load_hashes():
    try:
        with open(HASH_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_hashes(hashes):
    with open(HASH_FILE, "w") as f:
        json.dump(hashes, f)


def main():
    today = datetime.now().strftime("%Y년 %m월 %d일")
    last_hashes = load_hashes()
    new_hashes = {}
    messages = []

    # ① 금융거래등제한대상자 명단 모니터링
    limit_hash, limit_date, person_count, group_count, total_count = get_limit_info(LIMIT_URL)

    if limit_hash:
        new_hashes["limit"] = limit_hash
        last_limit = last_hashes.get("limit")

        count_info = (
            "개인: {}\n"
            "단체: {}\n"
            "총계: {}"
        ).format(person_count, group_count, total_count)

        if last_limit is None:
            messages.append(
                "[koFIU 금융거래등제한대상자 모니터링 시작]\n\n"
                "시작일: {}\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(today, count_info, limit_date, LIMIT_URL)
            )
        elif limit_hash != last_limit:
            messages.append(
                "[긴급] 금융거래등제한대상자 명단 변경 감지!\n\n"
                "감지일: {}\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}\n\n"
                "즉시 확인하여 시스템에 반영해 주세요!".format(today, count_info, limit_date, LIMIT_URL)
            )
        else:
            messages.append(
                "[{}] 금융거래등제한대상자 명단 변경없음\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(today, count_info, limit_date, LIMIT_URL)
            )

    # ② 공고/고시/훈령/예규 모니터링
    announce_hash, latest_title, latest_date = get_announce_info(ANNOUNCE_URL)

    if announce_hash:
        new_hashes["announce"] = announce_hash
        last_announce = last_hashes.get("announce")

        if last_announce is None:
            messages.append(
                "[koFIU 공고/고시/훈령/예규 모니터링 시작]\n\n"
                "시작일: {}\n"
                "최근 게시글: {}\n"
                "게시일: {}\n"
                "링크: {}".format(today, latest_title, latest_date, ANNOUNCE_URL)
            )
        elif announce_hash != last_announce:
            messages.append(
                "[긴급] 공고/고시/훈령/예규 신규 업데이트!\n\n"
                "감지일: {}\n"
                "최신 게시글: {}\n"
                "게시일: {}\n"
                "링크: {}\n\n"
                "즉시 확인해 주세요!".format(today, latest_title, latest_date, ANNOUNCE_URL)
            )
        else:
            messages.append(
                "[{}] 공고/고시/훈령/예규 변경없음\n\n"
                "최근 업데이트된 게시글: {}\n"
                "게시일: {}\n"
                "링크: {}".format(today, latest_title, latest_date, ANNOUNCE_URL)
            )

    # 메시지 전송
    if messages:
        full_message = "\n\n========================================\n\n".join(messages)
        send_telegram(full_message)

    # 해시 저장
    if new_hashes:
        merged = last_hashes.copy()
        merged.update(new_hashes)
        save_hashes(merged)


if __name__ == "__main__":
    main()
