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
ANNOUNCE_HASH_URL = "https://www.kofiu.go.kr/cmn/file/downloadLaw.do"

ANNOUNCE_INIT_TITLE = "특정 금융거래정보 보고 등에 관한 검사 및 제재규정 일부개정규정"
ANNOUNCE_INIT_DATE = "2026.02.19"

HASH_FILE = "last_hash.json"


def get_prev_business_day():
    today = date.today()
    d = today
    while True:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            return d.strftime("%Y.%m.%d")


def get_un_sanctions_info():
    try:
        print("UN XML 다운로드")
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(UN_XML_URL, headers=headers, timeout=30)
        print("UN 응답코드: {}".format(response.status_code))

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


def get_announce_hash():
    try:
        print("공고/고시 변경 감지")
        headers = {"User-Agent": "Mozilla/5.0", "Referer": ANNOUNCE_URL}
        response = requests.get(ANNOUNCE_HASH_URL, headers=headers, timeout=10)
        print("공고/고시 응답코드: {}".format(response.status_code))
        return hashlib.md5(response.text.encode()).hexdigest()
    except Exception as e:
        print("공고/고시 오류: {}".format(e))
        return None


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
            print("저장된 데이터 키: {}".format(list(data.keys())))
            return data
    except FileNotFoundError:
        print("저장 파일 없음 - 최초 실행")
        return {}


def save_data(data):
    with open(HASH_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False)
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
    prev_day = get_prev_business_day()
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
        prev_data = history.get(prev_day, {})
        prev_person = prev_data.get("person", 0)
        prev_entity = prev_data.get("entity", 0)

        diff_p = person_count - prev_person if prev_person else 0
        diff_e = entity_count - prev_entity if prev_entity else 0

        if prev_data:
            prev_line = "전일({}) 대비: 개인 {} / 단체 {}".format(
                prev_day, diff_str(diff_p), diff_str(diff_e))
        else:
            prev_line = "전일({}) 대비: 데이터 누적 중 (내일부터 표시)".format(prev_day)

        if last_hash is None:
            un_msg = (
                "🚨 <b>[koFIU 모니터링 시작]</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "🇺🇳 <b>UN 제재대상자 현황</b>\n"
                "┣ 개인: <b>{}명</b>\n"
                "┣ 단체: <b>{}개</b>\n"
                "┣ 명단 기준일: {}\n"
                "┗ * 전일 비교는 내일부터 표시\n\n"
                "출처: {}"
            ).format(person_count, entity_count, generated_date, UN_PAGE_URL)
        elif un_hash != last_hash:
            un_msg = (
                "🚨 <b>[긴급] UN 제재대상자 명단 변경!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "🇺🇳 <b>UN 제재대상자 현황</b>\n"
                "┣ 개인: <b>{}명</b>\n"
                "┣ 단체: <b>{}개</b>\n"
                "┣ 명단 기준일: {}\n"
                "┗ {}\n\n"
                "출처: {}\n\n"
                "⚠️ 즉시 확인하여 시스템에 반영해 주세요!"
            ).format(person_count, entity_count, generated_date, prev_line, UN_PAGE_URL)
        else:
            un_msg = (
                "✅ <b>[{}] UN 제재대상자 변동없음</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "🇺🇳 <b>UN 제재대상자 현황</b>\n"
                "┣ 개인: <b>{}명</b>\n"
                "┣ 단체: <b>{}개</b>\n"
                "┣ 명단 기준일: {}\n"
                "┗ {}\n\n"
                "출처: {}"
            ).format(today_str, person_count, entity_count, generated_date, prev_line, UN_PAGE_URL)

        messages.append(un_msg)

    # ② 공고/고시/훈령/예규 모니터링
    announce_hash = get_announce_hash()

    if announce_hash:
        new_data["announce_hash"] = announce_hash
        last_announce = last_data.get("announce_hash")

        saved_title = last_data.get("announce_title", ANNOUNCE_INIT_TITLE)
        saved_date = last_data.get("announce_date", ANNOUNCE_INIT_DATE)
        new_data["announce_title"] = saved_title
        new_data["announce_date"] = saved_date

        if last_announce is None:
            ann_msg = (
                "🚨 <b>[koFIU 모니터링 시작]</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📋 <b>공고/고시/훈령/예규</b>\n"
                "┣ 최근 게시글:\n"
                "┃  {}\n"
                "┣ 게시일: {}\n"
                "┗ 변경 발생 시 즉시 알림 드립니다\n\n"
                "전체 목록: {}"
            ).format(saved_title, saved_date, ANNOUNCE_URL)
        elif announce_hash != last_announce:
            new_data["announce_title"] = "새 게시글 등록됨 - 직접 확인 필요"
            new_data["announce_date"] = today_key
            ann_msg = (
                "🚨 <b>[긴급] 공고/고시/훈령/예규 변경 감지!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📋 <b>공고/고시/훈령/예규</b>\n"
                "┗ 새로운 게시글이 등록되었습니다!\n\n"
                "전체 목록: {}\n\n"
                "⚠️ 즉시 확인해 주세요!"
            ).format(ANNOUNCE_URL)
        else:
            ann_msg = (
                "✅ <b>[{}] 공고/고시/훈령/예규 변동없음</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "📋 <b>공고/고시/훈령/예규</b>\n"
                "┣ 최근 게시글:\n"
                "┃  {}\n"
                "┣ 게시일: {}\n"
                "┗ 전체 목록: {}"
            ).format(today_str, saved_title, saved_date, ANNOUNCE_URL)

        messages.append(ann_msg)

    print("전송할 메시지 수: {}".format(len(messages)))

    if messages:
        full_message = "\n\n".join(messages)
        send_telegram(full_message)

    if new_data:
        merged = last_data.copy()
        merged.update(new_data)
        save_data(merged)

    print("=== 모니터링 완료 ===")


if __name__ == "__main__":
    main()
