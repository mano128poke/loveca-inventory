import os
import re
import json
import time
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE = "https://llofficial-cardgame.com/cardlist/searchresults/"
OUTPUT = "data/cards.json"

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


def get_page(page):

    params = {
        "view": "text",
        "sort": "new"
    }

    if page > 1:
        params["page"] = str(page)

    response = session.get(
        BASE,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    return soup


def parse_cards(soup):

    cards = {}

    # ページ全体を改行区切りのテキストにする
    text = soup.get_text(
        "\n",
        strip=True
    )

    # 空行を除去
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # 公式サイトでは基本的に
    #
    # カード名
    # 収録商品
    # 商品名
    # カードタイプ
    # カードタイプ名
    # カード番号
    # カード番号
    #
    # の順番になっている
    #
    # これを直接解析する

    for i in range(len(lines) - 5):

        if lines[i + 1] != "収録商品":
            continue

        if lines[i + 3] != "カードタイプ":
            continue

        if lines[i + 5] != "カード番号":
            continue

        name = lines[i]
        product = lines[i + 2]
        kind = lines[i + 4]

        if i + 6 >= len(lines):
            continue

        card_id = lines[i + 6]

        # カード番号らしいものだけ採用
        if not re.match(
            r"^[A-Za-z0-9!＋+\-_.]+$",
            card_id
        ):
            continue

        # 明らかな誤検出を除外
        if name in (
            "カードを探す",
            "検索結果",
            "全てのカード",
            "検索条件を変更",
            "詳しく見る"
        ):
            continue

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


def get_rarity(card_id):

    # 例:
    # PL!S-bp7-001-R
    # PL!S-bp7-001-P
    # PL!S-bp7-001-R＋
    # LL-PR-001-PR

    parts = card_id.split("-")

    if not parts:
        return ""

    rarity = parts[-1]

    return rarity


def find_images(soup, cards):

    # カード番号が含まれるリンクや要素を探して
    # その周辺にある画像を取得する

    for card_id in cards:

        elements = soup.find_all(
            string=re.compile(
                re.escape(card_id)
            )
        )

        for element in elements:

            parent = element.parent

            # 最大10階層まで上へ探す
            for _ in range(10):

                if not parent:
                    break

                img = parent.find("img")

                if img:

                    src = (
                        img.get("src")
                        or img.get("data-src")
                        or img.get("data-lazy-src")
                        or ""
                    )

                    if src:

                        cards[card_id]["image"] = urljoin(
                            BASE,
                            src
                        )

                        break

                parent = parent.parent

            if cards[card_id]["image"]:
                break

    return cards


def main():

    cards = {}

    MAX_PAGES = 300

    for page in range(
        1,
        MAX_PAGES + 1
    ):

        print(
            "取得中:",
            page,
            "ページ"
        )

        try:

            soup = get_page(page)

        except Exception as e:

            print(
                "ページ取得エラー:",
                e
            )

            break

        page_cards = parse_cards(
            soup
        )

        # 画像も取得
        page_cards = find_images(
            soup,
            page_cards
        )

        before = len(cards)

        cards.update(
            page_cards
        )

        found = len(cards) - before

        print(
            "このページ:",
            found,
            "件 / 合計:",
            len(cards),
            "件"
        )

        # 2ページ目以降でカードがなくなったら終了
        if page > 1 and found == 0:

            print(
                "新しいカードがないため終了します"
            )

            break

        time.sleep(0.3)

    result = sorted(
        cards.values(),
        key=lambda x: x["id"]
    )

    print()
    print("==============================")
    print(
        "最終取得件数:",
        len(result)
    )
    print("==============================")

    # 安全装置
    if len(result) < 2000:

        raise RuntimeError(
            "取得件数が少なすぎるため安全停止しました: "
            + str(len(result))
            + " 件"
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

    print(
        "カードデータを更新しました"
    )

    print(
        "保存先:",
        OUTPUT
    )


if __name__ == "__main__":
    main()
