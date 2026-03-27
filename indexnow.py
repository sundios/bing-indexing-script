#!/usr/bin/env python3
"""
IndexNow Submission Tool
Reads URLs from a CSV or sitemap and submits them in batches to IndexNow-compatible search engines.

Usage:
    python indexnow.py --csv urls.csv --key YOUR_KEY --host example.com
    python indexnow.py --sitemap https://example.com/sitemap.xml --key YOUR_KEY --host example.com
    python indexnow.py --sitemap sitemap.xml --key YOUR_KEY --host example.com --batch-size 500 --engine bing
"""

import argparse
import csv
import json
import sys
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

# Supported IndexNow-compatible endpoints
ENGINES = {
    "indexnow": "https://api.indexnow.org/IndexNow",
    "bing":     "https://www.bing.com/indexnow",
    "yandex":   "https://yandex.com/indexnow",
}

MAX_BATCH_SIZE = 10_000


def load_urls_from_csv(path: str, column: str = None) -> list[str]:
    """Read URLs from a CSV file. Auto-detects the URL column if not specified."""
    urls = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        if column:
            if column not in headers:
                sys.exit(f"Column '{column}' not found in CSV. Available: {headers}")
            col = column
        else:
            # Auto-detect: prefer columns named 'url', 'URL', 'address', etc.
            candidates = [h for h in headers if "url" in h.lower() or "address" in h.lower() or "link" in h.lower()]
            if not candidates:
                sys.exit(f"Could not auto-detect URL column. Available columns: {headers}\nUse --column to specify.")
            col = candidates[0]
            print(f"[info] Using column '{col}' for URLs")

        for row in reader:
            val = row.get(col, "").strip()
            if val and val.startswith("http"):
                urls.append(val)

    return urls


def load_urls_from_sitemap(source: str) -> list[str]:
    """
    Parse URLs from a sitemap XML (local file or remote URL).
    Handles sitemap index files by recursively fetching child sitemaps.
    """
    urls = []

    def parse(content: bytes) -> list[str]:
        found = []
        root = ET.fromstring(content)
        ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        prefix = f"{{{ns}}}" if ns else ""

        # Sitemap index — recurse into each child sitemap
        if root.tag in (f"{prefix}sitemapindex", "sitemapindex"):
            for sitemap in root.findall(f"{prefix}sitemap"):
                loc = sitemap.findtext(f"{prefix}loc", "").strip()
                if loc:
                    print(f"[info] Fetching child sitemap: {loc}")
                    try:
                        resp = requests.get(loc, timeout=30)
                        resp.raise_for_status()
                        found.extend(parse(resp.content))
                    except requests.RequestException as e:
                        print(f"[warn] Could not fetch {loc}: {e}")
        else:
            # Regular sitemap — collect <loc> entries
            for url_el in root.findall(f"{prefix}url"):
                loc = url_el.findtext(f"{prefix}loc", "").strip()
                if loc:
                    found.append(loc)

        return found

    if source.startswith("http"):
        print(f"[info] Fetching sitemap: {source}")
        resp = requests.get(source, timeout=30)
        resp.raise_for_status()
        urls = parse(resp.content)
    else:
        with open(source, "rb") as f:
            urls = parse(f.read())

    return urls


def extract_host(urls: list[str]) -> str:
    """Return the most common host found in the URL list."""
    from collections import Counter
    hosts = [urlparse(u).netloc for u in urls if urlparse(u).netloc]
    if not hosts:
        sys.exit("[error] Could not determine host from URLs.")
    host, count = Counter(hosts).most_common(1)[0]
    if count < len(hosts):
        print(f"[warn] Multiple hosts found. Using most common: '{host}' ({count}/{len(urls)} URLs)")
    return host


def submit_batch(
    urls: list[str],
    host: str,
    key: str,
    key_location: str,
    endpoint: str,
    dry_run: bool,
) -> bool:
    """Submit a single batch of URLs. Returns True on success."""
    payload = {
        "host": host,
        "key": key,
        "keyLocation": key_location,
        "urlList": urls,
    }

    if dry_run:
        print(f"[dry-run] Would POST {len(urls)} URLs to {endpoint}")
        print(json.dumps(payload, indent=2))
        return True

    try:
        resp = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"[error] Request failed: {e}")
        return False

    status_messages = {
        200: "OK — URLs submitted successfully.",
        202: "Accepted — received, key validation pending.",
        400: "Bad Request — invalid format. Check host/key/urlList.",
        403: "Forbidden — key not found or does not match.",
        422: "Unprocessable — URLs don't match host, or key schema mismatch.",
        429: "Too Many Requests — slow down, potential spam detection.",
    }

    msg = status_messages.get(resp.status_code, f"Unexpected status: {resp.text[:200]}")
    success = resp.status_code in (200, 202)
    level = "ok" if success else "error"
    print(f"[{level}] HTTP {resp.status_code} — {msg}")
    return success


def chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def main():
    parser = argparse.ArgumentParser(
        description="Submit URLs to IndexNow-compatible search engines in batches."
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv",     metavar="FILE",        help="Path to CSV file containing URLs")
    source.add_argument("--sitemap", metavar="FILE_OR_URL", help="Path or URL to sitemap XML")

    parser.add_argument("--key",      required=True,  help="Your IndexNow API key")
    parser.add_argument("--host",                     help="Your domain (e.g. example.com). Auto-detected if omitted.")
    parser.add_argument("--key-location",             help="Full URL to your key file (optional if key is at domain root)")
    parser.add_argument("--column",                   help="CSV column name containing URLs (auto-detected if omitted)")
    parser.add_argument("--batch-size", type=int, default=200, metavar="N",
                        help=f"URLs per request (max {MAX_BATCH_SIZE}, default: 200)")
    parser.add_argument("--engine", default="indexnow", choices=list(ENGINES.keys()),
                        help="Search engine endpoint to submit to (default: indexnow)")
    parser.add_argument("--delay", type=float, default=1.0, metavar="SECONDS",
                        help="Seconds to wait between batch requests (default: 1.0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be sent without actually submitting")

    args = parser.parse_args()

    # Validate batch size
    if not 1 <= args.batch_size <= MAX_BATCH_SIZE:
        sys.exit(f"[error] --batch-size must be between 1 and {MAX_BATCH_SIZE}.")

    # Load URLs
    if args.csv:
        print(f"[info] Reading URLs from CSV: {args.csv}")
        urls = load_urls_from_csv(args.csv, column=args.column)
    else:
        print(f"[info] Reading URLs from sitemap: {args.sitemap}")
        urls = load_urls_from_sitemap(args.sitemap)

    if not urls:
        sys.exit("[error] No URLs found.")

    print(f"[info] {len(urls)} URLs loaded.")

    # Determine host
    host = args.host or extract_host(urls)
    print(f"[info] Host: {host}")

    # Build key location if not provided
    key_location = args.key_location or f"https://{host}/{args.key}.txt"
    print(f"[info] Key location: {key_location}")

    endpoint = ENGINES[args.engine]
    print(f"[info] Endpoint: {endpoint}")
    print(f"[info] Batch size: {args.batch_size} | Delay: {args.delay}s\n")

    # Submit in batches
    batches = list(chunk(urls, args.batch_size))
    success_count = 0
    fail_count = 0

    for i, batch in enumerate(batches, 1):
        print(f"[batch {i}/{len(batches)}] Submitting {len(batch)} URLs...")
        ok = submit_batch(
            urls=batch,
            host=host,
            key=args.key,
            key_location=key_location,
            endpoint=endpoint,
            dry_run=args.dry_run,
        )
        if ok:
            success_count += len(batch)
        else:
            fail_count += len(batch)

        if i < len(batches):
            time.sleep(args.delay)

    print(f"\n[done] {success_count} URLs submitted successfully, {fail_count} failed.")


if __name__ == "__main__":
    main()
