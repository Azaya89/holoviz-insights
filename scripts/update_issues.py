import json
import os
import requests
import argparse
import logging
import time
from github import Auth, Github

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def fetch_additional_issue_data(repo: str, token: str) -> dict:
    """Fetch additional issue metadata from GitHub API."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.mockingbird-preview+json",  # Required for timeline API
    }
    add_cols = {}
    page = 1
    base_url = f"https://api.github.com/repos/{repo}/issues"

    while True:
        url = f"{base_url}?state=all&per_page=100&page={page}"
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

            # Check for linked PRs using timeline API
            has_linked_pr = False
            issue_number = issue["number"]
            timeline_url = f"{base_url}/{issue_number}/timeline"

            # Retry logic for timeline API
            max_retries = 3
            retry_delay = 2  # seconds

            for attempt in range(max_retries):
                try:
                    timeline_result = requests.get(
                        timeline_url, headers=headers, timeout=10
                    )

                    if timeline_result.status_code == 200:
                        timeline_events = timeline_result.json()
                        for event in timeline_events:
                            if event.get("event") == "cross-referenced":
                                source = event.get("source", {})
                                source_issue = source.get("issue", {})
                                # Check if the cross-reference is a PR
                                if "pull_request" in source_issue:
                                    has_linked_pr = True
                                    break
                        break  # Success, exit retry loop
                    elif timeline_result.status_code == 403:
                        # Rate limit hit
                        logging.warning(
                            f"Rate limit hit for issue #{issue_number}, waiting..."
                        )
                        time.sleep(60)  # Wait 1 minute before retrying
                        continue
                    else:
                        logging.warning(
                            f"Could not fetch timeline for issue #{issue_number}: {timeline_result.status_code}"
                        )
                        break  # Don't retry for other errors

                except requests.exceptions.RequestException as e:
                    if attempt < max_retries - 1:
                        logging.warning(
                            f"Connection error for issue #{issue_number} (attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                    else:
                        logging.error(
                            f"Failed to fetch timeline for issue #{issue_number} after {max_retries} attempts: {e}"
                        )
                        break

            add_cols[issue["html_url"]] = {
                "milestone": issue["milestone"]["title"]
                if issue.get("milestone")
                else None,
                "assignees": [a["login"] for a in issue.get("assignees", [])],
                "has_linked_pr": has_linked_pr,
            }

            # Small delay between requests to avoid hitting rate limits
            time.sleep(0.1)
        page += 1

    return add_cols


def merge_and_save(
    original_json: str, output_json: str, repo: str, token: str, maintainers=None
):
    with open(original_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "issues" not in data:
        logging.error("Input JSON missing 'issues' key.")
        return

    extra_data = fetch_additional_issue_data(repo, token)
    # Add maintainer_responded field for each issue
    if maintainers is not None:
        g = Github(auth=Auth.Token(token))
        gh_repo = g.get_repo(repo)
        maintainers_lower = [m.lower() for m in maintainers]
        for issue in data["issues"]:
            # Extract issue number from html_url
            url = issue.get("html_url", "")
            try:
                issue_number = int(url.rstrip("/").split("/")[-1])
            except Exception:
                issue_number = None
            maintainer_responded = False
            if issue_number is not None:
                try:
                    gh_issue = gh_repo.get_issue(number=issue_number)
                    for comment in gh_issue.get_comments():
                        if comment.user.login.lower() in maintainers_lower:
                            maintainer_responded = True
                            break
                except Exception as e:
                    logging.warning(
                        f"Error checking comments for issue #{issue_number}: {e}"
                    )
            else:
                logging.warning(f"Could not extract issue number from url: {url}")
            issue["maintainer_responded"] = maintainer_responded
    # Enrich with milestone/assignees
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
        merge_and_save(
            args.input_json, args.output_json, args.repo, token, maintainers=maintainers
        )
