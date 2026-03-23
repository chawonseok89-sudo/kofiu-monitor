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
        print("제한대상자 페이지 접속 시도: {}".format(url))
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        print("제한대상자 페이지 응답코드: {}".format(response.status_code))

        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        page_hash = hashlib.md5(content.encode()).hexdigest()
        print("제한대상자 해시: {}".format(page_hash))

        update_date = "확인 불가"
        for tag in soup.find_all(string=True):
            t = tag.strip()
            if t and ("고시" in t or "개정" in t or "최종" in t):
                update_date = t
                break

        lines = [l.strip() for l in content.splitlines() if l.strip()]
        un_1267 = un_1718 = un_1988 = un_1737 = un_total = "확인 불가"
        for line in lines:
            if "1267" in line and ("명" in line or "개" in line):
                un_1267 = line
            if "1718" in line and ("명" in line or "개" in line):
                un_1718 = line
            if "1988" in line and ("명" in line or "개" in line):
                un_1988 = line
            if "1737" in line and ("명" in line or "개" in line):
                un_1737 = line
            if "총" in line and ("명" in line or "개" in line):
                un_total = line

        return page_hash, update_date, un_1267, un_1718, un_1988, un_1737, un_total
    except Exception as e:
        print("제한대상자 페이지 오류: {}".format(e))
        return None, None, None, None, None, None, None


def get_announce_info(url):
    try:
        print("공고/고시 페이지 접속 시도: {}".format(url))
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        print("공고/고시 페이지 응답코드: {}".format(response.status_code))

        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        page_hash = hashlib.md5(content.encode()).hexdigest()
        print("공고/고시 해시: {}".format(page_hash))

        posts = []
        rows = soup.select("table tbody tr")
        print("테이블 행 수: {}".format(len(rows)))
        for row in rows[:3]:
            cells = row.find_all("td")
            if len(cells) >= 2:
                title = cells[1].get_text(strip=True)
                date = cells[-1].get_text(strip=True)
                if title:
                    posts.append({"title": title, "date": date})

        if not posts:
            items = soup.select(".board-list li, .list-wrap li")
            for item in items[:3]:
                text = item.get_text(strip=True)
                if text:
                    posts.append({"title": text[:60], "date": ""})

        print("추출된 게시글 수: {}".format(len(posts)))
        latest_date = posts[0]["date"] if posts else "확인 불가"
        return page_hash, posts, latest_date
    except Exception as e:
        print("공고/고시 페이지 오류: {}".format(e))
        return None, [], "확인 불가"


def send_telegram(message):
    print("텔레그램 전송 시도...")
    print("TOKEN 앞 10자리: {}".format(str(TELEGRAM_TOKEN)[:10] if TELEGRAM_TOKEN else "없음"))
    print("CHAT_ID: {}".format(CHAT_ID))
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    response = requests.post(url, data=data)
    print("텔레그램 응답코드: {}".format(response.status_code))
    print("텔레그램 응답내용: {}".format(response.text[:200]))


def load_hashes():
    try:
        with open(HASH_FILE, "r") as f:
            data = json.load(f)
            print("저장된 해시: {}".format(data))
            return data
    except FileNotFoundError:
        print("해시 파일 없음 - 최초 실행")
        return {}


def save_hashes(hashes):
    with open(HASH_FILE, "w") as f:
        json.dump(hashes, f)
    print("해시 저장 완료: {}".format(hashes))


def main():
    today = datetime.now().strftime("%Y년 %m월 %d일")
    print("=== koFIU 모니터링 시작 ({}) ===".format(today))

    last_hashes = load_hashes()
    new_hashes = {}
    messages = []

    result = get_limit_info(LIMIT_URL)
    limit_hash, limit_date, un_1267, un_1718, un_1988, un_1737, un_total = result

    if limit_hash:
        new_hashes["limit"] = limit_hash
        last_limit = last_hashes.get("limit")
        print("이전 제한대상자 해시: {}".format(last_limit))
        print("현재 제한대상자 해시: {}".format(limit_hash))

        un_info = (
            "[ UN 제재대상자 현황 ]\n"
            "ISIL/Al-Qaida (결의 1267호): {}\n"
            "북한 DPRK    (결의 1718호): {}\n"
            "탈레반       (결의 1988호): {}\n"
            "이란         (결의 1737호): {}\n"
            "총계: {}"
        ).format(un_1267, un_1718, un_1988, un_1737, un_total)

        if last_limit is None:
            messages.append(
                "[koFIU 금융거래등제한대상자 모니터링 시작]\n\n"
                "시작일: {}\n\n{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(today, un_info, limit_date, LIMIT_URL)
            )
        elif limit_hash != last_limit:
            messages.append(
                "[긴급] 금융거래등제한대상자 명단 변경 감지!\n\n"
                "감지일: {}\n\n{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}\n\n"
                "즉시 확인하여 시스템에 반영해 주세요!".format(today, un_info, limit_date, LIMIT_URL)
            )
        else:
            print("제한대상자 변경 없음")
            messages.append(
                "[{}] 금융거래등제한대상자 명단 변경없음\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(today, un_info, limit_date, LIMIT_URL)
            )

    announce_hash, posts, latest_date = get_announce_info(ANNOUNCE_URL)

    if announce_hash:
        new_hashes["announce"] = announce_hash
        last_announce = last_hashes.get("announce")
        print("이전 공고/고시 해시: {}".format(last_announce))
        print("현재 공고/고시 해시: {}".format(announce_hash))

        post_lines = ""
        for i, p in enumerate(posts, 1):
            post_lines += "{}. {} ({})\n".format(i, p["title"], p["date"])

        if last_announce is None:
            messages.append(
                "[koFIU 공고/고시/훈령/예규 모니터링 시작]\n\n"
                "시작일: {}\n\n"
                "[ 최근 게시글 ]\n{}\n"
                "링크: {}".format(today, post_lines, ANNOUNCE_URL)
            )
        elif announce_hash != last_announce:
            messages.append(
                "[긴급] 공고/고시/훈령/예규 신규 업데이트!\n\n"
                "감지일: {}\n\n"
                "[ 최근 게시글 ]\n{}\n"
                "링크: {}\n\n"
                "즉시 확인해 주세요!".format(today, post_lines, ANNOUNCE_URL)
            )
        else:
            print("공고/고시 변경 없음")
            messages.append(
                "[{}] 공고/고시/훈령/예규 변경없음 (최근게시글 {})\n\n"
                "[ 최근 게시글 ]\n{}\n"
                "링크: {}".format(today, latest_date, post_lines, ANNOUNCE_URL)
            )

    print("전송할 메시지 수: {}".format(len(messages)))

    if messages:
        full_message = "\n\n========================================\n\n".join(messages)
        send_telegram(full_message)

    if new_hashes:
        merged = last_hashes.copy()
        merged.update(new_hashes)
        save_hashes(merged)

    print("=== 모니터링 완료 ===")


if __name__ == "__main__":
    main()
