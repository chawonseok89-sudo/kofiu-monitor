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
ANNOUNCE_LATEST_URL = "https://www.kofiu.go.kr/kor/law/announce_view.do?ntcnYardOrdrNo=83&seCd=LAW"
ANNOUNCE_HASH_API = "https://www.kofiu.go.kr/cmn/file/downloadLaw.do"
HASH_FILE = "last_hash.json"


def get_business_days():
    today = date.today()

    def prev_biz(d, n):
        while n > 0:
            d -= timedelta(days=1)
            if d.weekday() < 5:
                n -= 1
        return d

    prev1 = prev_biz(today, 1)
    prev2 = prev_biz(today, 2)
    return prev1.strftime("%Y.%m.%d"), prev2.strftime("%Y.%m.%d")


def get_un_sanctions_info():
    try:
        print("UN XML 다운로드")
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


def get_announce_info(last_data):
    try:
        print("공고/고시 변경 감지")
        headers = {"User-Agent": "Mozilla/5.0", "Referer": ANNOUNCE_URL}

        response = requests.get(ANNOUNCE_HASH_API, headers=headers, timeout=10)
        print("응답코드: {}".format(response.status_code))
        print("응답내용: {}".format(response.text[:300]))

        page_hash = hashlib.md5(response.text.encode()).hexdigest()

        saved_post = last_data.get("announce_latest_post", {})
        if not saved_post:
            saved_post = {
                "title": "특정 금융거래정보 보고 등에 관한 검사 및 제재규정 일부개정규정",
                "date": "2026.02.19",
                "link": ANNOUNCE_LATEST_URL
            }

        return page_hash, saved_post

    except Exception as e:
        print("공고/고시 오류: {}".format(e))
        return None, {}


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
            print("저장된 데이터: {}".format(list(data.keys())))
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
        return "+{}".format(diff)
    elif diff < 0:
        return "{}".format(diff)
    else:
        return "변동없음"


def main():
    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    today_key = datetime.now().strftime("%Y.%m.%d")
    prev1_day, prev2_day = get_business_days()
    print("=== koFIU 모니터링 시작 ({}) ===".format(today_str))

    last_data = load_data()
    new_data = {}
    messages = []

    # ① UN 제재 명단 모니터링
    un_hash, person_count, entity_count, generated_date = get_un_sanctions_info()

    if un_hash:
        new_data["un_hash"] = un_hash
        history = last_data.get("un_history", {})
        history[today_key] = {"person": person_count, "entity": entity_count}
        new_data["un_history"] = history

        last_hash = last_data.get("un_hash")
        prev1_data = history.get(prev1_day, {})
        prev2_data = history.get(prev2_day, {})

        prev1_person = prev1_data.get("person", 0)
        prev1_entity = prev1_data.get("entity", 0)
        prev2_person = prev2_data.get("person", 0)
        prev2_entity = prev2_data.get("entity", 0)

        diff1_p = person_count - prev1_person if prev1_person else 0
        diff1_e = entity_count - prev1_entity if prev1_entity else 0
        diff2_p = person_count - prev2_person if prev2_person else 0
        diff2_e = entity_count - prev2_entity if prev2_entity else 0

        if prev1_data:
            prev1_line = "전일({}) 대비: 개인 {} / 단체 {}".format(
                prev1_day, diff_str(diff1_p), diff_str(diff1_e))
        else:
            prev1_line = "전일({}) 대비: 데이터 누적 중 (내일부터 표시)".format(prev1_day)

        if prev2_data:
            prev2_line = "전전일({}) 대비: 개인 {} / 단체 {}".format(
                prev2_day, diff_str(diff2_p), diff_str(diff2_e))
        else:
            prev2_line = "전전일({}) 대비: 데이터 누적 중 (모레부터 표시)".format(prev2_day)

        un_info = (
            "[ UN 제재대상자 현황 ]\n"
            "개인: {}명 / 단체: {}개\n"
            "명단 기준일: {}\n\n"
            "{}\n{}"
        ).format(person_count, entity_count, generated_date, prev1_line, prev2_line)

        if last_hash is None:
            messages.append(
                "[koFIU 금융거래등제한대상자 모니터링 시작]\n\n"
                "[ UN 제재대상자 현황 ]\n"
                "개인: {}명 / 단체: {}개\n"
                "명단 기준일: {}\n\n"
                "* 전일/전전일 비교는 데이터 누적 후 표시됩니다\n\n"
                "출처: {}".format(person_count, entity_count, generated_date, UN_PAGE_URL)
            )
        elif un_hash != last_hash:
            messages.append(
                "[긴급] UN 제재대상자 명단 변경 감지!\n\n"
                "감지일: {}\n\n{}\n\n"
                "출처: {}\n\n"
                "즉시 확인하여 시스템에 반영해 주세요!".format(today_str, un_info, UN_PAGE_URL)
            )
        else:
            messages.append(
                "[{}] UN 제재대상자 명단 변동없음\n\n{}\n\n"
                "출처: {}".format(today_str, un_info, UN_PAGE_URL)
            )

    # ② 공고/고시/훈령/예규 모니터링
    announce_hash, latest_post = get_announce_info(last_data)

    if announce_hash:
        new_data["announce_hash"] = announce_hash
        new_data["announce_latest_post"] = latest_post
        last_announce = last_data.get("announce_hash")

        post_info = "게시글 확인 불가"
        if latest_post:
            post_info = "최신 게시글: {} ({})\n링크: {}".format(
                latest_post.get("title", ""),
                latest_post.get("date", ""),
                latest_post.get("link", ANNOUNCE_URL))

        if last_announce is None:
            messages.append(
                "[koFIU 공고/고시/훈령/예규 모니터링 시작]\n\n"
                "{}\n\n전체 목록: {}".format(post_info, ANNOUNCE_URL)
            )
        elif announce_hash != last_announce:
            messages.append(
                "[긴급] 공고/고시/훈령/예규 업데이트!\n\n"
                "감지일: {}\n\n{}\n\n전체 목록: {}\n\n"
                "즉시 확인해 주세요!".format(today_str, post_info, ANNOUNCE_URL)
            )
        else:
            messages.append(
                "[{}] 공고/고시/훈령/예규 변동없음\n\n{}\n\n"
                "전체 목록: {}".format(today_str, post_info, ANNOUNCE_URL)
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
