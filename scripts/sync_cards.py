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
        "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
})


def get_page(page):
    params = {
        "expansion": "",
        "view": "text",
        "sort": "new",
    }

    if page > 1:
        params["page"] = str(page)

    response = session.get(
        BASE,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.url, BeautifulSoup(
        response.text,
        "html.parser"
    )


def clean_text(text):
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_image(element):
    img = element.find("img")

    if not img:
        return ""

    src = (
        img.get("src")
        or img.get("data-src")
        or img.get("data-lazy-src")
        or ""
    )

    if not src:
        return ""

    return urljoin(BASE, src)


def parse_cards(soup):
    cards = {}

    # 公式サイトの検索結果本文を取得
    main = (
        soup.find("main")
        or soup.find("body")
    )

    if not main:
        return cards

    # 「カード番号」を含む要素を探す
    number_elements = main.find_all(
        string=re.compile(r"カード番号")
    )

    for number_text in number_elements:

        parent = number_text.parent

        # カード番号を抽出
        full_text = clean_text(
            parent.get_text(" ", strip=True)
        )

        match = re.search(
            r"カード番号\s*([A-Za-z0-9!＋+\-_.]+)",
            full_text
        )

        if not match:
            # 親を1段階上げて再検索
            parent = parent.parent

            if not parent:
                continue

            full_text = clean_text(
                parent.get_text(" ", strip=True)
            )

            match = re.search(
                r"カード番号\s*([A-Za-z0-9!＋+\-_.]+)",
                full_text
            )

        if not match:
            continue

        card_id = match.group(1).strip()

        # すでに取得済みならスキップ
        if card_id in cards:
            continue

        # カード番号まで含む適度な範囲を取得
        block = parent

        for _ in range(5):

            if not block:
                break

            text = clean_text(
                block.get_text(" ", strip=True)
            )

            if (
                "収録商品" in text
                and "カードタイプ" in text
                and "カード番号" in text
            ):
                break

            block = block.parent

        if not block:
            continue

        text = clean_text(
            block.get_text(" ", strip=True)
        )

        # -------------------------
        # 各項目を抽出
        # -------------------------

        def between(start, ends):
            pattern = (
                re.escape(start)
                + r"\s*(.*?)\s*(?="
                + "|".join(re.escape(x) for x in ends)
                + r"|$)"
            )

            m = re.search(pattern, text)

            if m:
                return clean_text(m.group(1))

            return ""

        product = between(
            "収録商品",
            [
                "カードタイプ",
                "作品名",
                "参加ユニット",
                "コスト",
                "スコア",
                "基本ハート",
                "レアリティ",
                "カード番号",
            ]
        )

        kind = between(
            "カードタイプ",
            [
                "作品名",
                "参加ユニット",
                "コスト",
                "スコア",
                "基本ハート",
                "レアリティ",
                "カード番号",
            ]
        )

        school = between(
            "作品名",
            [
                "参加ユニット",
                "コスト",
                "スコア",
                "基本ハート",
                "レアリティ",
                "カード番号",
            ]
        )

        unit = between(
            "参加ユニット",
            [
                "コスト",
                "スコア",
                "基本ハート",
                "レアリティ",
                "カード番号",
            ]
        )

        rarity = between(
            "レアリティ",
            [
                "カード番号",
            ]
        )

        # -------------------------
        # カード名
        # -------------------------

        name = ""

        # カード番号より前にある見出しを優先
        candidates = block.find_all(
            ["h2", "h3", "h4", "h5"]
        )

        for candidate in candidates:

            value = clean_text(
                candidate.get_text(" ", strip=True)
            )

            if not value:
                continue

            if value in (
                "Card List",
                "カードを探す",
                "詳しく見る",
                "検索条件を変更",
            ):
                continue

            if value.startswith("検索結果"):
                continue

            name = value
            break

        # 見出しが取れなかった場合
        if not name:

            lines = [
                clean_text(x)
                for x in block.stripped_strings
            ]

            for line in lines:

                if not line:
                    continue

                if line in (
                    "収録商品",
                    "カードタイプ",
                    "作品名",
                    "参加ユニット",
                    "カード番号",
                    "詳しく見る",
                ):
                    continue

                if (
                    "カード番号" in line
                    or "収録商品" in line
                    or "カードタイプ" in line
                ):
                    continue

                name = line
                break

        # -------------------------
        # 画像
        # -------------------------

        image = get_image(block)

        cards[card_id] = {
            "id": card_id,
            "name": name,
            "product": product,
            "rarity": rarity,
            "school": school,
            "unit": unit,
            "kind": kind,
            "image": image,
            "required": 1
        }

    return cards


def main():

    cards = {}

    MAX_PAGES = 300

    for page in range(1, MAX_PAGES + 1):

        print("取得中:", page, "ページ")

        try:
            final_url, soup = get_page(page)

        except Exception as e:
            print("ページ取得エラー:", e)
            break

        found_cards = parse_cards(soup)

        before = len(cards)

        cards.update(found_cards)

        found = len(cards) - before

        print(
            "このページ:",
            found,
            "件 / 合計:",
            len(cards),
            "件"
        )

        # 2ページ目以降で新規カードがなくなったら終了
        if page > 1 and found == 0:
            print("新しいカードがないため終了します")
            break

        time.sleep(0.5)

    result = sorted(
        cards.values(),
        key=lambda x: x["id"]
    )

    print()
    print("==============================")
    print("最終取得件数:", len(result))
    print("==============================")

    # 安全装置
    if len(result) < 2000:
        raise RuntimeError(
            "取得件数が少なすぎるため安全停止しました: "
            + str(len(result))
            + " 件"
        )

    os.makedirs(
        os.path.dirname(OUTPUT),
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

    print("カードデータを更新しました")
    print("保存先:", OUTPUT)


if __name__ == "__main__":
    main()
