"""Documented one-sentence deletions that produce ambiguous requirements."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from semanticdrift.protocols import PROTOCOLS_DIR


def collapse(text: str) -> str:
    return " ".join(text.split())


def load_edits(base: Path | None = None) -> Dict[str, Any]:
    path = (base or PROTOCOLS_DIR) / "requirement_edits.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def deleted_sentence(protocol: str, base: Path | None = None) -> str:
    edits = load_edits(base)
    raw = edits.get("edits", {}).get(protocol, {}).get("deleted", "")
    return collapse(raw)
