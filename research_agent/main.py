"""
AppIntel AI - Evidence-based research collector

Collects official application pages and relevant same-domain or
official subdomain developer documentation. Extracts evidence snippets
and source URLs.

IMPORTANT:
Evidence detection is not equivalent to full manual verification.
Missing evidence means only that it was not found in reviewed pages.
"""

import csv
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse, urldefrag

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------
# PROJECT PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

INPUT = ROOT / "data" / "apps.json"

OUT_JSON = ROOT / "reports" / "apps_evidence_v4.json"
OUT_CSV = ROOT / "reports" / "apps_evidence_v4.csv"

MAX_DOC_PAGES = 5
MAX_SNIPPETS_PER_TOPIC = 5
MAX_PAGE_CHARS = 150000
REQUEST_DELAY = 0.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

LOGGER = logging.getLogger("appintel")


# These patterns locate possible evidence.
# They do not independently prove a product capability.


TOPIC_PATTERNS = {
    "authentication": [
        r"\bOAuth(?:\s*2(?:\.0)?)?\b",
        r"\bAPI keys?\b",
        r"\bsecret keys?\b",
        r"\brestricted keys?\b",
        r"\baccess tokens?\b",
        r"\bBearer(?:\s+tokens?|\s+authentication)?\b",
        r"\bBasic\s+(?:authentication|Auth)\b",
        r"\bHTTP Basic(?:\s+authentication|\s+Auth)?\b",
        r"\busername\s+and\s+password\b",
        r"\bJWT\b",
        r"\bpersonal access tokens?\b",
        r"\bPATs?\b",
        r"\bGitHub Apps?\b",
        r"\bOAuth apps?\b",
        r"\bservice accounts?\b",
        r"\bAPI authentication\b",
        r"\bAPI tokens?\b",
        r"\bclient secrets?\b",
        r"\baccess credentials?\b",
        r"\bHTTP Basic\b",
        r"\bBasic Auth\b",
        r"\bAPI login\b",
        r"\bAPI password\b",
        r"\bprivate access tokens?\b",
        r"\binstallation access tokens?\b",
        r"\bapp access tokens?\b",
        r"\bclient secret\b",
        r"\baccess token authentication\b",
    ],
    "api_access": [
        # Keep this topic focused on explicit approval, verification, or
        # entitlement gates. Tokens, scopes, quotas, and rate limits alone
        # do not prove that API access is gated.
        r"\bapply for API access\b",
        r"\bAPI access request\b",
        r"\bAPI access approval\b",
        r"\brequest (?:standard|advanced|production) access\b",
        r"\b(?:standard|advanced|production) access (?:is )?approval\b",
        r"\bproduction approval required\b",
        r"\bAPI access is (?:restricted|limited) to\b",
        r"\bAPI access (?:is )?(?:subject to|requires) approval\b",
        r"\bdeveloper token required\b",
        r"\baccount must be verified\b",
        r"\bverify your account to (?:use|access|enable) the API\b",
        r"\bAPI access requires (?:an? )?(?:active )?subscription\b",
        r"\bsubscription required to (?:use|access) the API\b",
        r"\bAPI access is available only to\b",
        r"\bAPI access is enabled after\b",
        r"\bproduction access requires\b",
    ],
    "api_surface": [
        r"\bREST API\b",
        r"\bRESTful API\b",
        r"\bGraphQL\b",
        r"\bgRPC\b",
        r"\bAPI endpoints?\b",
        r"\bAPI v[0-9]+\b",
        r"\bAPI methods?\b",
        r"\bREST endpoints?\b",
        r"\bGraphQL API\b",
        r"\bAPI resources?\b",
        r"\bAPI reference\b",
        r"\bAPI documentation\b",
        r"\bAPI operations?\b",
        r"\bAPI schema\b",
    ],
    "mcp": [
        r"\bModel Context Protocol\b",
        r"\bMCP server\b",
        r"\bMCP servers\b",
        r"\bremote MCP server\b",
        r"\bhosted MCP server\b",
        r"\bMCP endpoint\b",
        r"\bMCP endpoints\b",
        r"\bMCP client\b",
        r"\bMCP transport\b",
        r"\bconnect(?:ing)? to .* MCP server\b",
    ],
}


DOC_LINK_HINTS = [
    (re.compile(r"\bdeveloper(?:\s+(?:portal|docs?|documentation))?\b", re.I), 5),
    (re.compile(r"\b(?:documentation|docs?)\b", re.I), 4),
    (re.compile(r"\bAPI\s+(?:reference|docs?|documentation)\b", re.I), 5),
    (re.compile(r"\bAPI\b", re.I), 2),
    (re.compile(r"\b(?:authentication|authorization|OAuth)\b", re.I), 3),
    (re.compile(r"\bMCP\b|Model Context Protocol", re.I), 4),
    (re.compile(r"\bquick\s*start\b|\bgetting[-\s.]started\b", re.I), 3),
    (re.compile(r"\b(?:guides?|reference|platform)\b", re.I), 2),
    (re.compile(r"\bintegrations?\b", re.I), -4),
    (re.compile(r"\b(?:login|log-in|sign[- ]?in|sign[- ]?up|register)\b", re.I), -20),
    (re.compile(r"\b(?:pricing|blog|changelog|careers|status)\b", re.I), -5),
]


# --------------------------------------------------
# HTTP SESSION
# --------------------------------------------------


def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)

    retry = Retry(
        total=2,
        connect=2,
        read=1,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# --------------------------------------------------
# TEXT EXTRACTION
# --------------------------------------------------


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get_page_text(soup):
    for element in soup(
        ["script", "style", "noscript", "svg", "header", "footer", "nav", "form"]
    ):
        element.decompose()

    for element in soup.find_all(True):
        if element.attrs is None:
            continue

        role = (element.get("role") or "").lower()
        label = " ".join(
            [
                str(element.get("id") or ""),
                " ".join(element.get("class", [])),
                str(element.get("aria-label") or ""),
            ]
        ).lower()
        if (
            element.parent is not None
            and role in {"navigation", "banner", "contentinfo"}
        ) or (
            element.parent is not None
            and re.search(
                r"\b(?:cookie|consent|breadcrumb|primary-nav|global-nav)\b", label
            )
        ):
            element.decompose()

    content = soup.find("main") or soup.find(attrs={"role": "main"}) or soup
    return clean(content.get_text(" ", strip=True))[:MAX_PAGE_CHARS]


def extract_title(soup):
    return clean(soup.title.get_text(" ", strip=True) if soup.title else "")


# --------------------------------------------------
# DOMAIN HELPERS
# --------------------------------------------------


def normalize_host(host):
    """Normalize a hostname for comparison."""
    host = (host or "").lower().rstrip(".")

    if host.startswith("www."):
        host = host[4:]

    return host


def normalize_url(url):
    """Canonicalize a URL for fetching and duplicate detection."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname or ""

    if scheme not in ("http", "https") or not hostname:
        return urldefrag(url)[0]

    hostname = normalize_host(hostname)
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"

    try:
        port = parsed.port
    except ValueError:
        return urldefrag(url)[0]

    netloc = hostname
    if (
        port
        and not (scheme == "http" and port == 80)
        and not (scheme == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    tracking_parameters = {"fbclid", "gclid", "mc_cid", "mc_eid"}
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in tracking_parameters and not key.lower().startswith("utm_")
    ]
    query.sort()

    return urlunparse((scheme, netloc, path, "", urlencode(query), ""))


def is_same_domain_or_subdomain(link_host, base_host):
    """
    Accept the original hostname and its subdomains.

    Example:
    salesforce.com
    developer.salesforce.com
    docs.salesforce.com

    Unrelated domains are rejected.
    """
    link_host = normalize_host(link_host)
    base_host = normalize_host(base_host)

    return link_host == base_host or link_host.endswith("." + base_host)


# --------------------------------------------------
# DOCUMENTATION LINK DISCOVERY
# --------------------------------------------------


def discover_doc_links(soup, base_url):
    base_host = urlparse(base_url).hostname or ""
    candidates = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        label = clean(
            " ".join(
                [
                    anchor.get_text(" ", strip=True),
                    str(anchor.get("aria-label") or ""),
                    str(anchor.get("title") or ""),
                ]
            )
        )

        if not href:
            continue

        if href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue

        absolute_url, _ = urldefrag(urljoin(base_url, href))
        url_key = normalize_url(absolute_url)

        parsed = urlparse(absolute_url)

        if parsed.scheme not in ("http", "https"):
            continue

        link_host = parsed.hostname or ""

        if not is_same_domain_or_subdomain(link_host, base_host):
            continue

        hint = f"{label} {parsed.path} {parsed.query}"
        score = sum(
            weight for pattern, weight in DOC_LINK_HINTS if pattern.search(hint)
        )

        if score >= 2:
            previous = candidates.get(url_key)
            if previous is None or score > previous[0]:
                candidates[url_key] = (score, absolute_url)

    ranked = sorted(candidates.values(), key=lambda item: (-item[0], item[1]))
    return [url for _, url in ranked[:MAX_DOC_PAGES]]


def is_negated_match(text, start, end):
    """Avoid treating clear statements that deny a capability as evidence."""
    sentence_start = max(text.rfind(separator, 0, start) for separator in ".!?;\n") + 1
    sentence_end_candidates = []
    for separator in ".!?;\n":
        position = text.find(separator, end)
        if position >= 0:
            sentence_end_candidates.append(position)
    sentence_end = (
        min(sentence_end_candidates) if sentence_end_candidates else len(text)
    )
    before = text[sentence_start:start].lower()
    after = text[end:sentence_end].lower()

    denied_state = re.compile(
        r"\b(?:(?:is|are|was|were|be|being|been)\s+)?"
        r"(?:not|never|no longer)\s+(?:(?:currently|generally|strictly)\s+)?"
        r"(?:required|needed|necessary|supported|available|provided|offered|"
        r"enabled|used|possible|mandatory|applicable|unnecessary)\b|"
        r"\b(?:isn't|aren't|wasn't|weren't|doesn't|don't|didn't|can't|cannot|"
        r"won't)\s+(?:(?:currently|generally|strictly)\s+)?"
        r"(?:required|needed|necessary|supported|available|provided|offered|"
        r"enabled|used|possible|mandatory|applicable|unnecessary)\b"
    )
    denied_action = re.compile(
        r"\b(?:does not|doesn't|do not|don't|did not|didn't|cannot|can't|"
        r"will not|won't|never)\s+(?:(?:currently|generally|strictly)\s+)?"
        r"(?:require|need|support|provide|offer|use|request|obtain|access|enable)\b[^.!?;]*$"
    )

    # Catch constructions such as "without ... completing an OAuth flow",
    # where the negation is separated from the matched term by other words.
    denied_without_action = re.compile(
        r"\bwithout\b[^.!?;]{0,100}"
        r"\b(?:completing|starting|initiating|using|setting up|going through)"
        r"\b[^.!?;]*$"
    )

    if (
        denied_state.search(after)
        or re.search(r"\bno\s*$", before)
        or denied_without_action.search(before)
    ):
        return True

    return bool(denied_action.search(before))


# --------------------------------------------------
# EVIDENCE EXTRACTION
# --------------------------------------------------


def extract_evidence(text, source_url):
    """
    Extract a short context window around every matched keyword.

    This ensures the displayed snippet contains the actual match.
    """

    evidence = {}

    for topic, patterns in TOPIC_PATTERNS.items():
        matches = []
        seen_snippets = set()

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.I):
                if is_negated_match(text, match.start(), match.end()):
                    continue

                start = max(0, match.start() - 180)
                end = min(len(text), match.end() + 220)

                snippet = clean(text[start:end])

                if len(snippet) < 10:
                    continue

                if snippet in seen_snippets:
                    continue

                seen_snippets.add(snippet)

                item = {
                    "snippet": snippet,
                    "matched_terms": [match.group(0)],
                    "source_url": source_url,
                }

                matches.append(item)

                if len(matches) >= MAX_SNIPPETS_PER_TOPIC:
                    break

            if len(matches) >= MAX_SNIPPETS_PER_TOPIC:
                break

        evidence[topic] = matches

    return evidence


def merge_evidence(existing, new):
    for topic in TOPIC_PATTERNS:
        for item in new.get(topic, []):
            if item not in existing[topic]:
                existing[topic].append(item)

        existing[topic] = existing[topic][:MAX_SNIPPETS_PER_TOPIC]

    return existing


# --------------------------------------------------
# FETCH ONE PAGE
# --------------------------------------------------


def fetch_page(session, url):
    try:
        response = session.get(
            urldefrag(url)[0],
            timeout=(10, 20),
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return {
                "ok": False,
                "url": response.url,
                "status": response.status_code,
                "error": f"HTTP {response.status_code}",
            }

        content_type = response.headers.get("Content-Type", "").lower()
        if not any(
            content_type.startswith(content_type_prefix)
            for content_type_prefix in (
                "text/html",
                "application/xhtml+xml",
                "text/plain",
                "text/markdown",
                "text/x-markdown",
                "application/markdown",
            )
        ):
            return {
                "ok": False,
                "url": response.url,
                "status": response.status_code,
                "error": f"Unsupported content type: {content_type}",
            }

        soup = BeautifulSoup(
            response.text[:MAX_PAGE_CHARS],
            "html.parser",
        )

        title = extract_title(soup)

        # Save documentation links before page text cleanup.
        doc_links = discover_doc_links(soup, response.url)

        text = get_page_text(soup)

        return {
            "ok": True,
            "url": response.url,
            "status": response.status_code,
            "title": title,
            "text": text,
            "doc_links": doc_links,
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "url": url,
            "status": "FETCH_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
        }


# --------------------------------------------------
# RESEARCH ONE APPLICATION
# --------------------------------------------------


def inspect_app(app, session):
    result = dict(app)

    result.update(
        {
            "http_status": "",
            "resolved_url": "",
            "page_title": "",
            "pages_reviewed": [],
            "authentication_evidence": [],
            "api_access_evidence": [],
            "api_surface_evidence": [],
            "mcp_evidence": [],
            "authentication_status": "NOT_FOUND_IN_REVIEWED_SOURCES",
            "api_access_status": "NOT_FOUND_IN_REVIEWED_SOURCES",
            "api_surface_status": "NOT_FOUND_IN_REVIEWED_SOURCES",
            "mcp_status": "NOT_FOUND_IN_REVIEWED_SOURCES",
            "buildability_verdict": "NEEDS_MANUAL_REVIEW",
            "main_blocker": "Not yet assessed manually",
            "research_status": "",
            "notes": "",
        }
    )

    url = app["starting_url"]

    print(f"  Checking: {url}")

    homepage = fetch_page(session, url)

    if not homepage["ok"]:
        result["http_status"] = str(homepage["status"])
        result["research_status"] = "FETCH_FAILED"
        result["notes"] = (
            f"Unavailable or blocked source: {homepage['url']} "
            f"[{homepage['status']}]: "
            f"{homepage.get('error', 'Page could not be retrieved.')}. "
            "Manual review required; this is not evidence that a feature is unavailable."
        )
        LOGGER.warning(
            "Unavailable homepage: %s (HTTP/status %s): %s",
            homepage["url"],
            homepage["status"],
            homepage.get("error", "Page could not be retrieved."),
        )

        for field in [
            "authentication_status",
            "api_access_status",
            "api_surface_status",
            "mcp_status",
        ]:
            result[field] = "SOURCE_UNAVAILABLE_OR_BLOCKED"

        return result

    result["http_status"] = str(homepage["status"])
    result["resolved_url"] = homepage["url"]
    result["page_title"] = homepage["title"]

    evidence = {topic: [] for topic in TOPIC_PATTERNS}

    reviewed_urls = []
    reviewed_statuses = []
    failed_pages = []
    pages_to_review = [homepage]
    reviewed_keys = {normalize_url(homepage["url"])}
    attempted_keys = set(reviewed_keys)
    LOGGER.info("Reviewed: %s (HTTP %s)", homepage["url"], homepage["status"])

    # Discover documentation links from the homepage.
    doc_links = homepage.get("doc_links", [])

    print(f"  Documentation links discovered: {len(doc_links)}")

    pending_links = list(doc_links)
    queued_keys = {normalize_url(url) for url in pending_links}
    doc_pages_attempted = 0

    # Follow the highest-ranked documentation links, including links on doc hubs.
    while pending_links and doc_pages_attempted < MAX_DOC_PAGES:
        doc_url = pending_links.pop(0)
        doc_key = normalize_url(doc_url)
        if doc_key in attempted_keys:
            continue

        attempted_keys.add(doc_key)
        doc_pages_attempted += 1
        page = fetch_page(session, doc_url)

        if page["ok"]:
            resolved_key = normalize_url(page["url"])
            if resolved_key in reviewed_keys:
                LOGGER.info("Skipped duplicate redirected page: %s", page["url"])
                time.sleep(0.3)
                continue

            reviewed_keys.add(resolved_key)
            pages_to_review.append(page)
            reviewed_statuses.append(f"{page['url']} [HTTP {page['status']}]")
            LOGGER.info("Reviewed: %s (HTTP %s)", page["url"], page["status"])

            for discovered_url in page.get("doc_links", []):
                discovered_key = normalize_url(discovered_url)
                if (
                    discovered_key not in attempted_keys
                    and discovered_key not in queued_keys
                ):
                    pending_links.append(discovered_url)
                    queued_keys.add(discovered_key)
        else:
            failure = (
                f"{page['url']} [{page.get('status')}]: "
                f"{page.get('error', 'Page could not be retrieved.')}"
            )
            failed_pages.append(failure)
            LOGGER.warning("Could not review %s", failure)

        time.sleep(0.3)

    # Extract evidence from each accessible page.
    for page in pages_to_review:
        reviewed_urls.append(page["url"])
        if page is homepage:
            reviewed_statuses.insert(0, f"{page['url']} [HTTP {page['status']}]")

        page_evidence = extract_evidence(
            page["text"],
            page["url"],
        )

        evidence = merge_evidence(
            evidence,
            page_evidence,
        )

    result["pages_reviewed"] = reviewed_urls

    # Store evidence in separate fields.
    result["authentication_evidence"] = evidence["authentication"]
    result["api_access_evidence"] = evidence["api_access"]
    result["api_surface_evidence"] = evidence["api_surface"]
    result["mcp_evidence"] = evidence["mcp"]

    # Evidence status means only that matching text was found.
    for topic in TOPIC_PATTERNS:
        field = f"{topic}_status"

        result[field] = (
            "EVIDENCE_FOUND"
            if evidence[topic]
            else (
                "SOURCE_UNAVAILABLE_OR_BLOCKED"
                if failed_pages
                else "NOT_FOUND_IN_REVIEWED_SOURCES"
            )
        )

    result["research_status"] = "EVIDENCE_COLLECTION_COMPLETED"

    result["notes"] = (
        "Evidence snippets were extracted from accessible pages. "
        "Each finding requires review against its source URL. "
        "Keyword matches do not independently prove a capability. "
        "No evidence found does not prove that a feature is unavailable. "
        "Buildability requires manual review. "
        f"Pages reviewed (HTTP): {'; '.join(reviewed_statuses) or 'none'}."
    )
    if failed_pages:
        result["notes"] += (
            " Unavailable or blocked pages: " + "; ".join(failed_pages) + "."
        )

    return result


# --------------------------------------------------
# REPORT EXPORT
# --------------------------------------------------


def get_output_paths():
    if not OUT_JSON.exists() and not OUT_CSV.exists():
        return OUT_JSON, OUT_CSV

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = 1
    while True:
        run_tag = f"{timestamp}_{suffix:03}"
        json_path = OUT_JSON.with_name(f"apps_evidence_v4_{run_tag}.json")
        csv_path = OUT_CSV.with_name(f"apps_evidence_v4_{run_tag}.csv")
        if not json_path.exists() and not csv_path.exists():
            return json_path, csv_path
        suffix += 1


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    print("\n======================================")
    print("       APPINTEL AI - EVIDENCE AGENT")
    print("======================================\n")

    if not INPUT.exists():
        print(f"ERROR: Input file not found: {INPUT}")
        return

    apps = json.loads(INPUT.read_text(encoding="utf-8"))
    out_json, out_csv = get_output_paths()

    print(f"Applications to research: {len(apps)}\n")

    session = create_session()
    results = []

    for index, app in enumerate(apps, start=1):
        print(f"\n[{index:03}/{len(apps)}] {app['app']}")

        result = inspect_app(app, session)
        results.append(result)

        print(
            f"  HTTP: {result['http_status']} | "
            f"Research: {result['research_status']}"
        )

        time.sleep(REQUEST_DELAY)

    OUT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # JSON retains complete evidence snippets and source URLs.
    out_json.write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # CSV stores nested evidence as JSON strings.
    fields = [
        "id",
        "category",
        "app",
        "starting_url",
        "resolved_url",
        "http_status",
        "page_title",
        "pages_reviewed",
        "authentication_status",
        "authentication_evidence",
        "api_access_status",
        "api_access_evidence",
        "api_surface_status",
        "api_surface_evidence",
        "mcp_status",
        "mcp_evidence",
        "buildability_verdict",
        "main_blocker",
        "research_status",
        "notes",
    ]

    with out_csv.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        for item in results:
            row = dict(item)

            for field in [
                "pages_reviewed",
                "authentication_evidence",
                "api_access_evidence",
                "api_surface_evidence",
                "mcp_evidence",
            ]:
                row[field] = json.dumps(
                    row.get(field, []),
                    ensure_ascii=False,
                )

            writer.writerow(row)

    # Summary
    successful = sum(
        1
        for item in results
        if (
            str(item.get("http_status", "")).isdigit()
            and int(item["http_status"]) < 400
        )
    )

    evidence_counts = {
        topic: sum(
            1 for item in results if item.get(f"{topic}_status") == "EVIDENCE_FOUND"
        )
        for topic in TOPIC_PATTERNS
    }

    print("\n======================================")
    print("       EVIDENCE COLLECTION COMPLETE")
    print("======================================")

    print(f"Total applications: {len(results)}")
    print(f"Successful homepage responses: {successful}")
    print(f"Failed or blocked homepages: {len(results) - successful}")

    print("\nApplications with matching evidence:")

    for topic, count in evidence_counts.items():
        print(f"  {topic}: {count}/{len(results)}")

    print("\nNew files created:")
    print(out_json)
    print(out_csv)

    print("\nIMPORTANT:")
    print("Evidence matches require source review.")
    print("No match does not mean a feature is unavailable.")
    print("Buildability remains a manual assessment.")


if __name__ == "__main__":
    main()
