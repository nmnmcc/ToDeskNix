#!/usr/bin/env python3
"""Scrape todesk.com/linux.html and update versions.json with new RPM versions and SRI hashes."""

import base64
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
VERSIONS_FILE = ROOT / "versions.json"

TODESK_PAGE = "https://www.todesk.com/linux.html"
ARCHIVE_SAVE = "https://web.archive.org/save/"
ARCHIVE_CHECK = "https://web.archive.org/web/2/{url}"
RPM_URL_PATTERN = re.compile(
    r"https://dl\.todesk\.com/linux/todesk-v([\d.]+)-x86_64\.rpm"
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


def discover_version():
    """Fetch the ToDesk Linux page and extract the x86_64 RPM version."""
    print("Fetching todesk.com/linux.html ...")
    body = fetch(TODESK_PAGE)
    if body is None:
        print("Failed to fetch ToDesk page", file=sys.stderr)
        sys.exit(1)
    text = body.decode(errors="replace")
    matches = RPM_URL_PATTERN.findall(text)
    if not matches:
        print(
            "No RPM URL found on the page. The page may use JS rendering.",
            file=sys.stderr,
        )
        print("Try providing the version manually: python update.py <version>")
        sys.exit(1)
    versions = sorted(set(matches), key=version_tuple, reverse=True)
    print(f"  found versions: {', '.join(versions)}")
    return versions


def archive_url_for(version):
    """Check if the RPM is on archive.org, or request archival."""
    original = f"https://dl.todesk.com/linux/todesk-v{version}-x86_64.rpm"
    check = ARCHIVE_CHECK.format(url=original)
    print(f"  checking archive.org for v{version} ...")
    try:
        req = Request(check, headers={"User-Agent": "todesk-nix-updater"})
        with urlopen(req, timeout=30) as r:
            final_url = r.url
            content_length = r.headers.get("Content-Length", "0")
            if int(content_length) > 1_000_000:
                return final_url.replace("/web/", "/web/").replace("http://", "https://")
    except Exception:
        pass

    print(f"  not found on archive.org, requesting archival ...")
    save_url = ARCHIVE_SAVE + original
    try:
        req = Request(save_url, headers={"User-Agent": "todesk-nix-updater"})
        with urlopen(req, timeout=120) as r:
            final_url = r.url
            if "web.archive.org" in final_url:
                # Convert to if_ URL for raw content
                final_url = re.sub(r"/web/(\d+)/", r"/web/\1if_/", final_url)
                return final_url
    except Exception as e:
        print(f"  archival request failed: {e}", file=sys.stderr)

    return None


def fetch_and_hash(url):
    """Download the RPM and compute its SRI hash."""
    print(f"  downloading {url} ...")
    data = fetch(url, timeout=300)
    if data is None or len(data) < 1_000_000:
        return None
    sri = sha256_to_sri(data)
    print(f"  hash: {sri} ({len(data)} bytes)")
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

    if len(sys.argv) > 1:
        new_versions = [sys.argv[1]]
        print(f"Using manually provided version: {new_versions[0]}")
    else:
        all_versions = discover_version()
        new_versions = [v for v in all_versions if v not in existing_versions]

    if not new_versions:
        print("--- up to date ---")
        return

    print(f"New versions to process: {', '.join(new_versions)}")

    for version in new_versions:
        print(f"\nProcessing v{version} ...")
        url = archive_url_for(version)
        if url is None:
            print(f"  SKIP: could not get archive URL for v{version}")
            continue

        # Ensure if_ in URL for raw content
        if "if_/" not in url:
            url = re.sub(r"/web/(\d+)/", r"/web/\1if_/", url)

        sri = fetch_and_hash(url)
        if sri is None:
            print(f"  SKIP: download/hash failed for v{version}")
            continue

        existing.setdefault("versions", {})[version] = {
            "x86_64-linux": {
                "url": url,
                "hash": sri,
            }
        }

    # Recompute latest
    all_vers = list(existing.get("versions", {}).keys())
    if all_vers:
        existing["latest"] = max(all_vers, key=version_tuple)

    VERSIONS_FILE.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n")
    print(f"\n--- done: {len(existing['versions'])} versions ---")


if __name__ == "__main__":
    main()
