import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "cards.json"

# バックアップ先
BACKUP_DIR = DATA_DIR / "backup"

WIKI_BASE = "https://wikiwiki.jp/llocardgame/"
LLOCG_API = "https://api.github.com/repos/wlt233/llocg_db/git/trees/master"
LLOCG_COMMITS_API = (
    "https://api.github.com/repos/wlt233/llocg_db/commits"
)
LLOCG_RAW = "https://raw.githubusercontent.com/wlt233/llocg_db/master/"
LLOCG_RAW_COMMIT = (
    "https://raw.githubusercontent.com/wlt233/llocg_db/{}/json/cards.json"
)

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
                print(
                    "429: {}秒待機".format(
                        wait
                    )
                )
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
                "通信エラー: {}".format(
                    e
                )
            )

        time.sleep(delay)

    return None


def load_existing():
    """
    現在のcards.jsonを読み込む。

    ここで読み込んだカードは、
    Wiki側から消えていても絶対に削除しない。
    """
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
            result = {}

            for card in data:
                if not isinstance(card, dict):
                    continue

                card_id = card.get("id")

                if not card_id:
                    continue

                result[str(card_id)] = card

            return result

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(
            "既存データ読み込み失敗: {}".format(
                e
            )
        )

    return {}


def backup_existing():
    """
    現在のcards.jsonをバックアップ。
    """
    if not DATA_FILE.exists():
        return

    try:
        BACKUP_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = time.strftime(
            "%Y%m%d_%H%M%S"
        )

        backup_file = (
            BACKUP_DIR
            / "cards_{}.json".format(
                timestamp
            )
        )

        shutil.copy2(
            DATA_FILE,
            backup_file,
        )

        print(
            "バックアップ作成: {}".format(
                backup_file
            )
        )

    except Exception as e:
        print(
            "バックアップ作成失敗: {}".format(
                e
            )
        )


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
            print(
                "  -> 取得失敗"
            )
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
        str(card_id)
    )

    if match:
        return match.group(0)

    return str(card_id).strip()


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
        str(rarity).upper(),
        200,
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

        path = selected["path"]

        image_url = (
            LLOCG_RAW
            + quote(
                path,
                safe="/!()-_.~",
            )
        )

        # 新しい画像が見つかった場合だけ更新
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
    print(
        "LLOCG_DB画像照合結果"
    )
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


def get_historical_llocg_cards(
    session,
):
    """
    現在の llocg_db/json/cards.json が空の場合に、
    GitHubの過去コミットから populated cards.json を探す。

    見つからなければ空dictを返す。
    """
    print("")
    print(
        "========================================"
    )
    print("LLOCG_DB過去JSON確認")
    print(
        "========================================"
    )

    response = request_with_retry(
        session,
        LLOCG_COMMITS_API,
        retries=3,
        delay=3,
        params={
            "path": "json/cards.json",
            "per_page": "20",
        },
    )

    if not response:
        print(
            "過去コミット一覧の取得失敗"
        )
        return {}

    try:
        commits = response.json()

    except Exception as e:
        print(
            "コミットJSON解析失敗: {}".format(
                e
            )
        )
        return {}

    if not isinstance(
        commits,
        list,
    ):
        return {}

    print(
        "過去コミット候補: {}".format(
            len(commits)
        )
    )

    checked = 0

    for commit in commits:

        sha = (
            commit
            .get("sha")
        )

        if not sha:
            continue

        checked += 1

        url = LLOCG_RAW_COMMIT.format(
            sha
        )

        print(
            "過去JSON確認 {}/{}: {}".format(
                checked,
                len(commits),
                sha[:8],
            )
        )

        old_response = request_with_retry(
            session,
            url,
            retries=2,
            delay=2,
        )

        if not old_response:
            continue

        try:
            data = old_response.json()

        except Exception:
            continue

        if not isinstance(
            data,
            dict,
        ):
            continue

        if len(data) < 100:
            continue

        print(
            "過去JSONから {}件を取得".format(
                len(data)
            )
        )

        return data

    print(
        "利用できる過去JSONは見つかりませんでした"
    )

    return {}


def normalize_external_card_id(
    value,
):
    if not value:
        return ""

    value = str(value).strip()

    match = CARD_ID_RE.search(
        value
    )

    if match:
        return match.group(0)

    return value


def attach_historical_data(
    cards,
    historical,
):
    """
    過去の llocg_db JSON から
    画像・レアリティ・商品・名前を補完する。

    既存の画像や情報は原則上書きしない。
    """
    if not historical:
        return cards

    image_added = 0
    rarity_added = 0
    product_added = 0
    name_added = 0

    # 正規化したキーで検索できるようにする
    normalized = {}

    for key, value in historical.items():

        if not isinstance(
            value,
            dict,
        ):
            continue

        card_no = value.get(
            "card_no",
            key,
        )

        normalized_id = normalize_external_card_id(
            card_no
        )

        if normalized_id:
            normalized[
                normalized_id
            ] = value

    for card_id, card in cards.items():

        if card.get("image"):
            has_image = True
        else:
            has_image = False

        source = normalized.get(
            normalize_base_id(card_id)
        )

        if not source:
            continue

        # 画像
        if not has_image:

            image = source.get(
                "img"
            )

            if image:
                card["image"] = image
                image_added += 1

        # レアリティ
        if not card.get(
            "rarity"
        ):

            rarity = source.get(
                "rare"
            )

            if rarity:
                card["rarity"] = str(
                    rarity
                ).replace(
                    "＋",
                    "+",
                )

                rarity_added += 1

        # 商品
        if not card.get(
            "product"
        ):

            product = source.get(
                "product"
            )

            if product:
                card["product"] = product
                product_added += 1

        # カード名
        if not card.get(
            "name"
        ):

            name = source.get(
                "name"
            )

            if name:
                card["name"] = name
                name_added += 1

    print("")
    print(
        "過去LLOCG_DB補完結果"
    )
    print(
        "画像追加: {}".format(
            image_added
        )
    )
    print(
        "レアリティ追加: {}".format(
            rarity_added
        )
    )
    print(
        "商品追加: {}".format(
            product_added
        )
    )
    print(
        "名前追加: {}".format(
            name_added
        )
    )

    return cards


def merge_cards(
    wiki_cards,
    existing,
):
    """
    最重要部分。

    existingを最初に全部コピーし、
    Wiki側のデータを上書き・追加する。

    つまり、
    Wikiから消えたカードがあっても
    existingから削除されない。
    """
    merged = {}

    # まず現在の1144件を全部残す
    for card_id, card in existing.items():

        if not isinstance(
            card,
            dict,
        ):
            continue

        merged[
            card_id
        ] = dict(card)

    # Wikiのカードを追加・更新
    for card_id, wiki in wiki_cards.items():

        if card_id in merged:

            old = merged[
                card_id
            ]

            # Wiki情報で基本情報を更新
            old.update(wiki)

            # 既存の画像は、
            # 後の画像補完まで消さない
            if existing.get(
                card_id,
                {}
            ).get("image"):

                old["image"] = existing[
                    card_id
                ]["image"]

            if existing.get(
                card_id,
                {}
            ).get("rarity"):

                old["rarity"] = existing[
                    card_id
                ]["rarity"]

        else:

            merged[
                card_id
            ] = dict(wiki)

    return merged


def verify_no_cards_lost(
    existing,
    merged,
):
    """
    既存カードが1枚でも消えていたら
    保存を中止する。
    """
    missing = []

    for card_id in existing:
        if card_id not in merged:
            missing.append(
                card_id
            )

    if missing:

        print("")
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )
        print(
            "ERROR: 既存カードが消えるため保存中止"
        )
        print(
            "消失予定: {}件".format(
                len(missing)
            )
        )
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        return False

    return True


def save_cards(
    cards,
):
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
        "========================================"
    )
    print(
        "ラブカカード同期開始"
    )
    print(
        "========================================"
    )

    session = get_session()

    # ----------------------------------------
    # 1. 現在のデータを読み込む
    # ----------------------------------------

    existing = load_existing()

    print("")
    print(
        "既存データ件数: {}".format(
            len(existing)
        )
    )

    # 1144件以上ある場合、
    # その件数を最低保証する
    existing_count = len(
        existing
    )

    # ----------------------------------------
    # 2. Wiki取得
    # ----------------------------------------

    wiki_cards = fetch_wiki_cards(
        session
    )

    print("")
    print(
        "Wiki取得件数: {}".format(
            len(wiki_cards)
        )
    )

    # Wikiが完全に死んでいる場合も
    # 既存データだけで続行する
    if len(wiki_cards) < 100:

        print("")
        print(
            "⚠ Wiki取得件数が少なすぎます"
        )
        print(
            "⚠ 既存データを維持して続行します"
        )

        merged = dict(
            existing
        )

    else:

        merged = merge_cards(
            wiki_cards,
            existing,
        )

    # ----------------------------------------
    # 3. LLOCG_DB画像
    # ----------------------------------------

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

        print("")
        print(
            "⚠ LLOCG_DB画像一覧取得失敗"
        )
        print(
            "⚠ 既存画像はそのまま維持します"
        )

    # ----------------------------------------
    # 4. 過去のLLOCG_DB JSON
    # ----------------------------------------

    # 画像がまだないカードを
    # 過去JSONの公式画像URLで補完
    needs_historical = False

    for card in merged.values():

        if not card.get(
            "image"
        ):
            needs_historical = True
            break

    historical = {}

    if needs_historical:

        historical = get_historical_llocg_cards(
            session
        )

        if historical:

            merged = attach_historical_data(
                merged,
                historical,
            )

    # ----------------------------------------
    # 5. 最終安全確認
    # ----------------------------------------

    print("")
    print(
        "========================================"
    )
    print("最終安全確認")
    print(
        "========================================"
    )

    if not verify_no_cards_lost(
        existing,
        merged,
    ):

        print(
            "安全確認失敗"
        )
        print(
            "cards.jsonは変更しません"
        )

        return

    final_count = len(
        merged
    )

    print(
        "開始時カード数: {}".format(
            existing_count
        )
    )

    print(
        "最終カード数: {}".format(
            final_count
        )
    )

    if final_count < existing_count:

        print("")
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )
        print(
            "ERROR: カード数が減少しています"
        )
        print(
            "{} -> {}".format(
                existing_count,
                final_count,
            )
        )
        print(
            "保存を中止します"
        )
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        return

    # ----------------------------------------
    # 6. バックアップ
    # ----------------------------------------

    backup_existing()

    # ----------------------------------------
    # 7. 保存
    # ----------------------------------------

    save_cards(
        merged
    )

    # ----------------------------------------
    # 8. 最終結果
    # ----------------------------------------

    image_count = 0

    for card in merged.values():
        if card.get("image"):
            image_count += 1

    print("")
    print(
        "========================================"
    )
    print(
        "同期完了"
    )
    print(
        "========================================"
    )
    print(
        "開始時: {}件".format(
            existing_count
        )
    )
    print(
        "最終: {}件".format(
            final_count
        )
    )
    print(
        "画像あり: {}件".format(
            image_count
        )
    )
    print(
        "画像なし: {}件".format(
            final_count - image_count
        )
    )
    print(
        "========================================"
    )


if __name__ == "__main__":
    main()
