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
ANNOUNCE_API = "https://www.kofiu.go.kr/cmn/board/selectBoardListFile.do?ntcnYardOrdrNo=&page=1&seCd=0006&selScope=&size=3&subSech="
ANNOUNCE_VIEW = "https://www.kofiu.go.kr/kor/law/announce_view.do?ntcnYardOrdrNo={}&seCd=0006"
HASH_FILE = "last_hash.json"


def get_limit_info(url):
    try:
        print("제한대상자 페이지 접속")
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

        person_total = "확인 불가"
        group_total = "확인 불가"

        person_match = re.search(r"개인\s*[:]?\s*(\d+)\s*명", content)
        group_match = re.search(r"단체\s*[:]?\s*(\d+)\s*개", content)
        if person_match:
            person_total = person_match.group(1)
        if group_match:
            group_total = group_match.group(1)

        if person_total == "확인 불가":
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    row_text = " ".join([c.get_text(strip=True) for c in cells])
                    print("테이블행: {}".format(row_text[:80]))
                    if "합계" in row_text or "총계" in row_text:
                        nums = []
                        for cell in cells:
                            t = cell.get_text(strip=True)
                            if re.match(r"^\d+$", t) and not (1000 <= int(t) <= 9999):
                                nums.append(t)
                        print("합계행 숫자들: {}".format(nums))
                        if len(nums) >= 2:
                            person_total = nums[0]
                            group_total = nums[1]

        print("개인:{} 단체:{}".format(person_total, group_total))
        return page_hash, update_date, person_total, group_total
    except Exception as e:
        print("제한대상자 오류: {}".format(e))
        return None, None, None, None


def get_announce_info():
    try:
        print("공고/고시 API 호출")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": ANNOUNCE_URL
        }
        response = requests.get(ANNOUNCE_API, headers=headers, timeout=10)
        print("응답코드: {}".format(response.status_code))
        print("응답내용: {}".format(response.text[:300]))

        page_hash = hashlib.md5(response.text.encode()).hexdigest()
        posts = []

        data = response.json()
        items = data.get("result", data.get("list", data.get("data", [])))
        print("items 길이: {}".format(len(items) if isinstance(items, list) else "N/A"))

        if isinstance(items, list):
            for item in items[:3]:
                title = item.get("ntcnYardSjNm", item.get("ntcnYardSj", ""))
                date = item.get("ntcnYardRgiDt", item.get("ntcnYardChangeDt", ""))
                order_no = item.get("ntcnYardOrdrNo", "")
                if date:
                    date = date[:10].replace("-", ".")
                link = ANNOUNCE_VIEW.format(order_no) if order_no else ANNOUNCE_URL
                if title:
                    posts.append({"title": title[:60], "date": date, "link": link})

        print("추출된 게시글: {}".format(posts))
        latest_date = posts[0]["date"] if posts else "확인 불가"
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
    print("텔레그램 응답: {}".format(response.text[:300]))


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

    limit_hash, limit_date, person_total, group_total = get_limit_info(LIMIT_URL)

    if limit_hash:
        new_hashes["limit"] = limit_hash
        last_limit = last_hashes.get("limit")

        un_info = (
            "[ UN 제재대상자 현황 ]\n"
            "개인: {}명 / 단체: {}개"
        ).format(person_total, group_total)

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
                "[{}] 금융거래등제한대상자 명단 변동없음\n\n"
                "{}\n\n"
                "최근 업데이트: {}\n"
                "링크: {}".format(today, un_info, limit_date, LIMIT_URL)
            )

    announce_hash, posts, latest_date = get_announce_info()

    if announce_hash:
        new_hashes["announce"] = announce_hash
        last_announce = last_hashes.get("announce")
        latest_post = posts[0] if posts else None

        if last_announce is None:
            post_info = "게시글 확인 불가"
            if latest_post:
                post_info = "최신 게시글: {} ({})\n링크: {}".format(
                    latest_post["title"], latest_post["date"], latest_post["link"])
            messages.append(
                "[koFIU 공고/고시/훈령/예규 모니터링 시작]\n\n"
                "{}\n\n"
                "전체 목록: {}".format(post_info, ANNOUNCE_URL)
            )
        elif announce_hash != last_announce:
            post_info = "게시글 확인 불가"
            if latest_post:
                post_info = "업데이트 게시글: {} ({})\n링크: {}".format(
                    latest_post["title"], latest_post["date"], latest_post["link"])
            messages.append(
                "[긴급] 공고/고시/훈령/예규 업데이트!\n\n"
                "감지일: {}\n\n"
                "{}\n\n"
                "전체 목록: {}\n\n"
                "즉시 확인해 주세요!".format(today, post_info, ANNOUNCE_URL)
            )
        else:
            post_info = "게시글 확인 불가"
            if latest_post:
                post_info = "최신 게시글: {} ({})\n링크: {}".format(
                    latest_post["title"], latest_post["date"], latest_post["link"])
            messages.append(
                "[{}] 공고/고시/훈령/예규 변동없음\n\n"
                "{}\n\n"
                "전체 목록: {}".format(today, post_info, ANNOUNCE_URL)
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
