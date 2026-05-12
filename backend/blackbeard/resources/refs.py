"""Reference parsing, resolution, and cycle detection.

Refs follow the format: "ref:<kind-plural>/<name>" e.g. "ref:agents/researcher"
The kind plural is mapped back to the ResourceKind enum.
"""

import re
from collections import defaultdict

from blackbeard.kinds import ResourceKind
from blackbeard.kinds import PLURAL_TO_KIND_ENUM, KIND_TO_PLURAL, PLURAL_TO_KIND

REF_PATTERN = re.compile(r"^ref:([a-z\-]+)/([a-z0-9][a-z0-9\-]*)$")


class RefParseError(Exception):
    """Raised when a ref string cannot be parsed."""


class CycleError(Exception):
    """Raised when a dependency cycle is detected."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        path = " -> ".join(cycle)
        super().__init__(f"Dependency cycle detected: {path}")


class RefInfo:
    """Parsed reference information."""

    def __init__(self, kind: ResourceKind, name: str, raw: str, field: str):
        self.kind = kind
        self.name = name
        self.raw = raw
        self.field = field

    def __repr__(self) -> str:
        return f"RefInfo({self.kind.value}/{self.name} from {self.field})"


def parse_ref(value: str, field: str = "") -> RefInfo | None:
    """Parse a ref string like 'ref:agents/researcher'.

    Returns None if the value is not a ref (just a plain string).
    Raises RefParseError if it looks like a ref but is malformed.
    """
    if not isinstance(value, str) or not value.startswith("ref:"):
        return None

    match = REF_PATTERN.match(value)
    if not match:
        raise RefParseError(f"Malformed ref '{value}' in field '{field}'. Expected format: ref:<kind>/<name>")

    plural, name = match.groups()
    kind = PLURAL_TO_KIND_ENUM.get(plural)
    if kind is None:
        valid = ", ".join(sorted(PLURAL_TO_KIND_ENUM.keys()))
        raise RefParseError(f"Unknown resource kind '{plural}' in ref '{value}'. Valid kinds: {valid}")

    return RefInfo(kind=kind, name=name, raw=value, field=field)


def extract_refs(spec: dict, prefix: str = "spec") -> list[RefInfo]:
    """Recursively extract all refs from a spec dict."""
    refs: list[RefInfo] = []

    def _walk(obj: object, path: str) -> None:
        if isinstance(obj, str):
            ref = parse_ref(obj, field=path)
            if ref is not None:
                refs.append(ref)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, f"{path}[{i}]")
        elif isinstance(obj, dict):
            for key, val in obj.items():
                _walk(val, f"{path}.{key}")

    _walk(spec, prefix)
    return refs


def detect_cycles(
    adjacency: dict[str, list[str]],
) -> list[list[str]]:
    """Detect cycles in a directed graph using DFS.

    adjacency: maps "Kind/name" -> list of "Kind/name" dependencies.
    Returns list of cycles found (empty list if no cycles).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)
    parent: dict[str, str | None] = {}
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        for neighbor in adjacency.get(node, []):
            if color[neighbor] == GRAY:
                # Found a cycle — reconstruct it
                cycle = [neighbor, node]
                current = node
                max_depth = len(adjacency) + 1
                depth = 0
                while current != neighbor and depth < max_depth:
                    current = parent.get(current, "")
                    depth += 1
                    if current and current != neighbor:
                        cycle.append(current)
                cycle.reverse()
                cycle.append(neighbor)  # close the cycle
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                parent[neighbor] = node
                dfs(neighbor)
        color[node] = BLACK

    for node in adjacency:
        if color[node] == WHITE:
            parent[node] = None
            dfs(node)

    return cycles


def build_adjacency(resources: list[dict]) -> dict[str, list[str]]:
    """Build adjacency list from a list of resource dicts (parsed YAML).

    Each resource dict has 'kind', 'metadata.name', and 'spec'.
    Returns adjacency: "Kind/name" -> ["Kind/dep_name", ...]
    """
    adjacency: dict[str, list[str]] = {}

    for res in resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        key = f"{kind}/{name}"
        refs = extract_refs(res.get("spec", {}))
        adjacency[key] = [f"{r.kind.value}/{r.name}" for r in refs]

    return adjacency
