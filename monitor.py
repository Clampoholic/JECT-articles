
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

ISSN = "2969-8960"
STATE_FILE = Path("seen_articles.json")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

API_URL = f"https://api.crossref.org/journals/{ISSN}/works"

def get_articles():
    response = requests.get(
        API_URL,
        params={
            "rows": 100,
            "sort": "published",
            "order": "desc",
            "select": "DOI,title,author,published,URL,type",
        },
        headers={
            "User-Agent": "JECT-Discord-Article-Monitor/1.0"
        },
        timeout=30,
    )
    response.raise_for_status()

    articles = response.json()["message"]["items"]
    results = []

    for item in articles:
        doi = item.get("DOI")
        if not doi:
            continue

        title = item.get("title", ["Untitled article"])[0]
        authors = item.get("author", [])
        author_names = [
            " ".join(
                filter(None, [a.get("given"), a.get("family")])
            )
            for a in authors[:5]
        ]

        if len(authors) > 5:
            author_names.append("et al.")

        date_parts = (
            item.get("published", {})
            .get("date-parts", [[]])[0]
        )
        date_text = "-".join(
            str(part).zfill(2) if i > 0 else str(part)
            for i, part in enumerate(date_parts)
        )

        results.append({
            "id": doi.lower(),
            "title": title,
            "authors": ", ".join(author_names) or "Not listed",
            "date": date_text or "Not listed",
            "url": f"https://doi.org/{doi}",
            "type": item.get("type", "Article"),
        })

    return list(reversed(results))


def send_to_discord(article):
    if not WEBHOOK.startswith(
        ("https://discord.com/api/webhooks/",
         "https://discordapp.com/api/webhooks/")
    ):
        raise ValueError(
            "Discord webhook is missing or invalid. "
            "Check the GitHub repository secret."
        )

    payload = {
        "username": "JECT Research Alerts",
        "embeds": [{
            "title": article["title"][:256],
            "url": article["url"],
            "color": 3447003,
            "description": (
                "**Journal:** Journal of ExtraCorporeal Technology\n"
                f"**Authors:** {article['authors'][:500]}\n"
                f"**Published:** {article['date']}\n"
                f"**Type:** {article['type']}\n\n"
                "[Read article](" + article["url"] + ")"
            ),
            "footer": {
                "text": "JECT • New research article"
            },
        }],
        "allowed_mentions": {"parse": []},
    }

    response = requests.post(
        WEBHOOK,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()


def main():
    articles = get_articles()
    print(f"Retrieved {len(articles)} JECT article records.")

    if not articles:
        raise RuntimeError(
            "No articles found. State was not changed."
        )

    if STATE_FILE.exists():
        seen = set(json.loads(STATE_FILE.read_text()))
    else:
        seen = {a["id"] for a in articles}
        STATE_FILE.write_text(
            json.dumps(sorted(seen), indent=2)
        )
        print(
            "First run: saved existing articles as baseline. "
            "Future articles will trigger alerts."
        )
        return

    new_count = 0

    for article in articles:
        if article["id"] in seen:
            continue

        send_to_discord(article)
        seen.add(article["id"])
        STATE_FILE.write_text(
            json.dumps(sorted(seen), indent=2)
        )
        new_count += 1
        print(f"Sent: {article['title']}")

    print(f"Done. {new_count} new article alerts sent.")


if __name__ == "__main__":
    main()
