import requests
from bs4 import BeautifulSoup
import hashlib
import os
import json
import re
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

LIMIT_URL = "https://www.kofiu.go.kr/kor/policy/ptfps02_1.do"
ANNOUNCE_URL = "https://www.kofiu.go.kr/kor/law/announce_list.do"
ANNOUNCE_API = "https://www.kofiu.go.kr/cmn/board/selectBoardListFile.do?seCd=0003&page=1&size=3&selScope=&subSech="
HASH_FILE = "last_hash.json"


def get_limit_info(url):
    try:
        print("제한대상자 페이지 접속 시도")
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        print("응답코드: {}".format(response.status_code))

        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        page_hash = hashlib.md5(content.encode()).hexdigest()

        update_date = "확인 불가"
        for tag in soup.find_all(string=True):
            t = tag.strip()
            if t and ("고시" in t or "개정" in t or "최종" in t):
                update_date = t
                break

        un_1267 = un_1718 = un_1988 = un_1737 = un_total = "확인 불가"
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                row_text = " ".join([c.get_text(strip=True) for c in cells])
                if "1267" in row_text:
                    nums = re.findall(r"\b(\d{1,4})\b", row_text)
                    counts = [n for n in nums if not (2000 <= int(n) <= 2099) and n not in ["1267","1718","1988","1737","2253","2231"]]
                    if counts:
                        un_1267 = counts[-1]
                if "1718" in row_text:
                    nums = re.findall(r"\b(\d{1,4})\b", row_text)
                    counts = [n for n in nums if not (2000 <= int(n) <= 2099) and n not in ["1267","1718","1988","1737","2253","2231"]]
                    if counts:
                        un_1718 = counts[-1]
                if "1988" in row_text and "1267" not in row_text:
                    nums = re.findall(r"\b(\d{1,4})\b", row_text)
                    counts = [n for n in nums if not (2000 <= int(n) <= 2099) and n not in ["1267","1718","1988","1737","2253","2231"]]
                    if counts:
                        un_1988 = counts[-1]
                if "1737" in row_text:
                    nums = re.findall(r"\b(\d{1,4})\b", row_text)
                    counts = [n for n in nums if not (2000 <= int(n) <= 2099) and n not in ["1267","1718","1988","1737","2253","2231"]]
                    if counts:
                        un_1737 = counts[-1]
                if "합계" in row_text or "총계" in row_text:
                    nums = re.findall(r"\b(\d+)\b", row_text)
                    counts = [n for n in nums if not (2000 <= int(n) <= 2099)]
                    if counts:
                        un_total = counts[-1]

        return page_hash, update_date, un_1267, un_1718, un_1988, un_1737, un_total
    except Exception as e:
        print("제한대상자 페이지 오류: {}".format(e))
        return None, None, None, None, None, None, None


def get_announce_info():
    try:
        print("공고/고시 API 호출 시도")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.kofiu.go.kr/kor/law/announce_list.do"
        }
        response = requests.get(ANNOUNCE_API, headers=headers, timeout=10)
        print("API 응답코드: {}".format(response.status_code))
        print("API 응답 앞부분: {}".format(response.text[:300]))

        posts = []
        latest_date = "확인 불가"
        page_hash = hashlib.md5(response.text.encode()).hexdigest()

        try:
            data = response.json()
            items = data.get("list", data.get("data", data.get("result", [])))
            if isinstance(items, list):
                for item in items[:3]:
                    title = item.get("ntcnYardSj", item.get("title", item.get("sj", "")))
                    date = item.get("ntcnYardRgiDt", item.get("date", item.get("regDt", "")))
                    if date:
                        date = date[:10].replace("-", ".")
                    if title:
                        posts.append({"title": title[:50], "date": date})
        except Exception as je:
            print("JSON 파싱 실패, HTML로 시도: {}".format(je))
            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("tr")
            for row in rows[:3]:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    title = ""
                    date = ""
                    for cell in cells:
                        txt = cell.get_text(strip=True)
                        if len(txt) > len(title) and not txt.isdigit() and len(txt) > 3:
                            title = txt
                        if re.search(r"\d{4}[.\-]\d{2}[.\-]\d{2}", txt):
                            date = txt
                    if title:
                        posts.append({"title": title[:50], "date": date})

        if posts:
            latest_date = posts[0]["date"] if posts[0]["date"] else "확인 불가"

        print("추출된 게시글: {}".format(posts))
        return page_hash, posts, latest_date
    except Exception as e:
        print("공고/고시 오류: {}".format(e))
        return None, [], "확인 불가"


def send_telegram(message):
    print("텔레그램 전송 시도...")
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    response = requests.post(url, data=data)
    print("텔레그램 응답코드: {}".format(response.status_code))
    print("텔레그램 응답: {}".format(response.text[:200]))


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
    print("해시 저장 완료")


def main():
    today = datetime.now().strftime("%Y년 %m월 %d일")
    print("=== koFIU 모니터링 시작 ({}) ===".format(today))

    last_hashes = load_hashes()
    new_hashes = {}
    messages = []

    # ① 금융거래등제한대상자 명단 모니터링
    result = get_limit_info(LIMIT_URL)
    limit_hash, limit_date, un_1267, un_1718, un_1988, un_1737, un_total = result

    if limit_hash:
        new_hashes["limit"] = limit_hash
        last_limit = last_hashes.get("limit")

        un_info = (
            "[ UN 제재대상자 현황 ]\n"
            "1267호 (ISIL/Al-Qaida): {}명\n"
            "1718호 (북한 DPRK)    : {}명\n"
            "1988호 (탈레반)       : {}명\n"
            "1737호 (이란)         : {}명\n"
            "총계                  : {}명"
        ).format(un_1267, un_1718, un_1988, un_1737, un_total)

        if last_limit is None:
            messages.append(
                "[koFIU 금융거래등제한대상자 모니터링 시작]\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(un_info, limit_date, LIMIT_URL)
            )
        elif limit_hash != last_limit:
            messages.append(
                "[긴급] 금융거래등제한대상자 명단 변경 감지!\n\n"
                "감지일: {}\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}\n\n"
                "즉시 확인하여 시스템에 반영해 주세요!".format(today, un_info, limit_date, LIMIT_URL)
            )
        else:
            messages.append(
                "[{}] 금융거래등제한대상자 명단 변경없음\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(today, un_info, limit_date, LIMIT_URL)
            )

    # ② 공고/고시/훈령/예규 모니터링
    announce_hash, posts, latest_date = get_announce_info()

    if announce_hash:
        new_hashes["announce"] = announce_hash
        last_announce = last_hashes.get("announce")

        post_lines = ""
        for i, p in enumerate(posts, 1):
            if p["date"]:
                post_lines += "{}. {} ({})\n".format(i, p["title"], p["date"])
            else:
                post_lines += "{}. {}\n".format(i, p["title"])

        if not post_lines:
            post_lines = "게시글 확인 불가\n"

        if last_announce is None:
            messages.append(
                "[koFIU 공고/고시/훈령/예규 모니터링 시작]\n\n"
                "[ 최근 게시글 ]\n"
                "{}\n"
                "링크: {}".format(post_lines, ANNOUNCE_URL)
            )
        elif announce_hash != last_announce:
            messages.append(
                "[긴급] 공고/고시/훈령/예규 업데이트!\n\n"
                "감지일: {}\n\n"
                "[ 변경된 최근 게시글 ]\n"
                "{}\n"
                "링크: {}\n\n"
                "즉시 확인해 주세요!".format(today, post_lines, ANNOUNCE_URL)
            )
        else:
            messages.append(
                "[{}] 공고/고시/훈령/예규 변동없음\n"
                "(최근게시글 {})\n\n"
                "[ 최근 게시글 ]\n"
                "{}\n"
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
