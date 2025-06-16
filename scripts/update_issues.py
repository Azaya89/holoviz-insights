import json
import os
import requests
import argparse
import logging
from github import Github

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def fetch_additional_issue_data(repo: str, token: str) -> dict:
    """Fetch additional issue metadata from GitHub API."""
    headers = {"Authorization": f"token {token}"}
    add_cols = {}
    page = 1

    while True:
        url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100&page={page}"
        result = requests.get(url, headers=headers)
        if result.status_code != 200:
            logging.error(f"GitHub API error {result.status_code}: {result.text}")
            break
        issues = result.json()
        if not issues:
            break

        for issue in issues:
            if "pull_request" in issue:
                continue  # Skip PRs
            add_cols[issue["html_url"]] = {
                "milestone": issue["milestone"]["title"]
                if issue.get("milestone")
                else None,
                "assignees": [a["login"] for a in issue.get("assignees", [])],
            }

        page += 1

    return add_cols


def merge_and_save(original_json: str, output_json: str, repo: str, token: str):
    with open(original_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "issues" not in data:
        logging.error("Input JSON missing 'issues' key.")
        return

    extra_data = fetch_additional_issue_data(repo, token)
    for issue in data["issues"]:
        url = issue.get("html_url")
        if url in extra_data:
            issue.update(extra_data[url])
        else:
            logging.warning(f"No enrichment data found for issue URL: {url}")

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.remove(original_json)
    logging.info(f"Deleted original JSON file {original_json}")

    logging.info(f"Merged issue file saved to {output_json}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Update issues with maintainer response info."
    )
    parser.add_argument("input_json", help="Path to issue-metrics JSON file")
    parser.add_argument("repo", help="GitHub repo (e.g. holoviz/panel)")
    parser.add_argument("output_json", help="Path to save updated JSON")
    parser.add_argument(
        "--maintainers",
        type=str,
        default="",
        help="Comma-separated list of maintainers",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    maintainers = [m.strip() for m in args.maintainers.split(",") if m.strip()]

    token = os.getenv("GH_TOKEN")
    if not token:
        logging.error("Missing GH_TOKEN environment variable.")
    else:
        # Load issues from input JSON
        with open(args.input_json) as f:
            issues = json.load(f)

        # For each issue, check if any comment author is a maintainer
        g = Github(token)
        repo = g.get_repo(args.repo)

        for issue in issues["issues"]:
            issue_number = issue.get("number")
            maintainer_responded = False
            try:
                gh_issue = repo.get_issue(number=issue_number)
                for comment in gh_issue.get_comments():
                    if comment.user.login in maintainers:
                        maintainer_responded = True
                        break
            except Exception:
                pass
            issue["maintainer_responded"] = maintainer_responded

        merge_and_save(args.input_json, args.output_json, args.repo, token)
