"""Parse `.ai-rules/*.md` files into structured `Rule` objects.

Each rule file has YAML frontmatter delimited by `---` lines followed by
markdown. We pick the YAML for metadata and extract any fenced
```glob``` blocks under headings called "Allowed paths" or
"Forbidden paths".

We intentionally avoid a YAML dependency for the path globs themselves —
they live in fenced code blocks so they read naturally for humans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Rule:
    """A single rule parsed from `.ai-rules/<id>.md`."""

    id: str
    title: str
    applies_to: str
    priority: int
    allowed_paths: tuple[str, ...] = field(default_factory=tuple)
    forbidden_paths: tuple[str, ...] = field(default_factory=tuple)
    enforced_by: tuple[str, ...] = field(default_factory=tuple)
    source_path: str | None = None

    @property
    def applies_to_all_phases(self) -> bool:
        return self.applies_to == "all_phases"

    @property
    def target_phase(self) -> str | None:
        """Return the phase name this rule applies to, or None for global rules."""
        if self.applies_to_all_phases:
            return None
        prefix = "phases."
        if self.applies_to.startswith(prefix):
            return self.applies_to[len(prefix) :]
        return None


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<yaml>.*?)\n---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)
_ALLOWED_HEADING_RE = re.compile(
    r"^##+\s*Allowed paths.*$",
    re.IGNORECASE | re.MULTILINE,
)
_FORBIDDEN_HEADING_RE = re.compile(
    r"^##+\s*Forbidden paths.*$",
    re.IGNORECASE | re.MULTILINE,
)
_NEXT_HEADING_RE = re.compile(r"^##+\s", re.MULTILINE)
_GLOB_FENCE_RE = re.compile(
    r"```(?:glob|gitignore)?\s*\n(?P<inner>.*?)\n```",
    re.DOTALL,
)


def _extract_globs_after(body: str, heading_re: re.Pattern[str]) -> tuple[str, ...]:
    """Find the first fenced glob block following the given heading.

    Stops scanning at the next ``##`` heading so heading order in the
    markdown doesn't accidentally pull in the wrong block.
    """
    heading_match = heading_re.search(body)
    if not heading_match:
        return ()
    start = heading_match.end()
    next_heading = _NEXT_HEADING_RE.search(body, pos=start)
    end = next_heading.start() if next_heading else len(body)
    region = body[start:end]
    fence = _GLOB_FENCE_RE.search(region)
    if not fence:
        return ()
    lines = [line.strip() for line in fence.group("inner").splitlines()]
    return tuple(line for line in lines if line and not line.startswith("#"))


def _coerce_priority(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 50


def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def parse_rule(content: str, source_path: str | None = None) -> Rule:
    """Parse a single rule markdown document."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError(
            f"Rule {source_path or '<inline>'} has no YAML frontmatter "
            "delimited by --- lines."
        )

    metadata: dict[str, Any] = yaml.safe_load(match.group("yaml")) or {}
    body = match.group("body")

    rule_id = str(metadata.get("id") or "").strip()
    if not rule_id:
        raise ValueError(f"Rule {source_path or '<inline>'} is missing 'id'.")

    return Rule(
        id=rule_id,
        title=str(metadata.get("title") or rule_id),
        applies_to=str(metadata.get("applies_to") or "all_phases"),
        priority=_coerce_priority(metadata.get("priority")),
        allowed_paths=_extract_globs_after(body, _ALLOWED_HEADING_RE),
        forbidden_paths=_extract_globs_after(body, _FORBIDDEN_HEADING_RE),
        enforced_by=_coerce_str_tuple(metadata.get("enforced_by")),
        source_path=source_path,
    )


def parse_rules_directory(directory: str | Path) -> tuple[Rule, ...]:
    """Parse every `*.md` file under the given directory.

    Returns rules sorted by descending priority then by id, so
    higher-priority rules are evaluated first.
    """
    base = Path(directory)
    if not base.exists():
        raise FileNotFoundError(f"Rules directory not found: {base}")

    rules: list[Rule] = []
    for path in sorted(base.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        rules.append(parse_rule(text, source_path=str(path)))

    rules.sort(key=lambda r: (-r.priority, r.id))
    return tuple(rules)
