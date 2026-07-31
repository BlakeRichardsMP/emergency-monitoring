import json
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import feedparser
import requests
import yaml


FEEDS_FILE = Path("provincial-feeds.yaml")
STATE_FILE = Path("provincial_seen_items.json")
RSS_FILE = Path("provincial.xml")


def load_feeds() -> list[dict]:
    with FEEDS_FILE.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    feeds = config.get("feeds", [])

    if not feeds:
        raise ValueError("No feeds found in provincial-feeds.yaml")

    return feeds


def load_seen_items() -> set[str]:
    if not STATE_FILE.exists():
        return set()

    with STATE_FILE.open("r", encoding="utf-8") as file:
        return set(json.load(file))


def save_seen_items(items: set[str]) -> None:
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(sorted(items), file, indent=2, ensure_ascii=False)


def rss_entry_identifier(entry) -> str:
    return (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
        or f"{entry.get('title', '')}|{entry.get('published', '')}"
    )


def parse_rss_feed(source_name: str, source_url: str) -> list[dict]:
    parsed_feed = feedparser.parse(source_url)

    if parsed_feed.bozo and not parsed_feed.entries:
        print(f"Feed failed: {source_name}: {parsed_feed.bozo_exception}")
        return []

    print(f"Found {len(parsed_feed.entries)} entries")

    items = []

    for entry in parsed_feed.entries:
        identifier = rss_entry_identifier(entry)

        items.append(
            {
                "id": identifier,
                "source": source_name,
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", "").strip(),
                "published": entry.get(
                    "published",
                    entry.get("updated", "")
                ),
                "summary": entry.get(
                    "summary",
                    entry.get("description", "")
                ),
            }
        )

    return items


def parse_saskatchewan_json(
    source_name: str,
    source_url: str
) -> list[dict]:
    response = requests.get(
        source_url,
        timeout=30,
        headers={"User-Agent": "EmergencyMonitoring/1.0"}
    )
    response.raise_for_status()

    data = response.json()
    entries = data.get("entries", [])

    print(f"Found {len(entries)} entries")

    items = []

    for entry in entries:
        identifier = (
            entry.get("id")
            or entry.get("identifier")
            or entry.get("cap_link")
            or entry.get("html_link")
        )

        title = (
            entry.get("event_en")
            or entry.get("headline")
            or entry.get("code")
            or "Saskatchewan Emergency Alert"
        )

        summary = (
            entry.get("summary_en")
            or entry.get("description_en")
            or entry.get("headline")
            or ""
        )

        link = (
            entry.get("html_link")
            or entry.get("cap_link")
            or source_url
        )

        published = (
            entry.get("sent")
            or entry.get("updated")
            or data.get("updated", "")
        )

        if not identifier:
            identifier = f"{title}|{published}|{link}"

        items.append(
            {
                "id": str(identifier),
                "source": source_name,
                "title": str(title).strip(),
                "link": str(link).strip(),
                "published": str(published).strip(),
                "summary": str(summary).strip(),
            }
        )

    return items


def build_rss(items: list[dict]) -> str:
    rss_items = []

    for item in items:
        rss_items.append(
            f"""
    <item>
      <title>{escape(item["title"])}</title>
      <link>{escape(item["link"])}</link>
      <guid isPermaLink="false">{escape(item["id"])}</guid>
      <pubDate>{escape(item["published"])}</pubDate>
      <description>{escape(item["summary"])}</description>
      <source>{escape(item["source"])}</source>
    </item>
"""
        )

    generated_at = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Provincial Emergency Alerts</title>
    <link>https://blakerichardsmp.github.io/emergency-monitoring/provincial.xml</link>
    <description>Canadian provincial and territorial emergency alert aggregator</description>
    <language>en-ca</language>
    <lastBuildDate>{generated_at}</lastBuildDate>
{''.join(rss_items)}
  </channel>
</rss>
"""


def main() -> None:
    feeds = load_feeds()
    seen_items = load_seen_items()
    updated_seen_items = set(seen_items)
    all_items = []

    for source in feeds:
        source_name = source["name"]
        source_url = source["url"]
        source_type = source.get("type", "rss").lower()

        print(f"Checking {source_name}")

        try:
            if source_type == "json":
                items = parse_saskatchewan_json(
                    source_name,
                    source_url
                )
            else:
                items = parse_rss_feed(
                    source_name,
                    source_url
                )

            all_items.extend(items)

            for item in items:
                updated_seen_items.add(item["id"])

        except Exception as error:
            print(f"Feed failed: {source_name}: {error}")

    RSS_FILE.write_text(build_rss(all_items), encoding="utf-8")
    save_seen_items(updated_seen_items)

    new_count = len(updated_seen_items - seen_items)

    print(f"RSS items written: {len(all_items)}")
    print(f"New items found: {new_count}")


if __name__ == "__main__":
    main()
