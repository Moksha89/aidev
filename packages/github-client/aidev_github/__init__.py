"""Thin GitHub REST client for the AI Developer platform."""

from aidev_github.client import GitHubClient, GitHubError
from aidev_github.models import (
    BranchRef,
    CommitInput,
    PullRequest,
    Repository,
)

__all__ = [
    "BranchRef",
    "CommitInput",
    "GitHubClient",
    "GitHubError",
    "PullRequest",
    "Repository",
]
__version__ = "0.1.0"
