import json
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


WIKI_BASE = "https://wikiwiki.jp/llocardgame/"
OFFICIAL_BASE = "https://llofficial-cardgame.com"
OUTPUT = "data/cards.json"

# Wikiへのアクセス間隔
WIKI_PAGE_DELAY = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://wikiwiki.jp/llocardgame/",
}


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


# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------

def get(url, params=None, retry=4):
    for i in range(retry):
        try:
            response = session.get(
                url,
                params=params,
                timeout=30,
            )

            # Wikiのアクセス制限
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")

                if retry_after:
                    try:
                        wait = int(retry_after)
                    except ValueError:
                        wait = 15
                else:
                    wait = 15 * (i + 1)

                print(
                    f"429 Too Many Requests: "
                    f"{wait}秒待って再試行 ({i + 1}/{retry})"
                )

                time.sleep(wait)
                continue

            response.raise_for_status()

            response.encoding = (
                response.apparent_encoding
                or response.encoding
            )

            return response

        except Exception as e:
            print(
                f"取得失敗: {url} "
                f"({i + 1}/{retry}) {e}"
            )

            if i < retry - 1:
                time.sleep(5 * (i + 1))

    return None


# ------------------------------------------------------------
# Utility
# ------------------------------------------------------------

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


# Wikiのリンクは
#   PL!-sd1-001 高坂穂乃果
# のようにカード番号＋名前になっている。
#
# そのため「リンク全体がID」という判定ではなく、
# リンク文字列の中からIDを探す。
CARD_ID_RE = re.compile(
    r"((?:PL!|LL-)[A-Za-z0-9!_-]+-\d{2,3}"
    r"(?:-[A-Za-z0-9＋+]+)?)"
)


def normalize_card_id(card_id):
    return card_id.replace("＋", "+")


def get_base_id(card_id):
    """
    PL!SP-bp2-001-P
    ↓
    PL!SP-bp2-001
    """

    card_id = normalize_card_id(card_id)

    match = re.match(
        r"^(.+-\d{2,3})(?:-[A-Za-z0-9+]+)?$",
        card_id,
    )

    if match:
        return match.group(1)

    return card_id


# ------------------------------------------------------------
# Wiki
# ------------------------------------------------------------

def parse_wiki_page(kind, work, path):
    url = urljoin(WIKI_BASE, path)

    response = get(url)

    if response is None:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    cards = []

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):

            links = tr.find_all("a")

            if not links:
                continue

            card_link = None
            card_id = None
            card_name = ""

            for link in links:
                text = clean_text(
                    link.get_text(" ", strip=True)
                )

                # ここが以前のコードとの重要な違い。
                # matchではなくsearchする。
                match = CARD_ID_RE.search(text)

                if not match:
                    continue

                card_id = normalize_card_id(
                    match.group(1)
                )

                # IDの後ろがカード名
                card_name = text[
                    match.end():
                ].strip()

                card_link = link
                break

            if card_link is None or card_id is None:
                continue

            # 商品名
            product = ""

            for link in links:
                text = clean_text(
                    link.get_text(" ", strip=True)
                )

                if text == clean_text(
                    card_link.get_text(" ", strip=True)
                ):
                    continue

                keywords = [
                    "スタートデッキ",
                    "ブースターパック",
                    "プレミアムブースター",
                    "プロモーション",
                    "PR",
                ]

                if any(
                    keyword in text
                    for keyword in keywords
                ):
                    product = text
                    break

            cards.append(
                {
                    "id": card_id,
                    "name": card_name,
                    "kind": kind,
                    "work": work,
                    "product": product,
                }
            )

    return cards


def get_wiki_cards(existing):
    result = []

    success_pages = 0

    print("")
    print("========================================")
    print("Wiki取得開始")
    print("========================================")

    for index, (kind, work, path) in enumerate(
        WIKI_PAGES,
        start=1,
    ):
        print(
            f"\nWiki {index}/{len(WIKI_PAGES)}: "
            f"{work} {kind}"
        )

        cards = parse_wiki_page(
            kind,
            work,
            path,
        )

        print(
            f"  → {len(cards)} 件"
        )

        if cards:
            success_pages += 1
            result.extend(cards)

        # Wikiへの連続アクセスを避ける
        if index < len(WIKI_PAGES):
            print(
                f"  次のページまで "
                f"{WIKI_PAGE_DELAY}秒待機"
            )
            time.sleep(WIKI_PAGE_DELAY)

    # 重複排除
    unique = {}

    for card in result:
        unique[card["id"]] = card

    result = list(unique.values())

    print("")
    print(
        f"Wiki取得件数: {len(result)}"
    )
    print(
        f"正常取得ページ: "
        f"{success_pages}/{len(WIKI_PAGES)}"
    )

    # Wikiが一時的に死んでいる場合
    # 既存のcards.jsonを絶対に消さない
    if len(result) < 100:

        if existing:
            print("")
            print(
                "Wiki取得件数が少なすぎます。"
            )
            print(
                "既存のcards.jsonを維持します。"
            )
            print(
                f"既存データ: {len(existing)} 件"
            )

            return list(existing.values())

        raise RuntimeError(
            "Wiki取得に失敗し、"
            "既存データもありません。"
        )

    return result


# ------------------------------------------------------------
# Official
# ------------------------------------------------------------

def official_search(card_id):
    url = (
        f"{OFFICIAL_BASE}/cardlist/searchresults/"
    )

    response = get(
        url,
        params={"cardno": card_id},
        retry=2,
    )

    if response is None:
        return None

    return response.text


def extract_official_cards(html, base_id):
    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    pattern = re.compile(
        r"(?:PL!|LL-)[A-Za-z0-9!_-]+-\d{2,3}"
        r"(?:-[A-Za-z0-9＋+]+)?"
    )

    found = []

    for card_id in pattern.findall(text):
        card_id = normalize_card_id(card_id)

        if get_base_id(card_id) != get_base_id(
            base_id
        ):
            continue

        found.append(
            {
                "id": card_id,
            }
        )

    unique = {}

    for card in found:
        unique[card["id"]] = card

    return list(unique.values())


def supplement_official(card):
    html = official_search(
        card["id"]
    )

    if not html:
        return []

    return extract_official_cards(
        html,
        card["id"],
    )


# ------------------------------------------------------------
# Existing
# ------------------------------------------------------------

def load_existing():
    if not os.path.exists(OUTPUT):
        return {}

    try:
        with open(
            OUTPUT,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        if not isinstance(data, list):
            return {}

        result = {}

        for card in data:
            if not isinstance(card, dict):
                continue

            card_id = card.get("id")

            if not card_id:
                continue

            result[card_id] = card

        return result

    except Exception as e:
        print(
            f"既存データ読み込み失敗: {e}"
        )

        return {}


def merge_card(old, new):
    """
    新しい値が空なら古い値を残す。
    """

    merged = dict(old)

    for key, value in new.items():

        if value in (
            None,
            "",
            [],
        ):
            continue

        merged[key] = value

    return merged


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    print("")
    print("========================================")
    print("ラブカ在庫データ同期")
    print("========================================")

    existing = load_existing()

    print(
        f"既存データ件数: {len(existing)}"
    )

    # --------------------------------------------------------
    # Wiki
    # --------------------------------------------------------

    wiki_cards = get_wiki_cards(
        existing
    )

    # 既存データを最初から保持
    final_cards = dict(existing)

    # Wiki情報を反映
    for card in wiki_cards:

        card_id = card["id"]

        if card_id in final_cards:
            final_cards[card_id] = merge_card(
                final_cards[card_id],
                card,
            )
        else:
            final_cards[card_id] = card

    print(
        f"Wiki反映後: {len(final_cards)} 件"
    )

    # --------------------------------------------------------
    # Official補完
    # --------------------------------------------------------

    print("")
    print("========================================")
    print("公式サイト補完")
    print("========================================")

    official_success = 0
    official_fail = 0

    # 新規カードを優先。
    # 既存カードを毎回919件問い合わせない。
    new_cards = [
        card
        for card in wiki_cards
        if card["id"] not in existing
    ]

    print(
        f"今回の新規カード: "
        f"{len(new_cards)} 件"
    )

    for index, card in enumerate(
        new_cards,
        start=1,
    ):

        print(
            f"[{index}/{len(new_cards)}] "
            f"{card['id']}"
        )

        official_cards = supplement_official(
            card
        )

        if official_cards:

            official_success += 1

            for official_card in official_cards:

                official_id = official_card[
                    "id"
                ]

                base = dict(
                    final_cards.get(
                        card["id"],
                        card,
                    )
                )

                base["id"] = official_id

                final_cards[official_id] = merge_card(
                    final_cards.get(
                        official_id,
                        {},
                    ),
                    base,
                )

        else:
            official_fail += 1

        # 公式サイトにも負荷をかけない
        time.sleep(0.5)

    print("")
    print(
        f"公式補完成功: "
        f"{official_success}"
    )
    print(
        f"公式補完失敗: "
        f"{official_fail}"
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    os.makedirs(
        os.path.dirname(OUTPUT),
        exist_ok=True,
    )

    cards = list(
        final_cards.values()
    )

    cards.sort(
        key=lambda x: x.get(
            "id",
            "",
        )
    )

    with open(
        OUTPUT,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            cards,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print("========================================")
    print(
        f"最終カード件数: {len(cards)}"
    )
    print(
        f"保存先: {OUTPUT}"
    )
    print("========================================")


if __name__ == "__main__":
    main()
