import json
import os
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml


FEEDS_FILE = Path("feeds.yaml")
STATE_FILE = Path("seen_items.json")
OUTPUT_FILE = Path("new_items.json")


def load_feeds() -> list[dict]:
    with FEEDS_FILE.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    feeds = config.get("feeds", [])

    if not feeds:
        raise ValueError("No feeds were found in feeds.yaml")

    return feeds


def load_seen_items() -> set[str]:
    if not STATE_FILE.exists():
        return set()

    with STATE_FILE.open("r", encoding="utf-8") as file:
        return set(json.load(file))


def save_json(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def entry_identifier(entry) -> str:
    return (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
        or f"{entry.get('title', '')}|{entry.get('published', '')}"
    )


def main() -> None:
    feeds = load_feeds()
    seen_items = load_seen_items()
    updated_seen_items = set(seen_items)
    new_items = []

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

            if identifier in seen_items:
                continue

            new_items.append(
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
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            updated_seen_items.add(identifier)

    save_json(OUTPUT_FILE, new_items)
    save_json(STATE_FILE, sorted(updated_seen_items))

    print(f"New items found: {len(new_items)}")

    github_output = os.environ.get("GITHUB_OUTPUT")

    if github_output:
        with open(github_output, "a", encoding="utf-8") as file:
            file.write(f"new_item_count={len(new_items)}\n")


if __name__ == "__main__":
    main()
