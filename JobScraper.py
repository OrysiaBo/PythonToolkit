"""
Job Scraper & Analyzer — Скрапер вакансій і аналізатор
=======================================================
Scrapes job listings from a public RSS/JSON feed, stores them in CSV,
and prints a simple frequency analysis of required skills.

Зчитує вакансії з публічного RSS/JSON-джерела, зберігає у CSV
та виводить частотний аналіз навичок, що найчастіше зустрічаються.

Requirements / Залежності:
  pip install requests beautifulsoup4

Run / Запуск:
  python job_scraper.py
  python job_scraper.py --limit 20 --keyword python
"""

import argparse
import csv
import re
import time
from collections import Counter
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ─── Data model / Модель даних ────────────────────────────────────────────────

@dataclass
class JobPost:
    """
    One job listing scraped from the source.
    Одна вакансія, зчитана з джерела.
    """
    title:     str
    company:   str
    location:  str
    url:       str
    posted:    str   # human-readable date / дата у читабельному форматі
    keywords:  str   # comma-separated skills found in the description / навички через кому


# ─── Configuration / Конфігурація ─────────────────────────────────────────────

# We use HackerNews "Who is hiring?" — no API key needed, fully public
# Використовуємо HackerNews "Who is hiring?" — без ключа, повністю публічне
HN_API_BASE  = "https://hacker-news.firebaseio.com/v0"
HN_TOP_ITEMS = f"{HN_API_BASE}/topstories.json"

# Skills to look for inside job descriptions (extend this list freely)
# Навички, які шукаємо в описах (розширюй список за потреби)
TRACKED_SKILLS = [
    "python", "javascript", "typescript", "react", "django", "fastapi",
    "sql", "postgresql", "mysql", "mongodb", "redis",
    "docker", "kubernetes", "linux", "git", "aws", "azure",
    "machine learning", "ml", "pytorch", "tensorflow", "llm",
]

OUTPUT_CSV = Path("jobs.csv")
REQUEST_DELAY = 0.5   # seconds between requests — be polite to the server
                       # секунди між запитами — не перевантажуємо сервер


# ─── Network helpers / Мережеві допоміжники ───────────────────────────────────

def fetch_json(url: str) -> dict | list | None:
    """
    GET request with timeout and basic error handling.
    GET-запит з таймаутом і базовою обробкою помилок.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()   # raise on 4xx/5xx / виняток на 4xx/5xx
        return response.json()
    except requests.RequestException as exc:
        print(f"  [network error] {exc}")
        return None


def fetch_text(url: str) -> str:
    """
    GET request returning raw text (for HTML pages).
    GET-запит, що повертає сирий текст (для HTML-сторінок).
    """
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"  [network error] {exc}")
        return ""


# ─── Parsing / Парсинг ────────────────────────────────────────────────────────

def extract_skills(text: str) -> list[str]:
    """
    Find tracked skill keywords in a block of text (case-insensitive).
    Знаходить навички зі списку у тексті (без урахування регістру).
    """
    lower = text.lower()
    found = []
    for skill in TRACKED_SKILLS:
        # Use word-boundary matching to avoid 'sql' matching inside 'nosql'
        # Пошук з межами слова, щоб 'sql' не знайшлось всередині 'nosql'
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, lower):
            found.append(skill)
    return found


def parse_hn_item(item: dict) -> JobPost | None:
    """
    Convert a raw HackerNews item dict into a JobPost.
    Перетворює сирий словник HN-елемента на JobPost.
    Returns None if the item is not a job post.
    Повертає None, якщо елемент не є вакансією.
    """
    # HN job posts have type "job"; skip everything else
    # Вакансії на HN мають тип "job"; інші пропускаємо
    if item.get("type") != "job":
        return None

    title   = item.get("title", "")
    url     = item.get("url", f"https://news.ycombinator.com/item?id={item['id']}")
    text_html = item.get("text", "")

    # Strip HTML tags from the description to get plain text for skill extraction
    # Знімаємо HTML-теги з опису, щоб отримати звичайний текст для аналізу
    soup        = BeautifulSoup(text_html, "html.parser")
    plain_text  = soup.get_text(separator=" ")
    combined    = f"{title} {plain_text}"

    skills = extract_skills(combined)

    # Try to extract company name from title (common pattern: "Company (City) | Role")
    # Намагаємось витягнути назву компанії з заголовку (поширений шаблон)
    company  = title.split(" is hiring")[0] if " is hiring" in title else "—"
    location = "Remote" if "remote" in combined.lower() else "—"

    ts = item.get("time", 0)
    posted = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else "—"

    return JobPost(
        title    = title,
        company  = company,
        location = location,
        url      = url,
        posted   = posted,
        keywords = ", ".join(skills),
    )


# ─── Scraping logic / Логіка скрапінгу ───────────────────────────────────────

def scrape_hn_jobs(limit: int = 10, keyword_filter: str = "") -> list[JobPost]:
    """
    Fetch recent HN job posts up to `limit` items.
    Зчитує останні вакансії з HN, не більше `limit` штук.
    """
    print(f"Fetching top stories list…")
    ids = fetch_json(HN_TOP_ITEMS) or []

    jobs: list[JobPost] = []
    checked = 0

    for item_id in ids:
        if len(jobs) >= limit:
            break

        item = fetch_json(f"{HN_API_BASE}/item/{item_id}.json")
        if not item:
            continue

        job = parse_hn_item(item)
        if job is None:
            continue   # not a job post / не вакансія

        # Optional keyword filter applied to title
        # Необов'язковий фільтр за ключовим словом у заголовку
        if keyword_filter and keyword_filter.lower() not in job.title.lower():
            continue

        jobs.append(job)
        checked += 1
        print(f"  [{checked}] {job.title[:60]}")

        # Throttle requests to avoid hammering the API
        # Робимо паузу між запитами, щоб не перевантажувати API
        time.sleep(REQUEST_DELAY)

    return jobs


# ─── Storage / Збереження ─────────────────────────────────────────────────────

def save_to_csv(jobs: list[JobPost], path: Path) -> None:
    """
    Write job posts to a CSV file (overwrites existing file).
    Записує вакансії у CSV-файл (перезаписує наявний).
    """
    column_names = [f.name for f in fields(JobPost)]   # derive headers from dataclass / заголовки з dataclass
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=column_names)
        writer.writeheader()
        for job in jobs:
            # dataclasses.asdict would work too; using __dict__ is slightly faster
            # dataclasses.asdict теж підійде; __dict__ трохи швидший
            writer.writerow(job.__dict__)
    print(f"\n✓ Saved {len(jobs)} jobs → {path}")


# ─── Analysis / Аналіз ────────────────────────────────────────────────────────

def print_skill_report(jobs: list[JobPost], top_n: int = 10) -> None:
    """
    Count skill mentions across all jobs and print a ranked table.
    Підраховує згадки навичок по всіх вакансіях і виводить рейтинг.
    """
    counter: Counter = Counter()
    for job in jobs:
        for skill in job.keywords.split(", "):
            skill = skill.strip()
            if skill:
                counter[skill] += 1

    print(f"\n{'─'*35}")
    print(f"  Top {top_n} skills / Топ навичок")
    print(f"{'─'*35}")

    for rank, (skill, count) in enumerate(counter.most_common(top_n), start=1):
        # Bar chart made of ASCII blocks — quick visual overview
        # Стовпчаста діаграма з ASCII-символів — швидкий візуальний огляд
        bar = "█" * count
        print(f"  {rank:>2}. {skill:<20} {bar} ({count})")

    print(f"{'─'*35}\n")


# ─── Entry point / Точка входу ────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape HN job posts / Скрапер вакансій HN")
    p.add_argument("--limit",   type=int, default=10, help="Max jobs to fetch (default 10)")
    p.add_argument("--keyword", type=str, default="",  help="Filter by keyword in title")
    return p


def main() -> None:
    args = build_parser().parse_args()

    print(f"\n=== Job Scraper started — {datetime.now():%Y-%m-%d %H:%M} ===\n")

    jobs = scrape_hn_jobs(limit=args.limit, keyword_filter=args.keyword)

    if not jobs:
        print("No job posts found. / Вакансій не знайдено.")
        return

    save_to_csv(jobs, OUTPUT_CSV)
    print_skill_report(jobs)


if __name__ == "__main__":
    main()