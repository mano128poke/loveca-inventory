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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
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


# ============================================================
# HTTP
# ============================================================

def get(url, params=None, retry=3):
    for i in range(retry):
        try:
            response = session.get(
                url,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            return response

        except Exception as e:
            print(f"取得失敗 {i + 1}/{retry}: {url}")
            print(f"  {e}")

            if i < retry - 1:
                time.sleep(2)

    return None


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


# ============================================================
# Wiki
# ============================================================

CARD_ID_RE = re.compile(
    r"^(PL!|LL-).+-\d{2,3}(?:-[A-Za-z0-9＋+]+)?$"
)


def parse_wiki_page(kind, work, path):
    url = urljoin(WIKI_BASE, path)

    print(f"Wiki取得: {work} / {kind}")
    print(f"  {url}")

    response = get(url)

    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    cards = []

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            links = tr.find_all("a")

            if not links:
                continue

            card_link = None

            for link in links:
                text = clean_text(
                    link.get_text(" ", strip=True)
                )

                if CARD_ID_RE.match(text):
                    card_link = link
                    break

            if card_link is None:
                continue

            card_text = clean_text(
                card_link.get_text(" ", strip=True)
            )

            parts = card_text.split(" ", 1)

            card_id = parts[0]

            if not CARD_ID_RE.match(card_id):
                continue

            if len(parts) > 1:
                name = parts[1].strip()
            else:
                name = ""

            product = ""

            for link in links:
                text = clean_text(
                    link.get_text(" ", strip=True)
                )

                if text == card_text:
                    continue

                if any(
                    keyword in text
                    for keyword in [
                        "スタートデッキ",
                        "ブースターパック",
                        "プレミアムブースター",
                        "プロモーション",
                    ]
                ):
                    product = text

            cards.append({
                "id": card_id,
                "name": name,
                "kind": kind,
                "work": work,
                "product": product,
            })

    return cards


def get_wiki_cards():
    result = []

    for kind, work, path in WIKI_PAGES:
        cards = parse_wiki_page(
            kind,
            work,
            path,
        )

        print(f"  → {len(cards)} 件")

        result.extend(cards)

    unique = {}

    for card in result:
        unique[card["id"]] = card

    result = list(unique.values())

    print()
    print("=" * 40)
    print(f"Wiki取得件数: {len(result)}")
    print("=" * 40)

    if len(result) < 100:
        raise RuntimeError(
            f"Wiki取得件数が少なすぎるため安全停止しました: "
            f"{len(result)} 件"
        )

    return result


# ============================================================
# 公式サイト
# ============================================================

def official_search(card_id):
    url = (
        f"{OFFICIAL_BASE}"
        "/cardlist/searchresults/"
    )

    params = {
        "cardno": card_id,
    }

    print(f"  公式検索: {card_id}")

    response = get(
        url,
        params=params,
    )

    if response is None:
        return None

    return response.text


def normalize_card_id(card_id):
    return card_id.replace("＋", "+")


def get_base_id(card_id):
    """
    レアリティ部分を除いたカード番号を返す。

    例:
      PL!SP-bp7-001-R
      ↓
      PL!SP-bp7-001
    """

    match = re.match(
        r"^(.+-\d{2,3})(?:-[A-Za-z0-9＋+]+)?$",
        card_id,
    )

    if match:
        return normalize_card_id(match.group(1))

    return normalize_card_id(card_id)


def extract_official_cards(html, base_id):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    pattern = re.compile(
        r"(?:PL!|LL-)"
        r"[A-Za-z0-9!_\-]+"
        r"-\d{2,3}"
        r"(?:-[A-Za-z0-9＋+]+)?"
    )

    found = []

    for card_id in pattern.findall(text):
        card_id = normalize_card_id(card_id)

        if card_id not in found:
            found.append(card_id)

    target = get_base_id(base_id)

    result = []

    for card_id in found:
        if get_base_id(card_id) == target:
            result.append({
                "id": card_id,
            })

    unique = {}

    for card in result:
        unique[card["id"]] = card

    return list(unique.values())


def supplement_official(card):
    base_id = card["id"]

    html = official_search(base_id)

    if not html:
        return []

    official_cards = extract_official_cards(
        html,
        base_id,
    )

    result = []

    for official_card in official_cards:
        new_card = dict(card)

        new_card["id"] = official_card["id"]

        result.append(new_card)

    return result


# ============================================================
# 既存データ
# ============================================================

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
        print(f"既存JSON読み込み失敗: {e}")
        return {}


def merge_cards(old, new):
    result = dict(old)

    for key, value in new.items():
        if value not in ("", None, []):
            result[key] = value

    return result


# ============================================================
# メイン
# ============================================================

def main():
    print("=" * 50)
    print("ラブカ カード同期開始")
    print("=" * 50)

    existing = load_existing()

    print(f"既存データ件数: {len(existing)}")

    # --------------------------------------------------------
    # Wiki
    # --------------------------------------------------------

    wiki_cards = get_wiki_cards()

    # --------------------------------------------------------
    # 公式
    # --------------------------------------------------------

    final_cards = {}

    official_success = 0
    official_failed = 0
    variant_count = 0

    for index, card in enumerate(
        wiki_cards,
        1,
    ):
        print(
            f"[{index}/{len(wiki_cards)}] "
            f"{card['id']} {card['name']}"
        )

        official_cards = supplement_official(
            card
        )

        if official_cards:
            official_success += 1
            variant_count += len(official_cards)

            for official_card in official_cards:
                card_id = official_card["id"]

                old = existing.get(
                    card_id,
                    {},
                )

                final_cards[card_id] = merge_cards(
                    old,
                    official_card,
                )

        else:
            official_failed += 1

            # 公式取得失敗でもWikiデータを保存
            card_id = card["id"]

            old = existing.get(
                card_id,
                {},
            )

            final_cards[card_id] = merge_cards(
                old,
                card,
            )

        time.sleep(0.15)

    # --------------------------------------------------------
    # 既存データを保持
    # --------------------------------------------------------

    for card_id, card in existing.items():
        if card_id not in final_cards:
            final_cards[card_id] = card

    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------

    output = list(final_cards.values())

    output.sort(
        key=lambda card: card.get(
            "id",
            "",
        )
    )

    output_dir = os.path.dirname(OUTPUT)

    if output_dir:
        os.makedirs(
            output_dir,
            exist_ok=True,
        )

    with open(
        OUTPUT,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------------
    # 結果
    # --------------------------------------------------------

    print()
    print("=" * 50)
    print("同期完了")
    print("=" * 50)
    print(f"Wiki基本カード: {len(wiki_cards)}")
    print(f"公式取得成功: {official_success}")
    print(f"公式取得失敗: {official_failed}")
    print(f"公式バリエーション: {variant_count}")
    print(f"最終カード件数: {len(output)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
