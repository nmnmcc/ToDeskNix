#!/usr/bin/env python3
"""Scrape todesk.com/linux.html and archive.org CDX API to update versions.json."""

import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
VERSIONS_FILE = ROOT / "versions.json"

TODESK_PAGE = "https://www.todesk.com/linux.html"
CDX_API = "https://web.archive.org/cdx/search/cdx"
ARCHIVE_SAVE = "https://web.archive.org/save/"

MIN_FILE_SIZE = 5_000_000

DEB_URL_RE = re.compile(
    r"https://dl\.todesk\.com/linux/todesk-v([\d.]+)-amd64\.deb"
)
ARCHIVE_VER_RE = re.compile(
    r"todesk-v([\d.]+)-amd64\.deb"
)


def fetch(url, timeout=30):
    try:
        req = Request(url, headers={"User-Agent": "todesk-nix-updater"})
        with urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        print(f"  fetch failed: {e}", file=sys.stderr)
        return None


def sha256_to_sri(data):
    digest = hashlib.sha256(data).digest()
    return "sha256-" + base64.b64encode(digest).decode()


def version_tuple(v):
    return tuple(int(x) for x in v.split("."))


def discover_from_page():
    """Scrape the ToDesk page for the current version (may fail due to JS rendering)."""
    print("Fetching todesk.com/linux.html ...")
    body = fetch(TODESK_PAGE)
    if body is None:
        return []
    text = body.decode(errors="replace")
    deb = DEB_URL_RE.findall(text)
    versions = sorted(set(deb), key=version_tuple, reverse=True)
    if versions:
        print(f"  found on page: {', '.join(versions)}")
    else:
        print("  page uses JS rendering, no versions found directly")
    return versions


def discover_from_cdx():
    """Query Wayback Machine CDX API for all archived ToDesk Linux packages."""
    print("Querying archive.org CDX API ...")
    results = {}

    for domain in ("dl.todesk.com", "newdl.todesk.com"):
        url = (
            f"{CDX_API}?url={domain}/linux/todesk-v*-amd64.deb"
            f"&matchType=prefix&output=json"
            f"&fl=original,timestamp,statuscode,length"
            f"&filter=statuscode:200"
        )
        body = fetch(url, timeout=60)
        if body is None:
            continue
        rows = json.loads(body)
        for row in rows[1:]:
            original, timestamp, status, length = row
            if int(length) < MIN_FILE_SIZE:
                continue
            m = ARCHIVE_VER_RE.search(original)
            if not m:
                continue
            version = m.group(1)
            archive_url = f"https://web.archive.org/web/{timestamp}if_/{original}"

            if version not in results or int(length) > results[version]["size"]:
                results[version] = {
                    "url": archive_url,
                    "size": int(length),
                }

    versions = sorted(results.keys(), key=version_tuple)
    print(f"  found in archive: {', '.join(versions)}")
    return results


def archive_new_version(version):
    """Request archive.org to save a new ToDesk deb."""
    for domain in ("dl.todesk.com", "newdl.todesk.com"):
        suffix = f"todesk-v{version}-amd64.deb"
        original = f"https://{domain}/linux/{suffix}"
        print(f"  requesting archive.org to save {suffix} ({domain}) ...")
        save_url = ARCHIVE_SAVE + original
        try:
            req = Request(save_url, headers={"User-Agent": "todesk-nix-updater"})
            with urlopen(req, timeout=180) as r:
                final_url = r.url
                content_length = int(r.headers.get("Content-Length", "0"))
                if "web.archive.org" in final_url and content_length > MIN_FILE_SIZE:
                    final_url = re.sub(r"/web/(\d+)/", r"/web/\1if_/", final_url)
                    print(f"  archived: {final_url} ({content_length} bytes)")
                    return final_url
        except Exception as e:
            print(f"  save failed for {fmt}: {e}", file=sys.stderr)
    return None


def fetch_and_hash(url):
    """Download and compute SRI hash."""
    print(f"  downloading ({url.split('/')[5]}) ...")
    data = fetch(url, timeout=600)
    if data is None or len(data) < MIN_FILE_SIZE:
        print(f"  SKIP: too small or failed ({len(data) if data else 0} bytes)")
        return None
    sri = sha256_to_sri(data)
    print(f"  hash: {sri} ({len(data):,} bytes)")
    return sri


def load_existing():
    if VERSIONS_FILE.exists():
        try:
            return json.loads(VERSIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"latest": None, "versions": {}}


def main():
    existing = load_existing()
    existing_versions = set(existing.get("versions", {}).keys())

    if len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        print("=== Backfill mode: collecting all historical versions ===\n")
        cdx_results = discover_from_cdx()
        to_process = {
            v: info for v, info in cdx_results.items()
            if v not in existing_versions
        }
    elif len(sys.argv) > 1:
        version = sys.argv[1]
        print(f"Using manually provided version: {version}")
        to_process = {version: None}
    else:
        page_versions = discover_from_page()
        cdx_results = discover_from_cdx()
        all_known = set(page_versions) | set(cdx_results.keys())
        to_process = {
            v: cdx_results.get(v)
            for v in all_known
            if v not in existing_versions
        }

    if not to_process:
        print("--- up to date ---")
        return

    print(f"\nVersions to process: {', '.join(sorted(to_process, key=version_tuple))}\n")

    for version in sorted(to_process, key=version_tuple):
        print(f"Processing v{version} ...")
        info = to_process[version]

        if info and "url" in info:
            url = info["url"]
        else:
            url = archive_new_version(version)
            if url is None:
                print(f"  SKIP: could not archive v{version}\n")
                continue

        sri = fetch_and_hash(url)
        if sri is None:
            print(f"  SKIP: download/hash failed for v{version}\n")
            continue

        existing.setdefault("versions", {})[version] = {
            "x86_64-linux": {
                "url": url,
                "hash": sri,
            }
        }
        print()

    all_vers = list(existing.get("versions", {}).keys())
    if all_vers:
        existing["latest"] = max(all_vers, key=version_tuple)

    VERSIONS_FILE.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
    print(f"--- done: {len(existing['versions'])} versions ---")


if __name__ == "__main__":
    main()
