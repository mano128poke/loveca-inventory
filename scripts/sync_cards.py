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

# Wikiの「各種データ」に実際に存在するページ
WIKI_PAGES = [
    # メンバーカード
    ("data/メンバーカード/μ's", "メンバー"),
    ("data/メンバーカード/Aqours", "メンバー"),
    ("data/メンバーカード/虹ヶ咲", "メンバー"),
    ("data/メンバーカード/Liella!", "メンバー"),
    ("data/メンバーカード/蓮ノ空", "メンバー"),
    ("data/メンバーカード/その他", "メンバー"),

    # ライブカード
    ("data/ライブカード/μ's", "ライブ"),
    ("data/ライブカード/Aqours", "ライブ"),
    ("data/ライブカード/虹ヶ咲", "ライブ"),
    ("data/ライブカード/Liella!", "ライブ"),
    ("data/ライブカード/蓮ノ空", "ライブ"),
    ("data/ライブカード/その他", "ライブ"),
]


# ============================================================
# HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
})


def get_soup(url):
    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


# ============================================================
# カード番号
# ============================================================

CARD_ID_RE = re.compile(
    r"^(PL![A-Za-z0-9!＋+\-_.]+|LL-[A-Za-z0-9!＋+\-_.]+)"
    r"(?:\s+)(.+)$"
)


def parse_card_text(text):
    """
    例:

    PL!-sd1-001 高坂穂乃果

    ↓

    card_id = PL!-sd1-001
    name    = 高坂穂乃果
    """

    if not text:
        return None

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    match = CARD_ID_RE.match(
        text
    )

    if not match:
        return None

    card_id = match.group(1).strip()
    name = match.group(2).strip()

    if not card_id or not name:
        return None

    # ヘッダー等を除外
    if name in (
        "カード名",
        "カード番号/カード名",
    ):
        return None

    return card_id, name


# ============================================================
# レアリティ
# ============================================================

def get_rarity(card_id):
    """
    Wiki側のカード番号にレアリティが含まれている場合のみ取得。
    """

    parts = card_id.split("-")

    if len(parts) < 2:
        return ""

    last = parts[-1]

    if re.fullmatch(
        r"(?:R|SR|L|SEC|P|PR|SD|PE|SRE|RM|SECL|SIR|SP|＋|\+)+",
        last
    ):
        return last

    return ""


# ============================================================
# Wiki解析
# ============================================================

def parse_wiki_page(soup, kind):
    """
    Wikiページ内のリンクからカード番号を取得。

    実際のWikiでは

    [[PL!-sd1-001 高坂穂乃果]]

    のようなリンクになっているため、
    tableのセル位置に依存しない。
    """

    cards = {}

    # --------------------------------------------------------
    # まずリンクを探す
    # --------------------------------------------------------

    for link in soup.find_all("a"):

        text = link.get_text(
            " ",
            strip=True
        )

        parsed = parse_card_text(
            text
        )

        if not parsed:
            continue

        card_id, name = parsed

        # カード番号として明らかにおかしいものを除外
        if not (
            card_id.startswith("PL!")
            or card_id.startswith("LL-")
        ):
            continue

        # ----------------------------------------------------
        # 収録商品
        # ----------------------------------------------------

        product = ""

        row = link.find_parent("tr")

        if row:

            cells = row.find_all(
                ["td", "th"]
            )

            if cells:

                # Wikiの表では最後のセルが
                # 初登場セット
                last_cell = cells[-1]

                product = last_cell.get_text(
                    " ",
                    strip=True
                )

                if product in (
                    "初登場セット",
                    "カード番号/カード名",
                ):
                    product = ""

        cards[card_id] = {
            "id": card_id,
            "name": name,
            "product": product,
            "rarity": get_rarity(card_id),
            "school": "",
            "unit": "",
            "kind": kind,
            "image": "",
            "required": 1,
        }

    return cards


def get_wiki_cards():
    """
    非公式Wikiから全カードを取得。
    """

    cards = {}

    print()
    print("==============================")
    print("非公式Wiki取得開始")
    print("==============================")

    for page_path, kind in WIKI_PAGES:

        url = urljoin(
            WIKI_BASE,
            page_path
        )

        print()
        print(
            "Wiki:",
            url
        )

        try:

            soup = get_soup(
                url
            )

            page_cards = parse_wiki_page(
                soup,
                kind
            )

            print(
                "取得:",
                len(page_cards),
                "件"
            )

            cards.update(
                page_cards
            )

        except Exception as e:

            print(
                "取得失敗:",
                e
            )

        time.sleep(0.5)

    print()
    print("==============================")
    print(
        "Wiki合計:",
        len(cards),
        "件"
    )
    print("==============================")

    return cards


# ============================================================
# 公式サイト補完
# ============================================================

def official_search(card_id):

    try:

        params = {
            "view": "text",
            "keyword1": card_id,
            "keyword_type1": "and",
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
            "公式取得失敗:",
            card_id,
            str(e)
        )

        return None


def parse_official_card(
    soup,
    card_id
):

    if soup is None:
        return None

    text = soup.get_text(
        "\n",
        strip=True
    )

    if card_id not in text:
        return None

    result = {}

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # --------------------------------------------------------
    # 既存形式の解析
    # --------------------------------------------------------

    for i in range(
        len(lines) - 6
    ):

        if lines[i + 1] != "収録商品":
            continue

        if lines[i + 3] != "カードタイプ":
            continue

        if lines[i + 5] != "カード番号":
            continue

        if lines[i + 6] != card_id:
            continue

        result["name"] = lines[i]
        result["product"] = lines[i + 2]
        result["kind"] = lines[i + 4]

        break

    # --------------------------------------------------------
    # 画像
    # --------------------------------------------------------

    for img in soup.find_all("img"):

        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
            or ""
        )

        if not src:
            continue

        alt = img.get(
            "alt",
            ""
        )

        # 画像周辺にカード番号が存在する場合
        parent_text = ""

        parent = img.parent

        if parent:
            parent_text = parent.get_text(
                " ",
                strip=True
            )

        if (
            card_id in alt
            or card_id in parent_text
        ):

            result["image"] = urljoin(
                OFFICIAL_BASE,
                src
            )

            break

    return result


def supplement_official(cards):
    """
    公式サイトから情報を補完。

    公式サイト側で取得できないカードは
    Wiki側のデータを維持する。
    """

    print()
    print("==============================")
    print("公式サイト補完開始")
    print("==============================")

    total = len(cards)

    success = 0
    failed = 0

    for index, card_id in enumerate(
        list(cards.keys()),
        start=1
    ):

        print(
            f"[{index}/{total}]",
            card_id
        )

        soup = official_search(
            card_id
        )

        official = parse_official_card(
            soup,
            card_id
        )

        if official:

            for key, value in official.items():

                if value:
                    cards[card_id][key] = value

            success += 1

        else:

            failed += 1

        # サーバー負荷軽減
        time.sleep(0.2)

    print()
    print(
        "公式補完成功:",
        success
    )

    print(
        "公式補完失敗:",
        failed
    )

    return cards


# ============================================================
# 既存データ
# ============================================================

def load_existing():

    if not os.path.exists(
        OUTPUT
    ):
        return {}

    try:

        with open(
            OUTPUT,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            list
        ):
            return {}

        result = {}

        for card in data:

            if not isinstance(
                card,
                dict
            ):
                continue

            card_id = card.get(
                "id"
            )

            if card_id:
                result[card_id] = card

        print(
            "既存データ:",
            len(result),
            "件"
        )

        return result

    except Exception as e:

        print(
            "既存データ読み込み失敗:",
            e
        )

        return {}


# ============================================================
# マージ
# ============================================================

def merge_cards(
    existing,
    new_cards
):

    merged = {}

    # 既存データを保持
    for card_id, card in existing.items():

        merged[card_id] = dict(
            card
        )

    # 新規データを反映
    for card_id, new_card in new_cards.items():

        if card_id not in merged:

            merged[card_id] = dict(
                new_card
            )

            continue

        old_card = merged[card_id]

        for key, value in new_card.items():

            # 空データで既存情報を消さない
            if value in (
                "",
                None,
                [],
            ):
                continue

            old_card[key] = value

        merged[card_id] = old_card

    return merged


# ============================================================
# 保存
# ============================================================

def save_cards(cards):

    result = sorted(
        cards.values(),
        key=lambda x: x.get(
            "id",
            ""
        )
    )

    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("========================================")
    print("ラブカ カードデータ同期")
    print("========================================")

    # --------------------------------------------------------
    # 既存データ
    # --------------------------------------------------------

    existing = load_existing()

    # --------------------------------------------------------
    # ① Wiki
    # --------------------------------------------------------

    wiki_cards = get_wiki_cards()

    # 0件なら絶対に上書きしない
    if len(wiki_cards) == 0:

        raise RuntimeError(
            "Wikiからカードを1件も取得できませんでした。"
            "既存データは変更していません。"
        )

    # 少なすぎる場合も停止
    if len(wiki_cards) < 100:

        raise RuntimeError(
            "Wiki取得件数が少なすぎます: "
            + str(len(wiki_cards))
            + " 件"
        )

    # --------------------------------------------------------
    # ② 公式補完
    # --------------------------------------------------------

    wiki_cards = supplement_official(
        wiki_cards
    )

    # --------------------------------------------------------
    # ③ 既存データと統合
    # --------------------------------------------------------

    merged = merge_cards(
        existing,
        wiki_cards
    )

    # --------------------------------------------------------
    # ④ 保存
    # --------------------------------------------------------

    result = save_cards(
        merged
    )

    # --------------------------------------------------------
    # 結果
    # --------------------------------------------------------

    print()
    print("========================================")
    print(
        "Wiki取得件数:",
        len(wiki_cards)
    )

    print(
        "既存データ件数:",
        len(existing)
    )

    print(
        "最終カード件数:",
        len(result)
    )

    print("========================================")

    print(
        "カードデータを更新しました:"
        ,
        OUTPUT
    )


if __name__ == "__main__":
    main()
