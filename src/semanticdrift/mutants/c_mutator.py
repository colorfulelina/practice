"""Lightweight C mutator on pycparser (methodology §7.2.2).

Operators are restricted to boundary flips, comparison swaps, and off-by-one
shifts so mutants stay plausible. The original file is copied and a single
token is rewritten; the rest of the source is unchanged.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pycparser import c_ast, c_parser

from semanticdrift.sv_sample import DEFAULT_CATEGORIES, SEED

BOUNDARY = {"<": "<=", "<=": "<", ">": ">=", ">=": ">"}
COMPARISON = {"==": "!=", "!=": "=="}
MAX_SOURCE_BYTES = 20_000

FAKE_PREAMBLE = """\
typedef unsigned int size_t;
typedef unsigned int uintptr_t;
typedef int bool;
void abort(void);
void reach_error(void);
void __VERIFIER_error(void);
void __VERIFIER_assert(int cond);
int __VERIFIER_nondet_int(void);
unsigned int __VERIFIER_nondet_uint(void);
int __VERIFIER_nondet_bool(void);
void __assert_fail(const char *a, const char *b, unsigned c, const char *d);
void assume_abort_if_not(int cond);
"""
PREAMBLE_LINES = len(FAKE_PREAMBLE.splitlines()) + 1


def strip_comments(text: str) -> str:
    """Blank out C comments without collapsing line numbers."""

    def block(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"/\*.*?\*/", block, text, flags=re.S)
    text = re.sub(r"//.*?$", "", text, flags=re.M)
    return text


def strip_gcc_extensions(text: str) -> str:
    """Remove GCC-isms that pycparser rejects, keeping line breaks."""

    text = strip_comments(text)

    def _strip_attr(src: str) -> str:
        key = "__attribute__"
        while key in src:
            start = src.find(key)
            index = start + len(key)
            while index < len(src) and src[index].isspace():
                index += 1
            if index >= len(src) or src[index] != "(":
                src = src[:start] + src[start + len(key) :]
                continue
            depth = 0
            end = index
            while end < len(src):
                if src[end] == "(":
                    depth += 1
                elif src[end] == ")":
                    depth -= 1
                    if depth == 0:
                        end += 1
                        break
                end += 1
            src = src[:start] + src[end:]
        return src

    text = _strip_attr(text)
    text = text.replace("__extension__", "")
    text = re.sub(r"\b_Bool\b", "int", text)
    text = re.sub(r"^#\s*include\b.*$", "", text, flags=re.M)
    text = re.sub(r"^#\s*define\b.*$", "", text, flags=re.M)
    return text


def parse_c(source: str) -> c_ast.FileAST:
    cleaned = strip_gcc_extensions(source)
    parser = c_parser.CParser()
    return parser.parse(FAKE_PREAMBLE + "\n" + cleaned)


@dataclass(frozen=True)
class Site:
    kind: str
    line: int
    old: str
    new: str


class SiteCollector(c_ast.NodeVisitor):
    def __init__(self) -> None:
        self.sites: List[Site] = []

    def _line(self, node: c_ast.Node) -> Optional[int]:
        coord = getattr(node, "coord", None)
        if coord is None or coord.line is None:
            return None
        original = coord.line - PREAMBLE_LINES
        if original < 1:
            return None
        return original

    def visit_BinaryOp(self, node: c_ast.BinaryOp) -> None:
        line = self._line(node)
        if line is None:
            self.generic_visit(node)
            return
        if node.op in BOUNDARY:
            self.sites.append(Site("boundary", line, node.op, BOUNDARY[node.op]))
        elif node.op in COMPARISON:
            self.sites.append(Site("comparison", line, node.op, COMPARISON[node.op]))
        elif node.op in {"+", "-"}:
            right = node.right
            if isinstance(right, c_ast.Constant) and right.type == "int" and right.value in {"1", "0"}:
                flipped = "0" if right.value == "1" else "1"
                self.sites.append(Site("off_by_one", line, right.value, flipped))
        self.generic_visit(node)

    def visit_Constant(self, node: c_ast.Constant) -> None:
        line = self._line(node)
        if line is None or node.type != "int":
            return
        if node.value.isdigit() and int(node.value) >= 1:
            self.sites.append(Site("off_by_one", line, node.value, str(int(node.value) + 1)))


_TOKEN_BOUNDARY = re.compile(r"(<=|>=|(?<![-<])<(?!=)|(?<![->])>(?!=))")
_TOKEN_COMPARE = re.compile(r"(==|!=)")
_TOKEN_OFF_BY_ONE = re.compile(r"(?:\+\s*1|\-\s*1)")


def collect_token_sites(source: str) -> List[Site]:
    """Same operator set as the AST walker, used when pycparser cannot parse."""
    sites: List[Site] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        for match in _TOKEN_BOUNDARY.finditer(line):
            old = match.group(1)
            if old in BOUNDARY:
                sites.append(Site("boundary", lineno, old, BOUNDARY[old]))
        for match in _TOKEN_COMPARE.finditer(line):
            old = match.group(1)
            if old in COMPARISON:
                sites.append(Site("comparison", lineno, old, COMPARISON[old]))
        if _TOKEN_OFF_BY_ONE.search(line) and "1" in line:
            sites.append(Site("off_by_one", lineno, "1", "0"))
    return sites


PROPERTY_MARKERS = (
    "__VERIFIER_assert",
    "__VERIFIER_error",
    "reach_error",
    "ERROR:",
)


def _dedupe(sites: Iterable[Site]) -> List[Site]:
    seen = set()
    unique: List[Site] = []
    for site in sites:
        key = (site.kind, site.line, site.old, site.new)
        if key in seen:
            continue
        seen.add(key)
        unique.append(site)
    return unique


def _implementation_sites(source: str, sites: Sequence[Site]) -> List[Site]:
    lines = source.splitlines()
    kept: List[Site] = []
    for site in sites:
        if site.line > len(lines):
            continue
        line = lines[site.line - 1]
        if any(marker in line for marker in PROPERTY_MARKERS):
            continue
        kept.append(site)
    return kept


def collect_sites(source: str) -> List[Site]:
    sites, _engine = collect_sites_with_engine(source)
    return sites


def collect_sites_with_engine(source: str) -> Tuple[List[Site], str]:
    try:
        ast = parse_c(source)
        collector = SiteCollector()
        collector.visit(ast)
        raw = collector.sites
        engine = "pycparser"
    except Exception:  # noqa: BLE001 — SV-COMP files often need the token fallback
        raw = collect_token_sites(source)
        engine = "token-fallback"
    sites = _implementation_sites(source, _dedupe(raw))
    if not sites and engine == "pycparser":
        sites = _implementation_sites(source, _dedupe(collect_token_sites(source)))
        if sites:
            engine = "token-fallback"
    return sites, engine


def apply_site(source: str, site: Site) -> str:
    lines = source.splitlines(keepends=True)
    if site.line > len(lines):
        raise ValueError(f"line {site.line} out of range")
    line = lines[site.line - 1]
    if site.old not in line:
        raise ValueError(f"{site.old!r} not on line {site.line}: {line!r}")
    lines[site.line - 1] = line.replace(site.old, site.new, 1)
    return "".join(lines)


def seed_one_mutant(
    source: str,
    rng: random.Random,
    prefer: Sequence[str] = ("boundary", "comparison", "off_by_one"),
) -> Tuple[str, Site, str]:
    sites, engine = collect_sites_with_engine(source)
    if not sites:
        raise ValueError("no mutation sites")
    for kind in prefer:
        pool = [s for s in sites if s.kind == kind]
        if pool:
            site = rng.choice(pool)
            return apply_site(source, site), site, engine
    site = rng.choice(sites)
    return apply_site(source, site), site, engine


def resolve_c_source(repo_root: Path, task: Dict[str, Any]) -> Path:
    yml = repo_root / task["task_yaml"]
    named = yml.parent / task["source_file"]
    if named.suffix == ".c" and named.is_file():
        return named
    sibling = named.with_suffix(".c")
    if sibling.is_file():
        return sibling
    if named.is_file():
        return named
    raise FileNotFoundError(named)


def seed_c_tasks(
    repo_root: Path,
    tasks: Iterable[Dict[str, Any]],
    out_dir: Path,
    seed: int = SEED,
    max_mutants: int = 80,
) -> Dict[str, Any]:
    rng = random.Random(seed)
    if out_dir.exists():
        for old in out_dir.glob("*.c"):
            old.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    correct = [t for t in tasks if t.get("expected") is True]
    records: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    seen_sources = set()

    for task in correct:
        if len(records) >= max_mutants:
            break
        try:
            src_path = resolve_c_source(repo_root, task)
        except FileNotFoundError as exc:
            skipped.append({"task": task["task_yaml"], "reason": str(exc)})
            continue
        if src_path in seen_sources:
            skipped.append({"task": task["task_yaml"], "reason": "duplicate source"})
            continue
        if src_path.stat().st_size > MAX_SOURCE_BYTES:
            skipped.append({"task": task["task_yaml"], "reason": "source too large"})
            continue
        seen_sources.add(src_path)
        source = src_path.read_text(encoding="utf-8", errors="replace")
        try:
            mutated, site, engine = seed_one_mutant(source, rng)
        except (ValueError, Exception) as exc:  # noqa: BLE001 — parse failures are expected
            skipped.append({"task": task["task_yaml"], "reason": str(exc).splitlines()[0][:200]})
            continue
        rel = src_path.relative_to(repo_root).as_posix().replace("/", "__")
        dest_name = f"{rel}__{site.kind}_{site.line}.c"
        dest = out_dir / dest_name
        dest.write_text(mutated, encoding="utf-8")
        records.append(
            {
                "file": dest_name,
                "task_yaml": task["task_yaml"],
                "source_file": str(src_path.relative_to(repo_root)),
                "original_expected": True,
                "operator": site.kind,
                "line": site.line,
                "old": site.old,
                "new": site.new,
                "engine": engine,
            }
        )

    manifest = {
        "seed": seed,
        "categories": list(DEFAULT_CATEGORIES),
        "n_correct_tasks": len(correct),
        "n_mutants": len(records),
        "n_skipped": len(skipped),
        "mutants": records,
        "skipped": skipped,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_spot_check(
    manifest: Dict[str, Any],
    out_path: Path,
    n: int = 30,
    seed: int = SEED,
) -> Dict[str, Any]:
    """Pick a reproducible sample of mutants for hand review."""
    mutants = list(manifest["mutants"])
    rng = random.Random(seed)
    if len(mutants) <= n:
        sample = mutants
    else:
        sample = rng.sample(mutants, n)
    payload = {
        "seed": seed,
        "n_requested": n,
        "n_reviewed": len(sample),
        "instruction": (
            "Each row is one seeded C mutant. plausible=yes means the edit is a "
            "recognizable boundary, comparison, or off-by-one bug, not junk."
        ),
        "reviews": [
            {
                "file": item["file"],
                "task_yaml": item["task_yaml"],
                "operator": item["operator"],
                "line": item["line"],
                "old": item["old"],
                "new": item["new"],
                "plausible": None,
                "note": "",
            }
            for item in sample
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
