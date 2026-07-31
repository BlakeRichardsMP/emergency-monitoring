import json
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import feedparser
import yaml


FEEDS_FILE = Path("provincial-feeds.yaml")
STATE_FILE = Path("provincial_seen_items.json")
RSS_FILE = Path("provincial.xml")


def load_feeds() -> list[dict]:
    with FEEDS_FILE.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    feeds = config.get("feeds", [])

    if not feeds:
        raise ValueError("No feeds found in feeds.yaml")

    return feeds


def load_seen_items() -> set[str]:
    if not STATE_FILE.exists():
        return set()

    with STATE_FILE.open("r", encoding="utf-8") as file:
        return set(json.load(file))


def save_seen_items(items: set[str]) -> None:
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(sorted(items), file, indent=2, ensure_ascii=False)


def entry_identifier(entry) -> str:
    return (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
        or f"{entry.get('title', '')}|{entry.get('published', '')}"
    )


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
    <title>Government Emergency Monitoring</title>
    <link>https://github.com/BlakeRichardsMP/emergency-monitoring</link>
    <description>Normalized Government of Canada emergency-related feeds</description>
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

        print(f"Checking {source_name}")

        parsed_feed = feedparser.parse(source_url)

        if parsed_feed.bozo and not parsed_feed.entries:
            print(f"Feed failed: {source_name}: {parsed_feed.bozo_exception}")
            continue

        print(f"Found {len(parsed_feed.entries)} entries")

        for entry in parsed_feed.entries:
            identifier = entry_identifier(entry)

            all_items.append(
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

            updated_seen_items.add(identifier)

    RSS_FILE.write_text(build_rss(all_items), encoding="utf-8")
    save_seen_items(updated_seen_items)

    new_count = len(updated_seen_items - seen_items)

    print(f"RSS items written: {len(all_items)}")
    print(f"New items found: {new_count}")


if __name__ == "__main__":
    main()
