#!/usr/bin/env python3
"""Fold messy genre tags into a curated whitelist by walking a genre DAG."""
import argparse
import json
import re
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAG_PATH = HERE / "dag.json"
CONFIG_PATH = HERE / "config.json"

# True: stop climbing at the first allowed genre on each path (most specific only).
# False: collect every allowed ancestor.
NEAREST_ONLY = True


def norm(s):
    return " ".join(s.lower().split())


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"missing file: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"bad JSON in {path}: {e}")


def load_config(path):
    cfg = load_json(path)
    allowed, stop, blocked, remap = {}, set(), {}, {}

    for name, props in cfg.get("genres", {}).items():
        n = norm(name)
        if props.get("keep", True):
            allowed[n] = name  # lowercase -> display casing
        if props.get("stop", False):
            stop.add(n)

    for tag, rule in cfg.get("tags", {}).items():
        t = norm(tag)
        if "block" in rule:
            blocked[t] = {norm(x) for x in rule["block"]}
        if "map" in rule:
            remap[t] = [norm(x) for x in rule["map"]]

    return allowed, stop, blocked, remap


def load_parents(path):
    """Build child -> parents from both `parents` and `children` fields,
    so an edge declared on only one side still counts."""
    raw = load_json(path)
    parents = {}
    for name, node in raw["nodes"].items():
        n = norm(name)
        parents.setdefault(n, set()).update(norm(p) for p in node.get("parents", []))
        for c in node.get("children", []):
            parents.setdefault(norm(c), set()).add(n)
    for ps in list(parents.values()):
        for p in ps:
            parents.setdefault(p, set())
    return parents


def compute_depths(parents):
    """Depth = longest path to a parentless node. Cycle-safe."""
    depth, active = {}, set()

    def d(n):
        if n in depth:
            return depth[n]
        active.add(n)
        best = -1
        for p in parents[n]:
            if p not in active:
                best = max(best, d(p))
        active.discard(n)
        depth[n] = best + 1
        return depth[n]

    for n in parents:
        d(n)
    return depth


ALLOWED_LC, STOP_LC, BLOCKED_LC, MAP_LC = load_config(CONFIG_PATH)
PARENTS = load_parents(DAG_PATH)
DEPTH = compute_depths(PARENTS)
_anc_cache = {}


def ancestors(n):
    if n not in _anc_cache:
        seen, q = set(), deque(PARENTS.get(n, ()))
        while q:
            cur = q.popleft()
            if cur not in seen:
                seen.add(cur)
                q.extend(PARENTS.get(cur, ()))
        _anc_cache[n] = seen
    return _anc_cache[n]


def resolve_tag(tag, nearest_only=NEAREST_ONLY):
    origin = norm(tag)
    blocked = BLOCKED_LC.get(origin, set())
    queue = deque(MAP_LC.get(origin, [origin]))
    seen, found = set(), set()

    while queue:
        cur = queue.popleft()
        if cur in seen:
            continue
        seen.add(cur)

        is_allowed = cur in ALLOWED_LC
        if is_allowed:
            found.add(cur)
        if cur in STOP_LC or (nearest_only and is_allowed):
            continue
        queue.extend(p for p in PARENTS.get(cur, ()) if p not in blocked)

    if nearest_only:
        found = {f for f in found if not any(f in ancestors(g) for g in found if g != f)}
    return found


def absorb(found):
    """Drop any result that descends from a stop-genre result."""
    protected = {f for f in found if f in STOP_LC}
    return {f for f in found if not any(p != f and p in ancestors(f) for p in protected)}


def resolve_list(text, nearest_only=NEAREST_ONLY):
    tags = [t.strip() for t in re.split(r"[;,]", text) if t.strip()]
    found, explicit, unresolved = set(), set(), []

    for t in tags:
        r = resolve_tag(t, nearest_only)
        if not r:
            unresolved.append(t)
        found |= r
        if norm(t) in ALLOWED_LC:
            explicit.add(norm(t))

    found = absorb(found) | explicit
    out = sorted((ALLOWED_LC[f] for f in found), key=lambda g: (-DEPTH.get(norm(g), 0), g))
    return out, unresolved


def main():
    ap = argparse.ArgumentParser(description="Fold genre tags into the whitelist.")
    ap.add_argument("tags", nargs="*", help='e.g. "post-punk, chillwave; glitch" (else read stdin, one set per line)')
    ap.add_argument("--all", action="store_true", help="collect every allowed ancestor, not just the nearest")
    ap.add_argument("--json", action="store_true", help="output JSON")
    args = ap.parse_args()

    lines = ["; ".join(args.tags)] if args.tags else [l for l in sys.stdin.read().splitlines() if l.strip()]
    for line in lines:
        out, unresolved = resolve_list(line, nearest_only=not args.all)
        print(json.dumps(out) if args.json else "; ".join(out))
        if unresolved:
            print("unresolved: " + "; ".join(unresolved), file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)