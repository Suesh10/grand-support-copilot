"""Собирает copilot/support_articles.json из открытого центра поддержки: python scripts/articles.py

Хранит только название, ссылку и ключевые слова для поиска, текст статей в проект не копируется.
Сеть нужна только этому скрипту: сервис работает с готовым файлом.
"""

import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "copilot" / "support_articles.json"
BASE = "https://support.grnd.gg/ru"
COLLECTIONS = [18442715, 12295907, 12295066, 12404105, 16579302, 12295047, 18442723, 18442724, 14011492, 14011494, 18442730]
# Правила сервис и так цитирует по пунктам, а новости устаревают.
SKIP_RE = re.compile(r"^(I|II|III|IV|V|VI)\. |Правила поведения|Кодекс поведения")
TERMS = 14
# Как игроки называют то же самое своими словами.
ALIASES = {
    "12802402": "получить права на машину грузовик автошкола",
    "11071809": "жб залить кинуть",
    "11071824": "апелляция обжаловать",
    "12802832": "фракция вступить устроиться",
    "11792114": "фракция вступить устроиться",
    "12852616": "эвакуатор",
    "12851812": "продать свою машину",
    "12802394": "сменить ник",
}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


def plain(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def article_text(article_id: str) -> str:
    page = fetch(f"{BASE}/articles/{article_id}")
    found = re.search(r"<article[^>]*>(.*?)</article>", page, re.S)
    return re.sub(r"Другие статьи по теме.*", "", plain(found.group(1) if found else page))


def main() -> None:
    titles = {}
    for collection in COLLECTIONS:
        page = fetch(f"{BASE}/collections/{collection}")
        for article_id, inner in re.findall(r'href="https://support\.grnd\.gg/ru/articles/(\d+)-[^"]*"[^>]*>(.*?)</a>', page, re.S):
            titles.setdefault(article_id, plain(inner)[:120])
    titles = {k: v for k, v in titles.items() if not SKIP_RE.search(v)}
    ids = list(titles)
    with ThreadPoolExecutor(6) as pool:
        texts = list(pool.map(article_text, ids))
    vec = TfidfVectorizer(token_pattern=r"[а-яёa-z]{4,}", max_df=0.15, sublinear_tf=True)
    weights = vec.fit_transform(texts).toarray()
    names = vec.get_feature_names_out()
    articles = []
    for row, article_id in zip(weights, ids):
        terms = [str(names[j]) for j in row.argsort()[::-1][:TERMS] if row[j] > 0]
        if article_id in ALIASES:
            terms += ALIASES[article_id].split()
        articles.append({"id": article_id, "title": titles[article_id], "url": f"{BASE}/articles/{article_id}", "terms": terms})
    OUT.write_text(json.dumps(articles, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Статей: {len(articles)} → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
