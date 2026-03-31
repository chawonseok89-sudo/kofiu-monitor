import requests
from bs4 import BeautifulSoup
import hashlib
import os
import json
import re
from datetime import datetime
import xml.etree.ElementTree as ET

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

UN_XML_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
UN_PAGE_URL = "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list"

ANNOUNCE_URL = "https://www.kofiu.go.kr/kor/law/announce_list.do"
ANNOUNCE_API = "https://www.kofiu.go.kr/cmn/board/selectBoardListFile.do?ntcnYardOrdrNo=&page=1&seCd=0006&selScope=&size=3&subSech="
ANNOUNCE_VIEW = "https://www.kofiu.go.kr/kor/law/announce_view.do?ntcnYardOrdrNo={}&seCd=0006"
HASH_FILE = "last_hash.json"


def get_un_sanctions_info():
    try:
        print("UN 제재 XML 다운로드 시도")
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(UN_XML_URL, headers=headers, timeout=30)
        print("UN XML 응답코드: {}".format(response.status_code))

        page_hash = hashlib.md5(response.content).hexdigest()

        root = ET.fromstring(response.content)
        print("XML 루트 태그: {}".format(root.tag))

        person_count = 0
        entity_count = 0

        generated_date = "확인 불가"
        date_attr = root.get("dateGenerated", root.get("date", ""))
        if date_attr:
            generated_date = date_attr[:10]

        for child in root:
            tag = child.tag.upper()
            print("섹션: {}".format(tag))
            if "INDIVIDUAL" in tag:
                person_count = len(child.findall("./INDIVIDUAL") or list(child))
            elif "ENTITY" in tag or "ENTITIES" in tag:
                entity_count = len(child.findall("./ENTITY") or list(child))

        if person_count == 0 and entity_count == 0:
            individuals = root.findall(".//INDIVIDUAL")
            entities = root.findall(".//ENTITY")
            person_count = len(individuals)
            entity_count = len(entities)

        print("개인:{} 단체:{} 날짜:{}".format(person_count, entity_count, generated_date))
        return page_hash, person_count, entity_count, generated_date

    except Exception as e:
        print("UN XML 오류: {}".format(e))
        return None, 0, 0, "확인 불가"


def get_announce_info():
    try:
        print("공고/고시 API 호출")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": ANNOUNCE_URL
        }
        response = requests.get(ANNOUNCE_API, headers=headers, timeout=10)
        print("응답코드: {}".format(response.status_code))

        page_hash = hashlib.md5(response.text.encode()).hexdigest()
        posts = []

        data = response.json()
        items = data.get("result", data.get("list", data.get("data", [])))

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

    # ① UN 제재 명단 모니터링
    un_hash, person_count, entity_count, generated_date = get_un_sanctions_info()

    if un_hash:
        new_hashes["un"] = un_hash
        last_un = last_hashes.get("un")

        un_info = (
            "[ UN 제재대상자 현황 ]\n"
            "개인: {}명 / 단체: {}개\n"
            "명단 기준일: {}"
        ).format(person_count, entity_count, generated_date)

        if last_un is None:
            messages.append(
                "[koFIU 금융거래등제한대상자 모니터링 시작]\n\n"
                "{}\n\n"
                "출처: {}".format(un_info, UN_PAGE_URL)
            )
        elif un_hash != last_un:
            messages.append(
                "[긴급] UN 제재대상자 명단 변경 감지!\n\n"
                "감지일: {}\n\n"
                "{}\n\n"
                "출처: {}\n\n"
                "즉시 확인하여 시스템에 반영해 주세요!".format(today, un_info, UN_PAGE_URL)
            )
        else:
            messages.append(
                "[{}] UN 제재대상자 명단 변동없음\n\n"
                "{}\n\n"
                "출처: {}".format(today, un_info, UN_PAGE_URL)
            )

    # ② 공고/고시/훈령/예규 모니터링
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
