"""Lightweight dataclasses for GitHub API responses we actually use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Repository:
    owner: str
    name: str
    default_branch: str
    full_name: str
    private: bool
    html_url: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Repository:
        return cls(
            owner=data["owner"]["login"],
            name=data["name"],
            default_branch=data.get("default_branch") or "main",
            full_name=data["full_name"],
            private=bool(data.get("private")),
            html_url=data["html_url"],
        )


@dataclass(frozen=True)
class BranchRef:
    name: str
    sha: str


@dataclass(frozen=True)
class CommitInput:
    """A single file write to be committed."""

    path: str
    content: str
    encoding: str = "utf-8"


@dataclass(frozen=True)
class PullRequest:
    number: int
    html_url: str
    head_ref: str
    base_ref: str
    title: str
    body: str
    state: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PullRequest:
        return cls(
            number=data["number"],
            html_url=data["html_url"],
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            title=data["title"],
            body=data.get("body") or "",
            state=data["state"],
        )
