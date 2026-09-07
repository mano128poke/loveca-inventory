import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "cards.json"

WIKI_BASE = "https://wikiwiki.jp/llocardgame/"
LLOCG_API = "https://api.github.com/repos/wlt233/llocg_db/git/trees/master"
LLOCG_RAW = "https://raw.githubusercontent.com/wlt233/llocg_db/master/"

WIKI_PAGE_DELAY = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 loveca-inventory-sync/1.0 "
        "https://github.com/mano128poke/loveca-inventory"
    )
}


WIKI_PAGES = [
    ("μ's", "member", "data/メンバーカード/μ's"),
    ("Aqours", "member", "data/メンバーカード/Aqours"),
    ("虹ヶ咲", "member", "data/メンバーカード/虹ヶ咲"),
    ("Liella!", "member", "data/メンバーカード/Liella!"),
    ("蓮ノ空", "member", "data/メンバーカード/蓮ノ空"),
    ("その他", "member", "data/メンバーカード/その他"),

    ("μ's", "live", "data/ライブカード/μ's"),
    ("Aqours", "live", "data/ライブカード/Aqours"),
    ("虹ヶ咲", "live", "data/ライブカード/虹ヶ咲"),
    ("Liella!", "live", "data/ライブカード/Liella!"),
    ("蓮ノ空", "live", "data/ライブカード/蓮ノ空"),
    ("その他", "live", "data/ライブカード/その他"),
]


CARD_ID_RE = re.compile(
    r"(?:PL![A-Za-z]*|LL)-"
    r"(?:[A-Za-z0-9]+)-"
    r"\d{3}"
    r"(?:-E\d{2})?",
    re.IGNORECASE,
)


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
                print("429: {}秒待機".format(wait))
                time.sleep(wait)
                continue

            print(
                "HTTP {}: {}".format(
                    response.status_code,
                    url,
                )
            )

        except requests.RequestException as e:
            print(
                "通信エラー: {}".format(e)
            )

        time.sleep(delay)

    return None


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
            "既存データ読み込み失敗: {}".format(
                e
            )
        )

    return {}


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

    for index, item in enumerate(
        WIKI_PAGES,
        1,
    ):
        work, kind, page = item

        url = WIKI_BASE + page

        print(
            "[Wiki {}/{}] {} / {}".format(
                index,
                len(WIKI_PAGES),
                work,
                kind,
            )
        )

        response = request_with_retry(
            session,
            url,
        )

        if not response:
            print("  -> 取得失敗")
            continue

        cards = parse_wiki_page(
            response.text,
            work,
            kind,
        )

        print(
            "  -> {}件".format(
                len(cards)
            )
        )

        for card in cards:
            all_cards[
                card["id"]
            ] = card

        time.sleep(
            WIKI_PAGE_DELAY
        )

    return all_cards


def normalize_base_id(card_id):
    if not card_id:
        return ""

    match = CARD_ID_RE.search(
        card_id
    )

    if match:
        return match.group(0)

    return card_id.strip()


def get_rarity_from_filename(
    filename,
):
    name = Path(filename).stem

    match = re.search(
        r"-([A-Za-z0-9＋+]+)$",
        name,
    )

    if not match:
        return ""

    return match.group(1).replace(
        "＋",
        "+",
    )


def get_llocg_image_tree(session):
    print("")
    print(
        "========================================"
    )
    print("LLOCG_DB画像一覧取得")
    print(
        "========================================"
    )

    response = request_with_retry(
        session,
        LLOCG_API,
        retries=5,
        delay=5,
        params={
            "recursive": "1",
        },
    )

    if not response:
        print(
            "LLOCG_DBのTree取得失敗"
        )
        return []

    try:
        data = response.json()

    except Exception as e:
        print(
            "JSON解析失敗: {}".format(
                e
            )
        )
        return []

    tree = data.get(
        "tree",
        [],
    )

    print(
        "LLOCG_DBファイル数: {}".format(
            len(tree)
        )
    )

    return tree


def build_image_index(tree):
    index = {}

    for item in tree:
        if item.get("type") != "blob":
            continue

        path = item.get(
            "path",
            "",
        )

        if not path.startswith(
            "img/cards/"
        ):
            continue

        if not path.lower().endswith(
            ".png"
        ):
            continue

        filename = Path(path).name

        base_id = normalize_base_id(
            filename
        )

        if not base_id:
            continue

        index.setdefault(
            base_id,
            [],
        ).append({
            "path": path,
            "filename": filename,
            "rarity": get_rarity_from_filename(
                filename
            ),
        })

    return index


def rarity_priority(rarity):
    priorities = {
        "N": 10,
        "P": 20,
        "R": 30,
        "L": 40,
        "SD": 45,
        "PE": 50,
        "PR": 60,
        "SR": 70,
        "SEC": 80,
        "SECE": 90,
        "P2": 100,
        "R2": 110,
    }

    return priorities.get(
        rarity.upper(),
        200,
    )


def choose_image(
    card_id,
    candidates,
):
    if not candidates:
        return None

    base_id = normalize_base_id(
        card_id
    )

    exact = [
        x
        for x in candidates
        if Path(
            x["filename"]
        ).stem.startswith(
            base_id + "-"
        )
    ]

    if exact:
        candidates = exact

    candidates = sorted(
        candidates,
        key=lambda x: (
            rarity_priority(
                x.get(
                    "rarity",
                    "",
                )
            ),
            x.get(
                "filename",
                "",
            ),
        ),
    )

    return candidates[0]


def attach_images(
    cards,
    image_index,
):
    matched = 0
    rarity_count = 0

    for card_id, card in cards.items():

        base_id = normalize_base_id(
            card_id
        )

        candidates = image_index.get(
            base_id,
            [],
        )

        selected = choose_image(
            card_id,
            candidates,
        )

        if not selected:
            continue

        path = selected[
            "path"
        ]

        image_url = (
            LLOCG_RAW
            + quote(
                path,
                safe="/!()-_.~",
            )
        )

        card["image"] = image_url

        matched += 1

        rarity = selected.get(
            "rarity",
            "",
        )

        if rarity:
            card["rarity"] = rarity
            rarity_count += 1

    print("")
    print("LLOCG_DB画像照合結果")
    print(
        "画像あり: {}".format(
            matched
        )
    )
    print(
        "レアリティあり: {}".format(
            rarity_count
        )
    )

    return cards


def merge_cards(
    wiki_cards,
    existing,
):
    merged = {}

    for card_id, wiki in wiki_cards.items():

        old = existing.get(
            card_id,
            {},
        )

        card = dict(old)

        card.update(wiki)

        if old.get("image"):
            card["image"] = old[
                "image"
            ]

        if old.get("rarity"):
            card["rarity"] = old[
                "rarity"
            ]

        merged[card_id] = card

    return merged


def save_cards(cards):
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = list(
        cards.values()
    )

    data.sort(
        key=lambda x: x.get(
            "id",
            "",
        )
    )

    with open(
        DATA_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print(
        "=============================="
    )
    print(
        "最終カード件数: {}".format(
            len(data)
        )
    )
    print(
        "保存先: {}".format(
            DATA_FILE
        )
    )
    print(
        "=============================="
    )


def main():

    print(
        "ラブカカード同期開始"
    )
    print("")

    session = get_session()

    existing = load_existing()

    print(
        "既存データ件数: {}".format(
            len(existing)
        )
    )

    wiki_cards = fetch_wiki_cards(
        session
    )

    print("")
    print(
        "Wiki取得件数: {}".format(
            len(wiki_cards)
        )
    )

    if len(wiki_cards) < 100:

        print("")
        print(
            "⚠ Wiki取得件数が少なすぎます"
        )
        print(
            "⚠ 既存データを維持します"
        )

        if existing:
            save_cards(
                existing
            )

        return

    merged = merge_cards(
        wiki_cards,
        existing,
    )

    tree = get_llocg_image_tree(
        session
    )

    if tree:

        image_index = build_image_index(
            tree
        )

        print(
            "画像カード番号種類: {}".format(
                len(image_index)
            )
        )

        merged = attach_images(
            merged,
            image_index,
        )

    else:

        print(
            "⚠ LLOCG_DB画像一覧を取得できませんでした"
        )
        print(
            "⚠ 既存画像がある場合は維持します"
        )

    save_cards(
        merged
    )


if __name__ == "__main__":
    main()
