import json
import os
import requests
import argparse
import logging
import time
from github import Auth, Github

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
RATE_LIMIT_WAIT = 60  # seconds


def _handle_rate_limit(response, context=""):
    """Handle rate limit by waiting until reset time.

    Args:
        response: The HTTP response object with rate limit headers
        context: Optional context string for logging (e.g., "issue #123")
    """
    reset_time = response.headers.get("X-RateLimit-Reset")
    if reset_time:
        wait_time = max(int(reset_time) - int(time.time()), 0) + 1
        logging.warning(
            f"Rate limit hit{' for ' + context if context else ''}, waiting {wait_time}s until reset..."
        )
        time.sleep(wait_time)
    else:
        logging.warning(
            f"Rate limit hit{' for ' + context if context else ''}, waiting {RATE_LIMIT_WAIT}s..."
        )
        time.sleep(RATE_LIMIT_WAIT)


def _log_retry(error_type, context, attempt, max_retries, error=None):
    """Log retry attempts with consistent formatting.

    Args:
        error_type: Type of error ("Connection error", "Error checking comments", etc.)
        context: Context string (e.g., "page 5", "issue #123")
        attempt: Current attempt number (0-indexed)
        max_retries: Maximum number of retries
        error: Optional error object to include in message
    """
    error_msg = f": {error}" if error else ""
    if attempt < max_retries - 1:
        logging.warning(
            f"{error_type} for {context} (attempt {attempt + 1}/{max_retries}){error_msg}"
        )
    else:
        logging.error(
            f"Failed: {error_type} for {context} after {max_retries} attempts{error_msg}"
        )


def fetch_additional_issue_data(repo: str, token: str) -> dict:
    """Fetch additional issue metadata from GitHub API."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",  # Required for timeline API
    }
    add_cols = {}
    page = 1
    base_url = f"https://api.github.com/repos/{repo}/issues"

    while True:
        url = f"{base_url}?state=all&per_page=100&page={page}"

        # Retry logic for pagination request
        for attempt in range(MAX_RETRIES):
            try:
                result = requests.get(url, headers=headers, timeout=10)
                if result.status_code == 200:
                    break
                elif result.status_code == 403:
                    _handle_rate_limit(result)
                    continue
                else:
                    logging.error(
                        f"GitHub API error {result.status_code}: {result.text}"
                    )
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        return add_cols
            except requests.exceptions.RequestException as e:
                _log_retry(
                    "Connection error", f"{repo} page {page}", attempt, MAX_RETRIES, e
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    return add_cols

        issues = result.json()
        if not issues:
            break

        for issue in issues:
            if "pull_request" in issue:
                continue  # Skip PRs

            has_linked_pr = False
            issue_number = issue["number"]

            # Only check for linked PRs on OPEN issues (to reduce API calls)
            if issue["state"] == "open":
                timeline_url = f"{base_url}/{issue_number}/timeline"

                # Retry logic for timeline API
                for attempt in range(MAX_RETRIES):
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
                            _handle_rate_limit(
                                timeline_result, f"issue #{issue_number}"
                            )
                            continue
                        else:
                            logging.warning(
                                f"Could not fetch timeline for {repo} issue #{issue_number}: {timeline_result.status_code}"
                            )
                            break  # Don't retry for other errors

                    except requests.exceptions.RequestException as e:
                        _log_retry(
                            "Connection error",
                            f"{repo} issue #{issue_number}",
                            attempt,
                            MAX_RETRIES,
                            e,
                        )
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(
                                RETRY_DELAY * (attempt + 1)
                            )  # Exponential backoff
                        else:
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


def add_maintainer_responses(data: dict, repo: str, token: str, maintainers: list):
    """Add maintainer_responded field to each issue."""
    if not maintainers:
        return

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
            # Retry logic for fetching comments
            for attempt in range(MAX_RETRIES):
                try:
                    gh_issue = gh_repo.get_issue(number=issue_number)
                    for comment in gh_issue.get_comments():
                        if comment.user.login.lower() in maintainers_lower:
                            maintainer_responded = True
                            break
                    break  # Success, exit retry loop
                except Exception as e:
                    _log_retry(
                        "Error checking comments",
                        f"{repo} issue #{issue_number}",
                        attempt,
                        MAX_RETRIES,
                        e,
                    )
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        break
        else:
            logging.warning(f"Could not extract issue number from url: {url}")
        issue["maintainer_responded"] = maintainer_responded


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
        add_maintainer_responses(data, repo, token, maintainers)

    # Enrich with milestone/assignees/has_linked_pr
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
