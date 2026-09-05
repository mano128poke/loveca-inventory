import json
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ============================================================
# 設定
# ============================================================

WIKI_BASE = "https://wikiwiki.jp/llocardgame/"
OFFICIAL_BASE = "https://llofficial-cardgame.com"

OUTPUT = "data/cards.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/139.0 Safari/537.36"
    )
}


# Wikiのカード一覧
WIKI_PAGES = [
    ("member", "μ's", "data/メンバーカード/μ's"),
    ("member", "Aqours", "data/メンバーカード/Aqours"),
    ("member", "虹ヶ咲", "data/メンバーカード/虹ヶ咲"),
    ("member", "Liella!", "data/メンバーカード/Liella!"),
    ("member", "蓮ノ空", "data/メンバーカード/蓮ノ空"),
    ("member", "その他", "data/メンバーカード/その他"),

    ("live", "μ's", "data/ライブカード/μ's"),
    ("live", "Aqours", "data/ライブカード/Aqours"),
    ("live", "虹ヶ咲", "data/ライブカード/虹ヶ咲"),
    ("live", "Liella!", "data/ライブカード/Liella!"),
    ("live", "蓮ノ空", "data/ライブカード/蓮ノ空"),
    ("live", "その他", "data/ライブカード/その他"),
]


session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# 共通
# ============================================================

def get(url, params=None, retry=3):
    for i in range(retry):
        try:
            r = session.get(
                url,
                params=params,
                timeout=30,
            )
            r.raise_for_status()
            return r

        except Exception as e:
            print(f"取得失敗 {i + 1}/{retry}: {url}")
            print(e)

            if i < retry - 1:
                time.sleep(2)

    return None


# ============================================================
# Wiki取得
# ============================================================

CARD_ID_RE = re.compile(
    r"^(PL![A-Za-z0-9!_\-]+-\d{2,3}(?:-[A-Za-z0-9＋+]+)?|LL-[A-Za-z0-9!_\-]+-\d{2,3}(?:-[A-Za-z0-9＋+]+)?)$"
)


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_wiki_page(kind, work, path):
    url = urljoin(WIKI_BASE, path)

    print(f"Wiki取得: {work} / {kind}")
    print(url)

    r = get(url)

    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    cards = []

    # PukiWikiの表を調べる
    for table in soup.find_all("table"):

        for tr in table.find_all("tr"):

            cells = tr.find_all(["td", "th"])

            if not cells:
                continue

            links = tr.find_all("a")

            card_link = None

            for a in links:
                text = clean_text(a.get_text(" ", strip=True))

                if CARD_ID_RE.match(text):
                    card_link = a
                    break

            if not card_link:
                continue

            card_text = clean_text(card_link.get_text(" ", strip=True))

            # 例:
            # PL!-sd1-001 高坂穂乃果
            parts = card_text.split(" ", 1)

            card_id = parts[0]

            if not CARD_ID_RE.match(card_id):
                continue

            name = parts[1].strip() if len
