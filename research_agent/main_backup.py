"""
AppIntel AI - Source-first research collector

Fetches the supplied 100 app URLs, records website metadata,
detects API/auth/MCP keyword signals, and exports JSON and CSV.

Important:
Keyword detection is discovery only. It does not prove authentication,
pricing/access requirements, API availability, or MCP support.
"""

import json
import time
import re
import csv
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------
# PROJECT PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

INPUT = ROOT / "data" / "apps.json"
OUT_JSON = ROOT / "reports" / "apps_enriched.json"
OUT_CSV = ROOT / "reports" / "apps_enriched.csv"


# --------------------------------------------------
# REQUEST CONFIGURATION
# --------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TERMS = {
    "rest": r"\bREST\b|REST API",
    "graphql": r"\bGraphQL\b",
    "oauth": r"\bOAuth\b",
    "api_key": r"API key|API keys",
    "mcp": r"\bMCP\b|Model Context Protocol",
    "webhook": r"\bwebhooks?\b",
    "developer_portal": r"developer portal|API reference|API documentation",
}


def create_session():
    """Create an HTTP session with retry handling."""

    session = requests.Session()
    session.headers.update(HEADERS)

    retry_strategy = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# --------------------------------------------------
# TEXT CLEANING
# --------------------------------------------------


def clean(text):
    """Remove unnecessary whitespace."""

    return re.sub(r"\s+", " ", text or "").strip()


# --------------------------------------------------
# WEBSITE RESEARCH
# --------------------------------------------------


def inspect_app(app, session):

    result = dict(app)
    url = app["starting_url"]

    print(f"  Fetching: {url}")

    try:

        response = session.get(url, timeout=(10, 25), allow_redirects=True)

        result["http_status"] = str(response.status_code)
        result["resolved_url"] = response.url

        # Parse HTML
        soup = BeautifulSoup(response.text[:1_500_000], "html.parser")

        # Page title
        title = soup.title.get_text(" ", strip=True) if soup.title else ""

        # Meta description
        desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})

        description = desc_tag.get("content", "") if desc_tag else ""

        # Page text
        page_text = clean(soup.get_text(" ", strip=True))[:120000]

        result["page_title"] = clean(title)
        result["description"] = clean(description)

        # Detect keyword signals
        result["signals"] = {
            key: bool(re.search(pattern, page_text, re.I))
            for key, pattern in TERMS.items()
        }

        if response.status_code >= 400:

            result["research_status"] = "HTTP error - manual review"

            result["notes"] = (
                f"HTTP {response.status_code}. "
                "Check the official developer documentation manually."
            )

        else:

            result["research_status"] = "Fetched - requires source review"

            result["notes"] = (
                "Page metadata and keyword signals collected. "
                "These signals are not verified API/auth findings."
            )

    except requests.RequestException as exc:

        result["http_status"] = "FETCH_ERROR"

        result["research_status"] = "Fetch failed - manual review required"

        result["resolved_url"] = ""

        result["page_title"] = ""
        result["description"] = ""

        result["signals"] = {}

        result["notes"] = (
            f"{type(exc).__name__}: {exc}. "
            "Possible causes include timeout, DNS, SSL, "
            "proxy restrictions or website bot protection."
        )

    return result


# --------------------------------------------------
# MAIN RESEARCH PIPELINE
# --------------------------------------------------


def main():

    print("\n===================================")
    print("       APPINTEL AI RESEARCH")
    print("===================================\n")

    if not INPUT.exists():

        print("ERROR: apps.json was not found.")
        print(f"Expected location: {INPUT}")
        return

    apps = json.loads(INPUT.read_text(encoding="utf-8"))

    print(f"Total apps to research: {len(apps)}\n")

    session = create_session()

    results = []

    for index, app in enumerate(apps, 1):

        print(f"[{index:03}/{len(apps)}] " f"{app['app']}")

        result = inspect_app(app, session)

        results.append(result)

        print(f"  Status: {result.get('http_status', 'UNKNOWN')}")

        # Be polite to websites
        time.sleep(0.5)

    # Create reports directory
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    # Export JSON
    OUT_JSON.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Export CSV
    fields = [
        "id",
        "category",
        "app",
        "starting_url",
        "resolved_url",
        "http_status",
        "page_title",
        "description",
        "auth_methods",
        "self_serve_vs_gated",
        "api_surface",
        "mcp_support",
        "buildability_verdict",
        "main_blocker",
        "research_status",
        "human_verified",
        "notes",
    ]

    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as file:

        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")

        writer.writeheader()
        writer.writerows(results)

    # Summary
    successful = sum(
        1
        for item in results
        if item.get("http_status", "").isdigit() and int(item["http_status"]) < 400
    )

    failed = len(results) - successful

    print("\n===================================")
    print("       RESEARCH COMPLETED")
    print("===================================")

    print(f"Total apps: {len(results)}")
    print(f"Successful HTTP responses: {successful}")
    print(f"Failed or blocked requests: {failed}")

    print("\nFiles generated:")

    print(OUT_JSON)
    print(OUT_CSV)

    print("\nIMPORTANT:")
    print(
        "Authentication, API breadth, access requirements, "
        "MCP support and buildability still require evidence review."
    )


if __name__ == "__main__":
    main()
