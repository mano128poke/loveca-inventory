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
session.headers["User-Agent"] = "Mozilla/5.0 LovecaInventorySync/1.0"


def get_page(page):
    url = BASE + "?view=text&sort=new"

    if page > 1:
        url += "&page=" + str(page)

    response = session.get(url, timeout=30)
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def extract_value(text, label, next_labels):
    pattern = (
        re.escape(label)
        + r"\s*(.*?)\s*(?="
        + "|".join(map(re.escape, next_labels))
        + r"|$)"
    )

    match = re.search(pattern, text)

    if match:
        return match.group(1).strip()

    return ""


def main():

    cards = {}

    for page in range(1, 301):

        print("取得中:", page, "ページ")

        soup = get_page(page)

        found = 0

        blocks = soup.select(
            "article, li, .searchresults__item, .card-list-item"
        )

        for block in blocks:

            text = block.get_text(" ", strip=True)

            match = re.search(
                r"カード番号\s*([A-Za-z0-9!+\-_.]+)",
                text
            )

            if not match:
                continue

            card_id = match.group(1)

            found += 1

            name = ""

            for element in block.select(
                "h2, h3, h4, .name, .card-name"
            ):

                value = element.get_text(" ", strip=True)

                if value and value != "詳しく見る":

                    name = value
                    break

            image = ""

            image_element = block.find("img")

            if image_element:

                src = image_element.get("src")

                if src:

                    image = urljoin(BASE, src)

            product = extract_value(
                text,
                "収録商品",
                [
                    "カードタイプ",
                    "作品名",
                    "参加ユニット",
                    "レアリティ",
                    "カード番号"
                ]
            )

            kind = extract_value(
                text,
                "カードタイプ",
                [
                    "作品名",
                    "参加ユニット",
                    "レアリティ",
                    "カード番号"
                ]
            )

            school = extract_value(
                text,
                "作品名",
                [
                    "参加ユニット",
                    "レアリティ",
                    "カード番号"
                ]
            )

            unit = extract_value(
                text,
                "参加ユニット",
                [
                    "レアリティ",
                    "カード番号"
                ]
            )

            rarity = extract_value(
                text,
                "レアリティ",
                [
                    "カード番号"
                ]
            )

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

        print(
            "このページ:",
            found,
            "件 / 合計:",
            len(cards),
            "件"
        )

        if page > 1 and found == 0:
            break

        time.sleep(0.2)

    result = sorted(
        cards.values(),
        key=lambda x: x["id"]
    )

    print("最終取得件数:", len(result))

    if len(result) < 2000:

        raise RuntimeError(
            "取得件数が少なすぎるため安全停止しました: "
            + str(len(result))
        )

    os.makedirs("data", exist_ok=True)

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


if __name__ == "__main__":
    main()
