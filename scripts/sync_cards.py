import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


# =========================================================
# 基本設定
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "cards.json"

WIKI_BASE = "https://wikiwiki.jp/llocardgame/"

# LLOCG_DB
LLOCG_API = "https://api.github.com/repos/wlt233/llocg_db/git/trees/master"
LLOCG_RAW = "https://raw.githubusercontent.com/wlt233/llocg_db/master/"

WIKI_PAGE_DELAY = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "loveca-inventory-sync/1.0 "
        "https://github.com/mano128poke/loveca-inventory"
    )
}


# =========================================================
# Wikiページ
# =========================================================

WIKI_PAGES = [
    # メンバーカード
    ("μ's", "member", "data/メンバーカード/μ's"),
    ("Aqours", "member", "data/メンバーカード/Aqours"),
    ("虹ヶ咲", "member", "data/メンバーカード/虹ヶ咲"),
    ("Liella!", "member", "data/メンバーカード/Liella!"),
    ("蓮ノ空", "member", "data/メンバーカード/蓮ノ空"),
    ("その他", "member", "data/メンバーカード/その他"),

    # ライブカード
    ("μ's", "live", "data/ライブカード/μ's"),
    ("Aqours", "live", "data/ライブカード/Aqours"),
    ("虹ヶ咲", "live", "data/ライブカード/虹ヶ咲"),
    ("Liella!", "live", "data/ライブカード/Liella!"),
    ("蓮ノ空", "live", "data/ライブカード/蓮ノ空"),
    ("その他", "live", "data/ライブカード/その他"),
]


# Wikiの基本カード番号
#
# 例:
# PL!-sd1-001
# PL!N-bp1-001
# PL!SP-bp1-003
# LL-PR-004
#
CARD_ID_RE = re.compile(
    r"(?:PL![A-Za-z]*|LL)-"
    r"(?:[A-Za-z0-9]+)-"
    r"\d{3}"
    r"(?:-E\d{2})?",
    re.IGNORECASE,
)


# =========================================================
# HTTP
# =========================================================

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def request_with_retry(
    session,
    url,
    retries=5,
    delay=5,
    params=None,
):
    for attempt in range(retries):
        try:
            response = session.get(
                url,
                params=params,
                timeout=30,
            )

            if response.status_code == 200:
                return response

            if response.status_code == 429:
                wait = delay * (attempt + 1)
                print(
                    f"429 Too Many Requests "
                    f"→ {wait}秒待機"
                )
                time.sleep(wait)
                continue

            print(
                f"HTTP {response.status_code}: "
                f"{url}"
            )

        except requests.RequestException as e:
            print(
                f"通信エラー: {e}"
            )

        time.sleep(delay)

    return None


# =========================================================
# 既存データ
# =========================================================

def load_existing():
    if not DATA_FILE.exists():
        return {}

    try:
        with open(
            DATA_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        if isinstance(data, list):
            return {
                str(card.get("id")): card
                for card in data
                if card.get("id")
            }

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(
            f"既存データ読み込み失敗: {e}"
        )

    return {}


# =========================================================
# Wiki
# =========================================================

def parse_wiki_page(
    html,
    work,
    kind,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    cards = []

    for a in soup.find_all("a"):
        text = " ".join(
            a.stripped_strings
        )

        match = CARD_ID_RE.search(text)

        if not match:
            continue

        card_id = match.group(0)

        name = text[
            match.end():
        ].strip()

        if not name:
            name = text

        cards.append({
            "id": card_id,
            "name": name,
            "kind": kind,
            "work": work,
            "product": "",
        })

    return cards


def fetch_wiki_cards(session):
    all_cards = {}

    print("")
    print(
        "========================================"
    )
    print("Wikiカード一覧取得")
    print(
        "========================================"
    )

    for index, (
        work,
        kind,
        page,
    ) in enumerate(
        WIKI_PAGES,
        1,
    ):
        url = WIKI_BASE + page

        print(
            f"[Wiki {index}/{len(WIKI_PAGES)}] "
            f"{work} / {kind}"
        )

        response = request_with_retry(
            session,
            url,
        )

        if not response:
            print("  → 取得失敗")
            continue

        cards = parse_wiki_page(
            response.text,
            work,
            kind,
        )

        print(
            f"  → {len(cards)}件"
        )

        for card in cards:
            all_cards[
                card["id"]
            ] = card

        time.sleep(
            WIKI_PAGE_DELAY
        )

    return all_cards


# =========================================================
# LLOCG_DB画像
# =========================================================

def normalize_base_id(card_id):
    """
    カード番号から基本番号を取り出す。

    PL!N-bp1-001-P
        ↓
    PL!N-bp1-001

    PL!-sd1-001-SD
        ↓
    PL!-sd1-001
    """

    if not card_id:
        return ""

    card_id = card_id.strip()

    match = CARD_ID_RE.search(
        card_id
    )

    if match:
        return match.group(0)

    return card_id


def get_rarity_from_filename(filename):
    """
    例:

   
