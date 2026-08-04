"""Import agent personas from Agency Agents markdown library.

Parses the structured markdown format used by
https://github.com/msitarzewski/agency-agents and converts
each persona into a Blackbeard Agent resource spec.
"""

from __future__ import annotations

import logging
import re
from typing import Any

__all__ = [
    "parse_agency_agent_markdown",
    "parse_frontmatter",
]

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)
_STRIP_AGENT_RE = re.compile(r"\s*(Agent|Personality).*$", re.IGNORECASE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SECTION_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def parse_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML frontmatter from markdown content."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _extract_section(content: str, heading_pattern: str) -> str:
    """Extract text under a heading matching the pattern, up to the next heading."""
    pat = _SECTION_PATTERN_CACHE.get(heading_pattern)
    if pat is None:
        if len(_SECTION_PATTERN_CACHE) >= 64:
            _SECTION_PATTERN_CACHE.clear()
        pat = re.compile(heading_pattern, re.IGNORECASE)
        _SECTION_PATTERN_CACHE[heading_pattern] = pat
    lines = content.split("\n")
    capturing = False
    result: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if capturing:
                break
            heading_text = line.lstrip("#").strip()
            if pat.search(heading_text):
                capturing = True
                continue
        elif capturing:
            result.append(line)
    return "\n".join(result).strip()


def _extract_role(content: str, frontmatter: dict[str, str]) -> str:
    """Extract role from Identity section or frontmatter."""
    identity = _extract_section(content, "Identity|Your Identity")
    if identity:
        for line in identity.splitlines():
            if "Role" in line and ":" in line:
                return line.split(":", 1)[1].strip().strip("*")
    return frontmatter.get("name", "Agent")


def _extract_goal(content: str, frontmatter: dict[str, str]) -> str:
    """Extract goal from Core Mission section or description."""
    mission = _extract_section(content, "Core Mission|Mission")
    if mission:
        lines = [
            line.strip("- ").strip()
            for line in mission.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if lines:
            return lines[0][:500]
    return frontmatter.get("description", "")[:500]


def _extract_backstory(content: str, frontmatter: dict[str, str]) -> str:
    """Extract backstory from Identity + personality sections."""
    identity = _extract_section(content, "Identity|Your Identity")
    if identity:
        parts = []
        for line in identity.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                clean = line.lstrip("- ").strip("*").strip()
                if clean and len(clean) > 5:
                    parts.append(clean)
        if parts:
            return " ".join(parts[:5])[:1000]

    vibe = frontmatter.get("vibe", "")
    desc = frontmatter.get("description", "")
    if vibe:
        return f"{desc}. {vibe}"[:1000]
    return desc[:1000]


def parse_agency_agent_markdown(
    content: str,
    filename: str = "",
) -> dict[str, Any] | None:
    """Parse an Agency Agents markdown file into a Blackbeard Agent spec.

    Returns a dict with ``role``, ``goal``, ``backstory`` fields suitable
    for creating an Agent resource, or ``None`` if the content is not a
    valid agent persona file.
    """
    frontmatter = parse_frontmatter(content)
    if not frontmatter.get("name"):
        title_match = _HEADING_RE.search(content)
        if title_match:
            raw_title = title_match.group(1)
            frontmatter["name"] = _STRIP_AGENT_RE.sub("", raw_title).strip()
        elif filename:
            frontmatter["name"] = filename.replace(".md", "").replace("-", " ").title()
        else:
            return None

    role = _extract_role(content, frontmatter)
    goal = _extract_goal(content, frontmatter)
    backstory = _extract_backstory(content, frontmatter)

    if not role or not goal:
        return None

    name = frontmatter["name"]
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")

    return {
        "name": slug,
        "role": role,
        "goal": goal,
        "backstory": backstory,
        "source": "agency-agents",
        "source_division": _infer_division(filename),
        "original_name": name,
    }


def _infer_division(filename: str) -> str:
    """Infer the Agency Agents division from the file path."""
    parts = filename.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return parts[-2]
    return "unknown"
