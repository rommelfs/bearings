"""Publish the canonical backlog into the owner-approved public Bearings repository."""

import json
import subprocess
from pathlib import Path

REPOSITORY = "rommelfs/bearings"


def api(path, data=None):
    args = ["gh", "api", path]
    if data is not None:
        args += ["--method", "POST", "--input", "-"]
    result = subprocess.run(
        args, input=json.dumps(data) if data is not None else None, capture_output=True, text=True
    )
    if result.returncode:
        raise SystemExit("GitHub API request failed; check approved access. No credentials are printed.")
    return json.loads(result.stdout)


def pages(path):
    rows, page = [], 1
    while True:
        batch = api(f"{path}&per_page=100&page={page}")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def main():
    repo = api(f"repos/{REPOSITORY}")
    if repo["full_name"].lower() != REPOSITORY.lower():
        raise SystemExit("Unexpected repository identity; refusing backlog publication.")
    milestones = {m["title"]: m["number"] for m in pages(f"repos/{REPOSITORY}/milestones?state=all")}
    issues = {i["title"] for i in pages(f"repos/{REPOSITORY}/issues?state=all") if "pull_request" not in i}
    backlog = json.loads((Path(__file__).resolve().parents[1] / "docs/backlog.json").read_text())
    created = 0
    for milestone in backlog:
        if milestone["title"] not in milestones:
            row = api(
                f"repos/{REPOSITORY}/milestones",
                {"title": milestone["title"], "description": milestone["description"]},
            )
            milestones[milestone["title"]] = row["number"]
        for issue in milestone["issues"]:
            if issue["title"] not in issues:
                api(f"repos/{REPOSITORY}/issues", {**issue, "milestone": milestones[milestone["title"]]})
                issues.add(issue["title"])
                created += 1
    print(f"Published missing milestones and {created} issues to {REPOSITORY}.")


if __name__ == "__main__":
    main()
