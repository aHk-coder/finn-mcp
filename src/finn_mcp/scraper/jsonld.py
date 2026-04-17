from __future__ import annotations

import json
import re
from typing import Any

from selectolax.parser import HTMLParser

_LD_JSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)


def _unwrap(obj: Any) -> list[dict[str, Any]]:
    """Normalize a parsed JSON-LD block into a list of dicts.

    finn.no's jobs pages wrap each block like {"script:ld+json": {...}}.
    @graph is also flattened here.
    """
    if obj is None:
        return []
    if isinstance(obj, list):
        out: list[dict[str, Any]] = []
        for item in obj:
            out.extend(_unwrap(item))
        return out
    if not isinstance(obj, dict):
        return []
    if "script:ld+json" in obj and len(obj) == 1:
        return _unwrap(obj["script:ld+json"])
    if "@graph" in obj and isinstance(obj["@graph"], list):
        return _unwrap(obj["@graph"])
    return [obj]


def extract_jsonld(html: str) -> list[dict[str, Any]]:
    """Return every schema.org dict embedded in <script type="application/ld+json">.

    Also works via selectolax if ``html`` is already a parsed tree's HTML.
    """
    results: list[dict[str, Any]] = []
    for m in _LD_JSON_RE.finditer(html):
        body = m.group(1).strip()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        results.extend(_unwrap(parsed))
    return results


def find_by_type(blocks: list[dict[str, Any]], *types: str) -> dict[str, Any] | None:
    wanted = set(types)
    for b in blocks:
        t = b.get("@type")
        if isinstance(t, list):
            if wanted.intersection(t):
                return b
        elif t in wanted:
            return b
    return None


def extract_jsonld_from_tree(tree: HTMLParser) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for node in tree.css('script[type="application/ld+json"]'):
        body = (node.text(deep=True) or "").strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        results.extend(_unwrap(parsed))
    return results
