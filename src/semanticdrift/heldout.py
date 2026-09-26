"""Component D: post-cutoff GitHub C tasks with pinned commits (§7.4)."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from semanticdrift.protocols import ROOT

CUTOFF = "2025-06-01"
SEARCH_QUERY = f"created:>{CUTOFF} language:C stars:1..50 license:mit size:<2000"
INTERESTING = re.compile(
    r"\b(mutex|pthread|spinlock|semaphore|barrier|atomic|lock|unlock|"
    r"queue|dequeue|enqueue|buffer|ring|handshake|protocol|state[_ ]?machine|"
    r"fsm|tcp|syn|ack|producer|consumer|philosopher|commit|abort|"
    r"condvar|condition_variable|wait|signal|broadcast|channel)\b",
    re.I,
)
SKIP_NAME = re.compile(
    r"(hello[-_ ]?world|tutorial|homework|assignment|leetcode|advent)",
    re.I,
)
TOKEN_PATH = ROOT / ".github_token"
DEFAULT_OUT = ROOT / "benchmarks" / "heldout"


def load_token(path: Path = TOKEN_PATH) -> Optional[str]:
    """Optional. Public search works without a token; do not pass tokens through chat."""
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    if env:
        return env
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def _request(url: str, token: Optional[str], accept: str = "application/vnd.github+json") -> Any:
    headers = {
        "Accept": accept,
        "User-Agent": "semanticdrift-heldout",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if accept.endswith("raw"):
                return raw
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        if exc.code in {403, 429} and "rate" in body.lower():
            time.sleep(8)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    if accept.endswith("raw"):
                        return raw
                    return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as retry_exc:
                retry_body = retry_exc.read().decode("utf-8", errors="replace")[:200]
                raise RuntimeError(f"GitHub {retry_exc.code} (rate limited)") from retry_exc
        raise RuntimeError(f"GitHub {exc.code} for {url.split('?')[0]}: {body[:160]}") from exc


def search_repos(
    token: Optional[str],
    pages: int = 4,
    per_page: int = 50,
    query: str = SEARCH_QUERY,
) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    seen = set()
    for page in range(1, pages + 1):
        encoded = urllib.parse.urlencode(
            {
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": per_page,
                "page": page,
            }
        )
        payload = _request(f"https://api.github.com/search/repositories?{encoded}", token)
        items = payload.get("items") or []
        if not items:
            break
        for repo in items:
            key = repo.get("full_name")
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(repo)
        time.sleep(0.8)
    return found


def list_c_files(token: str, owner: str, name: str, sha: str) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{name}/git/trees/{sha}?recursive=1"
    tree = _request(url, token)
    files = []
    for node in tree.get("tree") or []:
        path = node.get("path") or ""
        if node.get("type") != "blob":
            continue
        if not path.lower().endswith((".c", ".h")):
            continue
        size = int(node.get("size") or 0)
        if size < 80 or size > 12_000:
            continue
        files.append({"path": path, "size": size, "sha": node.get("sha")})
    return files


def fetch_file(token: str, owner: str, name: str, path: str, ref: str) -> str:
    quoted = urllib.parse.quote(path)
    url = f"https://api.github.com/repos/{owner}/{name}/contents/{quoted}?ref={ref}"
    raw = _request(url, token, accept="application/vnd.github.raw")
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _interesting(path: str, text: str) -> bool:
    if SKIP_NAME.search(path):
        return False
    blob = path + "\n" + text
    return bool(INTERESTING.search(blob))


def collect_candidates(
    token: Optional[str] = None,
    pages: int = 4,
    max_repos: int = 80,
) -> List[Dict[str, Any]]:
    repos = search_repos(token, pages=pages)
    candidates: List[Dict[str, Any]] = []
    for repo in repos[:max_repos]:
        owner = repo["owner"]["login"]
        name = repo["name"]
        try:
            detail = _request(f"https://api.github.com/repos/{owner}/{name}", token)
            branch = detail.get("default_branch") or "main"
            branch_info = _request(
                f"https://api.github.com/repos/{owner}/{name}/branches/{branch}", token
            )
            commit = branch_info["commit"]["sha"]
            files = list_c_files(token, owner, name, commit)
        except Exception as exc:  # noqa: BLE001 — skip empty/broken repos
            candidates.append(
                {
                    "repo": repo["full_name"],
                    "skipped": True,
                    "reason": str(exc)[:200],
                }
            )
            continue
        kept_files = []
        for item in files:
            if SKIP_NAME.search(item["path"]):
                continue
            try:
                text = fetch_file(token, owner, name, item["path"], commit)
            except Exception:
                continue
            if not _interesting(item["path"], text):
                continue
            kept_files.append(
                {
                    "path": item["path"],
                    "size": item["size"],
                    "blob_sha": item["sha"],
                    "preview": " ".join(text.split())[:240],
                }
            )
            if len(kept_files) >= 3:
                break
        if not kept_files:
            continue
        candidates.append(
            {
                "repo": repo["full_name"],
                "html_url": repo.get("html_url"),
                "created_at": repo.get("created_at"),
                "pushed_at": repo.get("pushed_at"),
                "license": (repo.get("license") or {}).get("spdx_id"),
                "stars": repo.get("stargazers_count"),
                "default_branch": branch,
                "commit": commit,
                "files": kept_files,
                "skipped": False,
            }
        )
        time.sleep(0.2)
    return candidates


def write_candidates(rows: Iterable[Dict[str, Any]], out_dir: Path = DEFAULT_OUT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "candidates.json"
    kept = [r for r in rows if not r.get("skipped")]
    payload = {
        "cutoff": CUTOFF,
        "query": SEARCH_QUERY,
        "n_candidates": len(kept),
        "repos": kept,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
