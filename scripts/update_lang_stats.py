# scripts/update_lang_stats.py
import os
import re
from collections import defaultdict

import requests

USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_TOKEN"]
API_ROOT = "https://api.github.com"
SESSION = requests.Session()
SESSION.headers.update(
    {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
)

TARGET_LANGS = ["Python", "Jupyter", "C++", "HTML", "CSS", "SQL", "Other"]


def gh_get(url, params=None):
    """
        Send a GET request to the GitHub API using the shared session.

        Args:
            url (str): Full GitHub API endpoint URL.
            params (dict, optional): Query parameters to include in the request.

        Returns:
            dict: JSON-decoded response from the GitHub API.

        Raises:
            HTTPError: If the response status indicates a failure.
    """
    r = SESSION.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_repos(username: str):
    """
        Fetch all repositories owned by a given GitHub user.

        This function automatically paginates through the GitHub API
        until all repositories are collected.

        Args:
            username (str): GitHub username.

        Returns:
            list[dict]: List of repository metadata objects.
    """
    repos = []
    page = 1
    while True:
        data = gh_get(
            f"{API_ROOT}/users/{username}/repos",
            params={"per_page": 100, "page": page, "type": "owner"},
        )
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def fetch_languages(repos):
    """
        Retrieve the language breakdown (in bytes) for all repositories.

        Args:
            repos (list[dict]): List of repository metadata dictionaries from GitHub.

        Returns:
            dict: Mapping from language name to total byte count across all repos.
    """
    totals = defaultdict(int)
    for repo in repos:
        langs = gh_get(repo["languages_url"])
        for name, bytes_ in langs.items():
            totals[name] += bytes_
    return totals

def bucket_languages(lang_bytes: dict):
    """
        Group raw language byte counts into predefined language buckets.

        Languages are normalized and placed into one of the target groups:
        Python, Jupyter, C++, HTML, CSS, SQL, or Other.

        Args:
            lang_bytes (dict): Raw language-to-byte mapping from GitHub.

        Returns:
            dict: Bucketed language byte totals.
    """
    buckets = {k: 0 for k in TARGET_LANGS}
    for lang, value in lang_bytes.items():
        lname = lang.lower()
        if lname == "python":
            buckets["Python"] += value
        elif "jupyter" in lname:
            buckets["Jupyter"] += value
        elif lname in {"c++", "cxx"}:
            buckets["C++"] += value
        elif lname in {"html", "html+erb"}:
            buckets["HTML"] += value
        elif "css" in lname:
            buckets["CSS"] += value
        elif "sql" in lname:
            buckets["SQL"] += value
        else:
            buckets["Other"] += value
    return buckets

def compute_percentages(buckets: dict):
    """
        Convert byte totals into percentage contributions.

        Percentages are rounded to two decimals and normalized
        so that the total is approximately 100%.

        Args:
            buckets (dict): Language bucket totals in bytes.

        Returns:
            dict: Mapping of language to its percentage share.
    """
    total = sum(buckets.values()) or 1
    perc = {}

    for k, v in buckets.items():
        perc[k] = round((v * 100.0 / total), 2)

    # normalize gần 100, nếu cần
    diff = round(100.0 - sum(perc.values()), 2)
    
    if abs(diff) > 0.01:
        perc["Other"] = max(0.0, perc.get("Other", 0.0) + diff)

    return perc

def build_badge(lang: str, pct: int) -> str:
    """
        Construct a Shields.io badge URL for a language percentage.

        Args:
            lang (str): Language bucket name.
            pct (float or int): Percentage value for the language.

        Returns:
            str: Markdown-formatted badge image.
    """
    if lang == "C++":
        label = "C%2B%2B"
        logo = "c%2B%2B"
    elif lang == "SQL":
        label = "SQL"
        logo = "mysql"
    elif lang == "Python":
        label = "Python"
        logo = "python"
    elif lang == "Jupyter":
        label = "Jupyter"
        logo = "jupyter"
    elif lang == "HTML":
        label = "HTML"
        logo = "html5"
    elif lang == "CSS":
        label = "CSS"
        logo = "css3"
    else:
        label = "Other"
        logo = ""
    color = "blue"
    if lang == "Python":
        color = "yellowgreen"
    elif lang == "HTML":
        color = "orange"
    elif lang == "CSS":
        color = "blue"
    elif lang == "SQL":
        color = "darkblue"
    elif lang == "Jupyter":
        color = "orange"
    elif lang == "Other":
        color = "lightgrey"

    base = f"https://img.shields.io/badge/{label}-{pct}%25-{color}?style=flat"
    if logo:
        base += f"&logo={logo}"
    return f"![{lang}]({base})"

def build_markdown_row(perc: dict) -> str:
    """
        Create the full Markdown table row containing all language badges.

        Args:
            perc (dict): Mapping of languages to their percentage values.

        Returns:
            str: Markdown string containing a table row with badges.
    """
    order = ["Python", "Jupyter", "C++", "HTML", "CSS", "SQL", "Other"]
    badges = [build_badge(lang, perc.get(lang, 0)) for lang in order]
    badges_str = " ".join(badges)
    grade_badge = "![Grade](https://img.shields.io/badge/Overall-A%2B-brightgreen?style=flat&logo=github)"
    row = (
        "| 🏅 Grade (Stars) | 📚 Language Breakdown |\n"
        "|------------------|----------------------|\n"
        f"| {grade_badge} | {badges_str} |\n"
    )
    return row

def update_readme(row_md: str):
    """
        Insert or update the language statistics block inside README.md.

        Stats are placed between special markers:
            <!-- STATS_START -->
            <!-- STATS_END -->

        If the block does not exist, it is appended to the README.

        Args:
            row_md (str): Markdown row containing language badges.
    """
    path = "README.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    start = "<!-- STATS_START -->"
    end = "<!-- STATS_END -->"

    if start not in content or end not in content:
        block = f"{start}\n\n{row_md}\n{end}"
        content = content.rstrip() + "\n\n" + block + "\n"
    else:
        pattern = re.compile(
            rf"{re.escape(start)}.*?{re.escape(end)}",
            re.DOTALL,
        )
        block = f"{start}\n\n{row_md}\n{end}"
        content = pattern.sub(block, content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    repos = fetch_repos(USERNAME)
    lang_bytes = fetch_languages(repos)
    buckets = bucket_languages(lang_bytes)
    perc = compute_percentages(buckets)
    row_md = build_markdown_row(perc)
    update_readme(row_md)

if __name__ == "__main__":
    main()
