import requests
import sys
import os
import logging
from pathlib import Path
import re
import csv

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def classify_release(tag):
    """Classify release as major, minor, or patch based on semver."""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if not match:
        return "unknown"
    major, minor, patch = map(int, match.groups())
    if major > 0 and minor == patch == 0:
        return "major"
    elif patch == 0:
        return "minor"
    return "patch"


def fetch_releases(repo, token):
    """Fetch release tags from GitHub API and classify by type."""
    headers = {"Authorization": f"token {token}"}
    releases = []
    page = 1

    while True:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            logging.error(f"Failed to fetch releases: {res.status_code} {res.text}")
            break
        page_data = res.json()
        if not page_data:
            break
        for r in page_data:
            if not r.get("published_at"):
                continue
            releases.append(
                {
                    "tag": r["tag_name"],
                    "published_at": r["published_at"],
                    "type": classify_release(r["tag_name"]),
                }
            )
        page += 1

    return releases


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python get_releases.py <owner/repo> <output_file.csv>")
        sys.exit(1)

    repo = sys.argv[1]
    output_file = sys.argv[2]
    token = os.getenv("GH_TOKEN")

    if not token:
        print("Error: GH_TOKEN environment variable is not set.")
        sys.exit(1)

    releases = fetch_releases(repo, token)
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["tag", "published_at", "type"])
        writer.writeheader()
        writer.writerows(releases)

    print(f"Saved {len(releases)} releases to {output_file}")
