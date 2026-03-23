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

        text = soup.get_text()
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        un_1267 = "확인 불가"
        un_1718 = "확인 불가"
        un_1988 = "확인 불가"
        un_1737 = "확인 불가"
        un_total = "확인 불가"

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
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        content = soup.get_text()
        page_hash = hashlib.md5(content.encode()).hexdigest()

        posts = []

        rows = soup.select("table tbody tr")
        for row in rows[:3]:
            cells = row.find_all("td")
            if len(cells) >= 2:
                title = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                date = cells[-1].get_text(strip=True) if cells else ""
                if title:
                    posts.append({"title": title, "date": date})

        if not posts:
            items = soup.select(".board-list li, .list-wrap li")
            for item in items[:3]:
                text = item.get_text(strip=True)
                if text:
                    posts.append({"title": text[:60], "date": ""})

        latest_date = posts[0]["date"] if posts else "확인 불가"
        return page_hash, posts, latest_date
    except Exception as e:
        print("공고/고시 페이지 오류: {}".format(e))
        return None, [], "확인 불가"


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
