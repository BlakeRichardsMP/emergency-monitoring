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


def clean_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def rss_entry_identifier(entry) -> str:
    return (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
        or f"{entry.get('title', '')}|{entry.get('published', '')}"
    )


def get_json(source_url: str):
    response = requests.get(
        source_url,
        timeout=30,
        headers={
            "User-Agent": "EmergencyMonitoring/1.0",
            "Accept": "application/json",
        },
    )
    response.raise_for_status()
    return response.json()


def parse_rss_feed(
    source_name: str,
    source_url: str
) -> list[dict]:
    parsed_feed = feedparser.parse(source_url)

    if parsed_feed.bozo and not parsed_feed.entries:
        raise ValueError(parsed_feed.bozo_exception)

    print(f"Found {len(parsed_feed.entries)} entries")

    items = []

    for entry in parsed_feed.entries:
        identifier = rss_entry_identifier(entry)

        items.append(
            {
                "id": clean_text(identifier),
                "source": source_name,
                "title": clean_text(entry.get("title", "")),
                "link": clean_text(entry.get("link", "")),
                "published": clean_text(
                    entry.get(
                        "published",
                        entry.get("updated", "")
                    )
                ),
                "summary": clean_text(
                    entry.get(
                        "summary",
                        entry.get("description", "")
                    )
                ),
            }
        )

    return items


def parse_alertable_json(
    source_name: str,
    source_url: str
) -> list[dict]:
    data = get_json(source_url)
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

        event_name = clean_text(entry.get("event_en", ""))
        alert_status = clean_text(entry.get("type_en", ""))
        level = clean_text(entry.get("level", ""))

        title_parts = [
            event_name.title() if event_name else "",
            f"({alert_status})" if alert_status else "",
        ]

        title = " ".join(
            part for part in title_parts if part
        )

        if not title:
            title = f"{source_name} Emergency Alert"

        summary = clean_text(
            entry.get("summary_en")
            or entry.get("headline")
            or entry.get("event_en")
            or ""
        )

        link = clean_text(
            entry.get("html_link")
            or entry.get("cap_link")
            or source_url
        )

        published = clean_text(
            entry.get("sent")
            or entry.get("updated")
            or data.get("updated", "")
        )

        area_entries = entry.get("area") or []
        area_names = []

        for area in area_entries:
            if isinstance(area, dict):
                area_name = clean_text(area.get("name_en", ""))
                if area_name:
                    area_names.append(area_name)

        extra_parts = []

        if area_names:
            extra_parts.append("Areas: " + ", ".join(area_names))

        if level:
            extra_parts.append("Level: " + level)

        if extra_parts:
            summary = " | ".join(
                part for part in [summary, *extra_parts] if part
            )

        if not identifier:
            identifier = f"{title}|{published}|{link}"

        items.append(
            {
                "id": clean_text(identifier),
                "source": source_name,
                "title": clean_text(title),
                "link": link,
                "published": published,
                "summary": summary,
            }
        )

    return items


def parse_manitoba_json(
    source_name: str,
    source_url: str
) -> list[dict]:
    data = get_json(source_url)
    entries = data.get("warnings", [])

    print(f"Found {len(entries)} entries")

    items = []

    for entry in entries:
        identifier = (
            entry.get("id")
            or entry.get("event")
            or (
                f"{entry.get('title', '')}|"
                f"{entry.get('published-date-time', '')}"
            )
        )

        title = (
            entry.get("title")
            or entry.get("warning-type")
            or entry.get("name")
            or "Manitoba Emergency Alert"
        )

        headline = clean_text(entry.get("headline", ""))
        warning_type = clean_text(entry.get("warning-type", ""))
        alert_line = clean_text(entry.get("alert-line", ""))
        severity = clean_text(entry.get("cap-severity", ""))
        urgency = clean_text(entry.get("cap-urgency", ""))

        location_data = entry.get("location") or {}
        location_name = clean_text(location_data.get("value", ""))

        summary_parts = [
            warning_type,
            headline,
            alert_line,
            severity,
            urgency,
            location_name,
        ]

        summary = " | ".join(
            part for part in summary_parts if part
        )

        published = (
            entry.get("published-date-time")
            or entry.get("updatedAt")
            or entry.get("web-message-updated-at")
            or ""
        )

        items.append(
            {
                "id": clean_text(identifier),
                "source": source_name,
                "title": clean_text(title),
                "link": "https://mbready.manitoba.ca/",
                "published": clean_text(published),
                "summary": summary,
            }
        )

    return items


def parse_quebec_json(
    source_name: str,
    source_url: str
) -> list[dict]:
    entries = get_json(source_url)

    if not isinstance(entries, list):
        raise ValueError("Quebec API did not return a list")

    print(f"Found {len(entries)} entries")

    items = []

    for entry in entries:
        identifier = (
            entry.get("id")
            or entry.get("identifier")
            or entry.get("alertId")
            or entry.get("uuid")
        )

        title = (
            entry.get("title")
            or entry.get("name")
            or entry.get("event")
            or entry.get("headline")
            or "Quebec Emergency Alert"
        )

        summary = (
            entry.get("description")
            or entry.get("message")
            or entry.get("headline")
            or entry.get("summary")
            or ""
        )

        published = (
            entry.get("published")
            or entry.get("sent")
            or entry.get("updated")
            or entry.get("date")
            or ""
        )

        link = (
            entry.get("url")
            or entry.get("link")
            or "https://alerte.gouv.qc.ca/en"
        )

        if not identifier:
            identifier = f"{title}|{published}|{link}"

        items.append(
            {
                "id": clean_text(identifier),
                "source": source_name,
                "title": clean_text(title),
                "link": clean_text(link),
                "published": clean_text(published),
                "summary": clean_text(summary),
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
            if source_type in {
                "saskatchewan_json",
                "nova_scotia_json",
            }:
                items = parse_alertable_json(
                    source_name,
                    source_url
                )

            elif source_type == "manitoba_json":
                items = parse_manitoba_json(
                    source_name,
                    source_url
                )

            elif source_type == "quebec_json":
                items = parse_quebec_json(
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

    RSS_FILE.write_text(
        build_rss(all_items),
        encoding="utf-8"
    )

    save_seen_items(updated_seen_items)

    new_count = len(updated_seen_items - seen_items)

    print(f"RSS items written: {len(all_items)}")
    print(f"New items found: {new_count}")


if __name__ == "__main__":
    main()
