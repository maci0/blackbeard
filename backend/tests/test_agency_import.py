"""Tests for Agency Agents markdown parser."""

from __future__ import annotations

from blackbeard.engine.agency_import import (
    parse_agency_agent_markdown,
    parse_frontmatter,
)

SAMPLE_AGENT = """---
name: Backend Architect
description: Senior backend architect specializing in scalable system design
color: blue
emoji: 🏗️
vibe: Designs the systems that hold everything up
---

# Backend Architect Agent Personality

You are **Backend Architect**.

## 🧠 Your Identity & Memory
- **Role**: System architecture and server-side development specialist
- **Personality**: Strategic, security-focused, scalability-minded
- **Experience**: You've seen systems succeed through proper architecture

## 🎯 Your Core Mission

### Design Scalable System Architecture
- Create microservices architectures that scale horizontally
- Design database schemas optimized for performance

### Ensure System Reliability
- Implement proper error handling and circuit breakers

## 🚨 Critical Rules You Must Follow

### Security-First Architecture
- Implement defense in depth strategies
"""

MINIMAL_AGENT = """---
name: Simple Agent
description: A simple test agent
---

# Simple Agent

## Core Mission
- Do simple things well
"""

NO_FRONTMATTER = """# Random Agent

## Your Identity
- **Role**: Random helper

## Core Mission
- Help with random tasks
"""


class TestParseFrontmatter:
    def test_extracts_name(self):
        result = parse_frontmatter(SAMPLE_AGENT)
        assert result["name"] == "Backend Architect"

    def test_extracts_description(self):
        result = parse_frontmatter(SAMPLE_AGENT)
        assert "scalable system design" in result["description"]

    def test_extracts_vibe(self):
        result = parse_frontmatter(SAMPLE_AGENT)
        assert "hold everything up" in result["vibe"]

    def test_empty_content(self):
        result = parse_frontmatter("")
        assert result == {}

    def test_no_frontmatter(self):
        result = parse_frontmatter("# Just a heading\nSome text")
        assert result == {}


class TestParseAgencyAgent:
    def test_full_agent(self):
        result = parse_agency_agent_markdown(
            SAMPLE_AGENT, "engineering/engineering-backend-architect.md"
        )
        assert result is not None
        assert result["name"] == "backend-architect"
        assert "backend" in result["role"].lower() or "architect" in result["role"].lower()
        assert len(result["goal"]) > 10
        assert len(result["backstory"]) > 10
        assert result["source"] == "agency-agents"
        assert result["source_division"] == "engineering"
        assert result["original_name"] == "Backend Architect"

    def test_minimal_agent(self):
        result = parse_agency_agent_markdown(MINIMAL_AGENT, "test/simple.md")
        assert result is not None
        assert result["name"] == "simple-agent"

    def test_no_frontmatter_extracts_from_heading(self):
        result = parse_agency_agent_markdown(NO_FRONTMATTER, "test/random.md")
        assert result is not None
        assert "random" in result["name"].lower()

    def test_empty_content_returns_none(self):
        result = parse_agency_agent_markdown("", "empty.md")
        assert result is None

    def test_slug_is_lowercase_hyphenated(self):
        result = parse_agency_agent_markdown(SAMPLE_AGENT, "test.md")
        assert result is not None
        assert result["name"] == "backend-architect"
        assert " " not in result["name"]

    def test_division_from_path(self):
        result = parse_agency_agent_markdown(SAMPLE_AGENT, "marketing/marketing-seo-specialist.md")
        assert result is not None
        assert result["source_division"] == "marketing"

    def test_goal_is_not_empty(self):
        result = parse_agency_agent_markdown(SAMPLE_AGENT, "test.md")
        assert result is not None
        assert len(result["goal"]) > 0

    def test_backstory_is_not_empty(self):
        result = parse_agency_agent_markdown(SAMPLE_AGENT, "test.md")
        assert result is not None
        assert len(result["backstory"]) > 0

    def test_goal_max_length(self):
        long_mission = "---\nname: Test\ndescription: Test\n---\n\n## Core Mission\n" + (
            "- " + "x" * 600 + "\n"
        )
        result = parse_agency_agent_markdown(long_mission, "test.md")
        assert result is not None
        assert len(result["goal"]) <= 500

    def test_backstory_max_length(self):
        long_identity = (
            "---\nname: Test\ndescription: Test\n---\n\n## Your Identity\n"
            + ("- " + "y" * 1200 + "\n")
            + "\n## Core Mission\n- Do stuff\n"
        )
        result = parse_agency_agent_markdown(long_identity, "test.md")
        assert result is not None
        assert len(result["backstory"]) <= 1000
