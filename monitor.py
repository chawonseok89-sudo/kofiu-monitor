import requests
import hashlib
import os
import json
from datetime import datetime, date, timedelta
import xml.etree.ElementTree as ET

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

UN_XML_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
UN_PAGE_URL = "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list"

ANNOUNCE_URL = "https://www.kofiu.go.kr/kor/law/announce_list.do"
ANNOUNCE_SEC_CODES = ["0004","0005","0006","0008","0009","0010","0011","0012"]
ANNOUNCE_API_BASE = "https://www.kofiu.go.kr/cmn/board/selectBoardListFile.do?ntcnYardOrdrNo=&page=1&size=3&selScope=&subSech=&seCd={}"
ANNOUNCE_VIEW = "https://www.kofiu.go.kr/kor/law/announce_view.do?ntcnYardOrdrNo={}&seCd={}"
HASH_FILE = "last_hash.json"


def get_business_days():
    today = date.today()

    def prev_biz(d, offset):
        while offset > 0:
            d -= timedelta(days=1)
            if d.weekday() < 5:
                offset -= 1
        return d

    prev1 = prev_biz(today, 1)
    prev2 = prev_biz(today, 2)
    return prev1.strftime("%Y.%m.%d"), prev2.strftime("%Y.%m.%d")


def get_un_sanctions_info():
    try:
        print("UN 제재 XML 다운로드")
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(UN_XML_URL, headers=headers, timeout=30)
        print("응답코드: {}".format(response.status_code))

        page_hash = hashlib.md5(response.content).hexdigest()
        root = ET.fromstring(response.content)

        person_count = 0
        entity_count = 0
        generated_date = "확인 불가"

        date_attr = root.get("dateGenerated", root.get("date", ""))
        if date_attr:
            generated_date = date_attr[:10]

        for child in root:
            tag = child.tag.upper()
            if "INDIVIDUAL" in tag:
                person_count = len(child.findall("./INDIVIDUAL") or list(child))
            elif "ENTITY" in tag or "ENTITIES" in tag:
                entity_count = len(child.findall("./ENTITY") or list(child))

        if person_count == 0 and entity_count == 0:
            person_count = len(root.findall(".//INDIVIDUAL"))
            entity_count = len(root.findall(".//ENTITY"))

        print("개인:{} 단체:{} 날짜:{}".format(person_count, entity_count, generated_date))
        return page_hash, person_count, entity_count, generated_date

    except Exception as e:
        print("UN XML 오류: {}".format(e))
        return None, 0, 0, "확인 불가"


def get_announce_info():
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": ANNOUNCE_URL}
        best_posts = []
        best_date = ""
        best_hash = None
        best_seCd = "0006"

        for seCd in ANNOUNCE_SEC_CODES:
            try:
                url = ANNOUNCE_API_BASE.format(seCd)
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    continue

                data = response.json()
                items = data.get("result", data.get("list", data.get("data", [])))
                if not isinstance(items, list) or len(items) == 0:
                    continue

                posts = []
                for item in items[:3]:
                    title = item.get("ntcnYardSjNm", item.get("ntcnYardSj", ""))
                    date_val = item.get("ntcnYardRgiDt", item.get("ntcnYardChangeDt", ""))
                    order_no = item.get("ntcnYardOrdrNo", "")
                    if date_val:
                        date_val = date_val[:10].replace("-", ".")
                    link = ANNOUNCE_VIEW.format(order_no, seCd) if order_no else ANNOUNCE_URL
                    if title:
                        posts.append({"title": title[:60], "date": date_val, "link": link})

                if posts:
                    latest = posts[0]["date"]
                    print("seCd={} | {} ({})".format(seCd, posts[0]["title"][:20], latest))
                    if latest > best_date:
                        best_date = latest
                        best_posts = posts
                        best_hash = hashlib.md5(response.text.encode()).hexdigest()
                        best_seCd = seCd
            except Exception as e:
                print("seCd={} 오류: {}".format(seCd, e))

        print("최종 seCd={} 날짜={}".format(best_seCd, best_date))
        if best_hash is None:
            best_hash = hashlib.md5("no_data".encode()).hexdigest()
        return best_hash, best_posts, best_date if best_date else "확인 불가"

    except Exception as e:
        print("공고/고시 오류: {}".format(e))
        return None, [], "확인 불가"


def send_telegram(message):
    print("텔레그램 전송 시도...")
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    response = requests.post(url, data=data)
    print("응답코드: {}".format(response.status_code))
    print("응답: {}".format(response.text[:200]))


def load_data():
    try:
        with open(HASH_FILE, "r") as f:
            data = json.load(f)
            print("저장된 데이터: {}".format(data))
            return data
    except FileNotFoundError:
        print("저장 파일 없음 - 최초 실행")
        return {}


def save_data(data):
    with open(HASH_FILE, "w") as f:
        json.dump(data, f)
    print("데이터 저장 완료")


def diff_str(diff):
    if diff > 0:
        return "(+{})".format(diff)
    elif diff < 0:
        return "({})".format(diff)
    else:
        return "(변동없음)"


def main():
    today = datetime.now().strftime("%Y년 %m월 %d일")
    prev1_day, prev2_day = get_business_days()
    print("=== koFIU 모니터링 시작 ({}) ===".format(today))

    last_data = load_data()
    new_data = {}
    messages = []

    # ① UN 제재 명단 모니터링
    un_hash, person_count, entity_count, generated_date = get_un_sanctions_info()

    if un_hash:
        new_data["un_hash"] = un_hash
        new_data["un_person_today"] = person_count
        new_data["un_entity_today"] = entity_count

        last_hash = last_data.get("un_hash")
        prev1_person = last_data.get("un_person_today", 0)
        prev1_entity = last_data.get("un_entity_today", 0)
        prev2_person = last_data.get("un_person_prev1", 0)
        prev2_entity = last_data.get("un_entity_prev1", 0)

        # 오늘 → 전일로 이동 저장
        new_data["un_person_prev1"] = prev1_person
        new_data["un_entity_prev1"] = prev1_entity

        diff1_person = person_count - prev1_person
        diff1_entity = entity_count - prev1_entity
        diff2_person = person_count - prev2_person
        diff2_entity = entity_count - prev2_entity

        if last_hash is None:
            un_info = (
                "[ UN 제재대상자 현황 ]\n"
                "개인: {}명 / 단체: {}개\n"
                "명단 기준일: {}"
            ).format(person_count, entity_count, generated_date)

            messages.append(
                "[koFIU 금융거래등제한대상자 모니터링 시작]\n\n"
                "{}\n\n"
                "출처: {}".format(un_info, UN_PAGE_URL)
            )
        elif un_hash != last_hash:
            un_info = (
                "[ UN 제재대상자 현황 ]\n"
                "개인: {}명 / 단체: {}개\n"
                "명단 기준일: {}\n\n"
                "[ 전일({}) 대비 ]\n"
                "개인: {} / 단체: {}\n\n"
                "[ 전전일({}) 대비 ]\n"
                "개인: {} / 단체: {}"
            ).format(
                person_count, entity_count, generated_date,
                prev1_day, diff_str(diff1_person), diff_str(diff1_entity),
                prev2_day, diff_str(diff2_person), diff_str(diff2_entity)
            )
            messages.append(
                "[긴급] UN 제재대상자 명단 변경 감지!\n\n"
                "감지일: {}\n\n"
                "{}\n\n"
                "출처: {}\n\n"
                "즉시 확인하여 시스템에 반영해 주세요!".format(today, un_info, UN_PAGE_URL)
            )
        else:
            un_info = (
                "[ UN 제재대상자 현황 ]\n"
                "개인: {}명 / 단체: {}개\n"
                "명단 기준일: {}\n\n"
                "[ 전일({}) 대비 ]\n"
                "개인: {} / 단체: {}\n\n"
                "[ 전전일({}) 대비 ]\n"
                "개인: {} / 단체: {}"
            ).format(
                person_count, entity_count, generated_date,
                prev1_day, diff_str(diff1_person), diff_str(diff1_entity),
                prev2_day, diff_str(diff2_person), diff_str(diff2_entity)
            )
            messages.append(
                "[{}] UN 제재대상자 명단 변동없음\n\n"
                "{}\n\n"
                "출처: {}".format(today, un_info, UN_PAGE_URL)
            )

    # ② 공고/고시/훈령/예규 모니터링
    announce_hash, posts, latest_date = get_announce_info()

    if announce_hash:
        new_data["announce_hash"] = announce_hash
        last_announce = last_data.get("announce_hash")
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

    if new_data:
        merged = last_data.copy()
        merged.update(new_data)
        save_data(merged)

    print("=== 모니터링 완료 ===")


if __name__ == "__main__":
    main()
