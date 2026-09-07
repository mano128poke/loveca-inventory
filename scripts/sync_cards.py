import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# =========================================================
# 設定
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "cards.json"

WIKI_BASE = "https://wikiwiki.jp/llocardgame/"
OFFICIAL_BASE = "https://llofficial-cardgame.com"
OFFICIAL_LIST = f"{OFFICIAL_BASE}/cardlist/searchresults/"

WIKI_PAGE_DELAY = 6
OFFICIAL_PAGE_DELAY = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; loveca-inventory/1.0; "
        "+https://github.com/mano128poke/loveca-inventory)"
    )
}


# =========================================================
# Wiki
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


# Wiki側の基本カード番号
CARD_ID_RE = re.compile(
    r"(?:PL![A-Z]*|LL)-"
    r"(?:[A-Za-z0-9]+)-"
    r"\d{3}"
    r"(?:-E\d{2})?",
    re.IGNORECASE,
)


def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def request_with_retry(session, url, retries=5, delay=5):
    """
    429 / 一時的な通信失敗に対応。
    """
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)

            if r.status_code == 200:
                return r

            if r.status_code == 429:
                wait = delay * (attempt + 1)
                print(f"429: {wait}秒待機")
                time.sleep(wait)
                continue

            print(f"HTTP {r.status_code}: {url}")

        except requests.RequestException as e:
            print(f"通信エラー: {e}")

        time.sleep(delay)

    return None


def load_existing():
    if not DATA_FILE.exists():
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
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
        print(f"既存データ読み込み失敗: {e}")

    return {}


def parse_wiki_page(html, work, kind):
    soup = BeautifulSoup(html, "html.parser")

    cards = []

    for a in soup.find_all("a"):
        text = " ".join(a.stripped_strings)

        match = CARD_ID_RE.search(text)

        if not match:
            continue

        card_id = match.group(0)

        # ID以降をカード名として扱う
        name = text[match.end():].strip()

        if not name:
            # リンク先のタイトル等から補完
            name = text

        # 商品名は行のテキストから拾う
        parent_text = " ".join(a.parent.stripped_strings)

        product = ""

        # よくある商品名
        product_patterns = [
            r"(スタートデッキ[^|]+)",
            r"(ブースターパック[^|]+)",
            r"(プレミアムブースター[^|]+)",
            r"(PRカード[^|]*)",
        ]

        for pattern in product_patterns:
            m = re.search(pattern, parent_text)
            if m:
                product = m.group(1).strip()
                break

        cards.append({
            "id": card_id,
            "name": name,
            "kind": kind,
            "work": work,
            "product": product,
        })

    return cards


def fetch_wiki_cards(session):
    all_cards = {}

    for index, (work, kind, page) in enumerate(WIKI_PAGES, 1):
        url = urljoin(WIKI_BASE, page)

        print(
            f"[Wiki {index}/{len(WIKI_PAGES)}] "
            f"{work} / {kind}"
        )

        r = request_with_retry(session, url)

        if not r:
            continue

        cards = parse_wiki_page(
            r.text,
            work,
            kind,
        )

        print(f"  → {len(cards)}件")

        for card in cards:
            all_cards[card["id"]] = card

        time.sleep(WIKI_PAGE_DELAY)

    return all_cards


# =========================================================
# 公式サイト
# =========================================================

OFFICIAL_CARD_ID_RE = re.compile(
    r"(?:PL![A-Z]*|LL)-"
    r"(?:[A-Za-z0-9]+)-"
    r"\d{3}"
    r"(?:-E\d{2})?"
    r"(?:-[A-Za-z0-9＋+]+)?",
    re.IGNORECASE,
)


def normalize_card_id(card_id):
    """
    公式:
        PL!-sd1-001-SD
        PL!-bp1-001-R
        PL!-bp1-001-P

    Wiki:
        PL!-sd1-001
        PL!-bp1-001

    → Wiki形式の基本番号にする
    """
    if not card_id:
        return ""

    card_id = card_id.strip()

    m = CARD_ID_RE.search(card_id)

    if not m:
        return card_id

    value = m.group(0)

    # 最後のレアリティ部分を削る
    parts = value.split("-")

    if len(parts) >= 4:
        # E01などのエネルギー番号は保持
        if re.fullmatch(r"E\d{2}", parts[-1], re.IGNORECASE):
            return value

        # 例:
        # PL!-bp1-001-R → PL!-bp1-001
        # PL!-sd1-001-SD → PL!-sd1-001
        parts = parts[:3]

    return "-".join(parts)


def rarity_from_official_id(card_id):
    """
    公式カード番号末尾からレアリティを取得。
    """
    if not card_id:
        return ""

    parts = card_id.split("-")

    if len(parts) < 4:
        return ""

    rarity = parts[-1]

    # レアリティとして扱わないもの
    if rarity.upper().startswith("E"):
        return ""

    return rarity.replace("＋", "+")


def extract_official_cards(html):
    """
    公式検索結果からカード情報を抽出。

    HTMLのクラス名に依存しすぎないよう、
    カード番号を基準に親要素を探す。
    """
    soup = BeautifulSoup(html, "html.parser")

    results = {}

    # カード番号を含むテキストを全探索
    text_nodes = soup.find_all(string=OFFICIAL_CARD_ID_RE)

    for node in text_nodes:
        text = " ".join(node.parent.stripped_strings)

        match = OFFICIAL_CARD_ID_RE.search(text)

        if not match:
            continue

        official_id = match.group(0)
        base_id = normalize_card_id(official_id)

        if not base_id:
            continue

        # 近い親要素を探す
        container = node.parent

        for _ in range(6):
            if container is None:
                break

            container_text = " ".join(container.stripped_strings)

            if official_id in container_text:
                # ある程度大きいカード単位になったところで停止
                if len(container_text) < 2000:
                    break

            container = container.parent

        if container is None:
            continue

        container_text = " ".join(container.stripped_strings)

        # -----------------------------
        # カード名
        # -----------------------------

        name = ""

        # 画像altからカード名を探す
        for img in container.find_all("img"):
            alt = img.get("alt", "").strip()

            if (
                alt
                and alt not in ["Image", "icon", "heart"]
                and not alt.startswith("http")
            ):
                # カード番号そのものは除外
                if official_id not in alt:
                    name = alt
                    break

        # -----------------------------
        # 画像
        # -----------------------------

        image = ""

        for img in container.find_all("img"):
            src = (
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("src")
                or ""
            )

            if not src:
                continue

            if src.startswith("data:"):
                continue

            # カード画像らしいものを優先
            lower = src.lower()

            if any(x in lower for x in [
                "card",
                "cardlist",
                "upload",
                "wp-content",
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
            ]):
                image = urljoin(OFFICIAL_BASE, src)
                break

        # -----------------------------
        # 商品
        # -----------------------------

        product = ""

        product_match = re.search(
            r"(?:収録商品)\s*[:：]?\s*(.+?)(?:カードタイプ|カード番号|詳しく見る|$)",
            container_text,
        )

        if product_match:
            product = product_match.group(1).strip()

        # -----------------------------
        # カードタイプ
        # -----------------------------

        card_kind = ""

        kind_match = re.search(
            r"カードタイプ\s*(メンバー|ライブ|エネルギー)",
            container_text,
        )

        if kind_match:
            card_kind = kind_match.group(1)

        # -----------------------------
        # レアリティ
        # -----------------------------

        rarity = rarity_from_official_id(official_id)

        results[base_id] = {
            "official_id": official_id,
            "name": name,
            "image": image,
            "rarity": rarity,
            "product": product,
            "official_kind": card_kind,
        }

    return results


def fetch_official_cards(session):
    """
    公式サイトの「全てのカード」をまとめて取得。

    1枚ずつアクセスしない。
    """
    params = {
        "expansion": "",
        "view": "text",
    }

    print("")
    print("========================================")
    print("公式カードリスト取得開始")
    print("========================================")

    r = request_with_retry(
        session,
        OFFICIAL_LIST,
    )

    if not r:
        print("公式サイト取得失敗")
        return {}

    cards = extract_official_cards(r.text)

    print(f"公式サイト抽出件数: {len(cards)}")

    return cards


# =========================================================
# マージ
# =========================================================

def merge_cards(wiki_cards, official_cards, existing):
    merged = {}

    # -----------------------------------------
    # Wikiを基本データにする
    # -----------------------------------------

    for card_id, wiki in wiki_cards.items():
        old = existing.get(card_id, {})

        card = dict(old)
        card.update(wiki)

        # 既存データは維持
        merged[card_id] = card

    # -----------------------------------------
    # 公式データを追加
    # -----------------------------------------

    official_count = 0
    image_count = 0
    rarity_count = 0

    for base_id, official in official_cards.items():

        # Wikiに存在しないカードは新規追加可能
        if base_id not in merged:
            merged[base_id] = {
                "id": base_id,
                "name": official.get("name", ""),
                "kind": "",
                "work": "",
                "product": official.get("product", ""),
            }

        card = merged[base_id]

        if official.get("name"):
            # Wiki名を優先。ただし空なら公式
            if not card.get("name"):
                card["name"] = official["name"]

        if official.get("image"):
            card["image"] = official["image"]
            image_count += 1

        if official.get("rarity"):
            card["rarity"] = official["rarity"]
            rarity_count += 1

        if official.get("product"):
            if not card.get("product"):
                card["product"] = official["product"]

        if official.get("official_id"):
            card["official_id"] = official["official_id"]

        official_count += 1

    print("")
    print("========================================")
    print("公式補完結果")
    print(f"公式カード: {official_count}")
    print(f"画像取得:   {image_count}")
    print(f"レアリティ: {rarity_count}")
    print("========================================")

    return merged


# =========================================================
# 保存
# =========================================================

def save_cards(cards):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data = list(cards.values())

    data.sort(
        key=lambda x: x.get("id", "")
    )

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print("==============================")
    print(f"最終カード件数: {len(data)}")
    print(f"保存先: {DATA_FILE}")
    print("==============================")


# =========================================================
# メイン
# =========================================================

def main():
    print("ラブカカード同期開始")
    print("")

    session = get_session()

    # 既存データ
    existing = load_existing()

    print(f"既存データ件数: {len(existing)}")

    # Wiki
    wiki_cards = fetch_wiki_cards(session)

    print("")
    print(f"Wiki取得件数: {len(wiki_cards)}")

    # Wikiが死んでいた場合は既存データを絶対に消さない
    if len(wiki_cards) < 100:
        print("")
        print("⚠ Wiki取得件数が少なすぎます")
        print("⚠ 既存データを維持して終了します")

        if existing:
            save_cards(existing)

        return

    # 公式
    official_cards = fetch_official_cards(session)

    # マージ
    merged = merge_cards(
        wiki_cards,
        official_cards,
        existing,
    )

    # 保存
    save_cards(merged)


if __name__ == "__main__":
    main()
