"""List recent PoB issues that may be suitable for a headless regression."""

import argparse
import json
import subprocess
import sys


QUERY = """
query($owner: String!, $repo: String!, $limit: Int!) {
  repository(owner: $owner, name: $repo) {
    issues(first: $limit, states: OPEN, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        number
        title
        url
        labels(first: 15) { nodes { name } }
        closedByPullRequestsReferences(first: 1, includeClosedPrs: false) { totalCount }
      }
    }
  }
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="PathOfBuildingCommunity/PathOfBuilding")
    parser.add_argument("--limit", type=int, default=50, help="number of recent open issues to scan (1–100)")
    args = parser.parse_args()
    owner, _, repo = args.repo.partition("/")
    if not owner or not repo or "/" in repo:
        parser.error("--repo must be OWNER/REPO")
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")

    try:
        response = subprocess.check_output(
            ["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}",
             "-f", f"repo={repo}", "-F", f"limit={args.limit}"],
            encoding="utf-8",
        )
    except FileNotFoundError:
        parser.exit(1, "The GitHub CLI (gh) must be installed and authenticated.\n")
    except subprocess.CalledProcessError as failure:
        return failure.returncode

    issues = json.loads(response)["data"]["repository"]["issues"]["nodes"]
    for issue in issues:
        if issue["closedByPullRequestsReferences"]["totalCount"]:
            continue
        labels = [label["name"] for label in issue["labels"]["nodes"]]
        if labels and not any(label == "bug" or label.startswith("bug:") for label in labels):
            continue
        print(f"#{issue['number']}\t{issue['title']}\t{', '.join(labels)}\t{issue['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
