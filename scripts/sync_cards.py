import os
import re
import json
import time
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup


# ============================================================
# 設定
# ============================================================

WIKI_BASE = "https://wikiwiki.jp/llocardgame/"
OFFICIAL_BASE = "https://llofficial-cardgame.com/cardlist/searchresults/"

OUTPUT = "data/cards.json"

# 非公式Wikiのカードデータページ
WIKI_PAGES = [
    # メンバーカード
    "data/メンバーカード/μ's",
    "data/メンバーカード/Aqours",
    "data/メンバーカード/虹ヶ咲",
    "data/メンバーカード/Liella!",
    "data/メンバーカード/蓮ノ空",
    "data/メンバーカード/その他",

    # ライブカード
    "data/ライブカード/μ's",
    "data/ライブカード/Aqours",
    "data/ライブカード/虹ヶ咲",
    "data/ライブカード/Liella!",
    "data/ライブカード/蓮ノ空",
    "data/ライブカード/その他",
]

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ja-JP,ja;q=0.9"
})


# ============================================================
# 共通
# ============================================================

def request_page(url):
    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def get_rarity(card_id):
    """
    カード番号末尾からレアリティを取得。

    例:
    PL!-bp7-001-R
    PL!-bp7-001-P
    PL!-bp7-001-R＋
    """

    parts = card_id.split("-")

    if not parts:
        return ""

    last = parts[-1]

    # Wikiの通常カード番号にはレアリティがない場合がある
    if re.fullmatch(
        r"(?:R|SR|L|SEC|P|PR|SD|PE|SRE|RM|SECL|SIR|SP|＋|\+)+",
        last
    ):
        return last

    return ""


def is_card_id(value):
    """
    ラブカのカード番号らしい文字列か判定。
    """

    value = value.strip()

    # 通常カード
    if re.match(
        r"^(PL!|LL-)[A-Za-z0-9!＋+\-_.]+$",
        value
    ):
        return True

    return False


# ============================================================
# Wiki
# ============================================================

def parse_wiki_card_cell(text):
    """
    Wikiの

    PL!-bp5-006 西木野真姫

    のようなセルから
    カード番号とカード名を取り出す。
    """

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    # 先頭のカード番号を取得
    match = re.match(
        r"^((?:PL!|LL-)[A-Za-z0-9!＋+\-_.]+)\s+(.+)$",
        text
    )

    if not match:
        return None

    card_id = match.group(1).strip()
    name = match.group(2).strip()

    if not is_card_id(card_id):
        return None

    return card_id, name


def parse_wiki_page(soup):
    """
    Wikiの表からカードを取得する。
    """

    cards = {}

    for table in soup.find_all("table"):

        rows = table.find_all("tr")

        for row in rows:

            cells = row.find_all(
                ["th", "td"]
            )

            if not cells:
                continue

            values = [
                cell.get_text(
                    " ",
                    strip=True
                )
                for cell in cells
            ]

            if not values:
                continue

            # 先頭セルに
            # カード番号 / カード名
            # が入っている
            parsed = parse_wiki_card_cell(
                values[0]
            )

            if not parsed:
                continue

            card_id, name = parsed

            # 表の最後に「初登場セット」がある
            product = ""

            if len(values) >= 2:
                # 末尾の値を商品名として扱う
                candidate = values[-1]

                if candidate not in (
                    "初登場セット",
                    "カード名",
                    "カード番号/カード名"
                ):
                    product = candidate

            # メンバー / ライブを判定
            page_text = soup.get_text(
                " ",
                strip=True
            )

            if "メンバーカード" in page_text:
                kind = "メンバー"

            elif "ライブカード" in page_text:
                kind = "ライブ"

            else:
                kind = ""

            cards[card_id] = {
                "id": card_id,
                "name": name,
                "product": product,
                "rarity": get_rarity(card_id),
                "school": "",
                "unit": "",
                "kind": kind,
                "image": "",
                "required": 1
            }

    return cards


def get_wiki_cards():
    """
    非公式Wikiからカード一覧を取得。
    """

    cards = {}

    print()
    print("==============================")
    print("非公式Wikiからカード一覧を取得")
    print("==============================")

    success_pages = 0

    for page_path in WIKI_PAGES:

        url = urljoin(
            WIKI_BASE,
            page_path
        )

        print(
            "Wiki取得:",
            page_path
        )

        try:

            soup = request_page(url)

            page_cards = parse_wiki_page(
                soup
            )

            print(
                "  →",
                len(page_cards),
                "件"
            )

            cards.update(
                page_cards
            )

            if page_cards:
                success_pages += 1

        except Exception as e:

            print(
                "  → 取得失敗:",
                e
            )

        time.sleep(0.3)

    print()
    print(
        "Wiki取得完了:",
        len(cards),
        "件"
    )

    return cards


# ============================================================
# 公式サイト
# ============================================================

def official_search(card_id):
    """
    公式サイトでカード番号を検索。

    公式サイトが取得できない場合は None。
    """

    try:

        params = {
            "view": "text",
            "keyword1": card_id,
            "keyword_type1": "and"
        }

        response = session.get(
            OFFICIAL_BASE,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        return BeautifulSoup(
            response.text,
            "html.parser"
        )

    except Exception as e:

        print(
            "公式検索失敗:",
            card_id,
            e
        )

        return None


def parse_official_card(
    soup,
    card_id
):
    """
    公式サイトからカード情報を補完。

    公式側のHTML仕様が変わっていても、
    取得できなければNoneを返して
    Wiki/既存データを維持する。
    """

    if soup is None:
        return None

    text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # カード番号がページ
