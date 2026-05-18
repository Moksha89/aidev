"""GitHub REST client used by the agent-runner and the FastAPI backend.

Designed for the small slice of GitHub operations the platform performs:
branch creation, file commits, PR creation, PR comments.

Auth modes:
- PAT: pass `token=...`
- GitHub App: pass `app_id`, `private_key`, `installation_id`. The client
  mints an installation token via JWT and refreshes it on expiry.

If `httpx` is not installed, the client raises a clear ImportError at
instantiation rather than at first call.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from aidev_github.models import BranchRef, CommitInput, PullRequest, Repository


class GitHubError(RuntimeError):
    """Raised for non-2xx responses from the GitHub API."""

    def __init__(self, status: int, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status
        self.payload = payload or {}


_GITHUB_API = "https://api.github.com"


@dataclass
class _InstallationToken:
    token: str
    expires_at: float

    def is_fresh(self, skew_seconds: int = 60) -> bool:
        return self.token != "" and self.expires_at - skew_seconds > time.time()


class GitHubClient:
    """Minimal async-friendly GitHub REST client.

    The client is intentionally synchronous to keep it usable from both
    Celery tasks (sync) and the FastAPI request path (where we wrap calls
    in `run_in_executor`). For high throughput, instantiate one client
    per worker process and reuse it.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        app_id: int | None = None,
        private_key: str | None = None,
        installation_id: int | None = None,
        base_url: str = _GITHUB_API,
        user_agent: str = "aidev-platform/0.1",
    ) -> None:
        if not token and not (app_id and private_key and installation_id):
            raise ValueError(
                "GitHubClient requires either `token` or all of "
                "(`app_id`, `private_key`, `installation_id`)."
            )
        try:
            import httpx  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "GitHubClient requires the 'httpx' package. "
                "Run `poetry add httpx` in the consuming service."
            ) from exc

        self._token = token
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._installation_token: _InstallationToken | None = None

    # ------------------------------------------------------------ helpers

    def _auth_header(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {"Authorization": f"Bearer {self._installation_access_token()}"}

    def _installation_access_token(self) -> str:
        """Mint or reuse a GitHub App installation token."""
        if self._installation_token and self._installation_token.is_fresh():
            return self._installation_token.token

        import httpx

        try:
            import jwt  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "GitHub App auth requires the 'PyJWT[crypto]' package."
            ) from exc

        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": self._app_id}
        assertion = jwt.encode(payload, self._private_key, algorithm="RS256")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {assertion}",
            "User-Agent": self._user_agent,
        }
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{self._base_url}/app/installations/"
                f"{self._installation_id}/access_tokens",
                headers=headers,
            )
            if resp.status_code >= 300:
                raise GitHubError(resp.status_code, resp.text)
            body = resp.json()
        # `expires_at` is ISO 8601; convert with strptime to avoid pulling dateutil.
        from datetime import datetime

        expires_at = datetime.strptime(
            body["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC).timestamp()
        self._installation_token = _InstallationToken(
            token=body["token"], expires_at=expires_at
        )
        return self._installation_token.token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        import httpx

        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": self._user_agent,
            **self._auth_header(),
        }
        with httpx.Client(timeout=30) as client:
            resp = client.request(
                method, url, headers=headers, json=json, params=params
            )
            if resp.status_code >= 300:
                payload: dict[str, Any] = {}
                try:
                    payload = resp.json()
                except Exception:
                    payload = {}
                raise GitHubError(
                    resp.status_code,
                    payload.get("message") or resp.text or "request failed",
                    payload,
                )
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

    # ------------------------------------------------------------ public

    def get_repository(self, owner: str, repo: str) -> Repository:
        data = self._request("GET", f"/repos/{owner}/{repo}")
        return Repository.from_api(data)

    def get_branch(self, owner: str, repo: str, branch: str) -> BranchRef:
        data = self._request("GET", f"/repos/{owner}/{repo}/branches/{branch}")
        return BranchRef(name=data["name"], sha=data["commit"]["sha"])

    def create_branch(
        self, owner: str, repo: str, *, new_branch: str, from_sha: str
    ) -> BranchRef:
        """Create `refs/heads/<new_branch>` pointing at `from_sha`."""
        data = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{new_branch}", "sha": from_sha},
        )
        return BranchRef(name=new_branch, sha=data["object"]["sha"])

    def put_file(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        path: str,
        message: str,
        content: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a single file via the Contents API.

        For batched, atomic commits use `create_commit` instead (Trees API).
        """
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        return self._request(
            "PUT", f"/repos/{owner}/{repo}/contents/{path}", json=body
        )

    def create_commit(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        parent_sha: str,
        message: str,
        files: list[CommitInput],
    ) -> str:
        """Create one commit on `branch` containing all `files`.

        Returns the new commit SHA. Uses the Trees + Commits API so all
        files land in a single commit even if there are many.
        """
        # 1. Create blobs for each file.
        tree_entries: list[dict[str, Any]] = []
        for f in files:
            blob = self._request(
                "POST",
                f"/repos/{owner}/{repo}/git/blobs",
                json={
                    "content": base64.b64encode(
                        f.content.encode(f.encoding)
                    ).decode("ascii"),
                    "encoding": "base64",
                },
            )
            tree_entries.append(
                {
                    "path": f.path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob["sha"],
                }
            )

        # 2. Create tree based on parent commit's tree.
        parent = self._request(
            "GET", f"/repos/{owner}/{repo}/git/commits/{parent_sha}"
        )
        tree = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/trees",
            json={
                "base_tree": parent["tree"]["sha"],
                "tree": tree_entries,
            },
        )

        # 3. Create the commit.
        commit = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            json={
                "message": message,
                "tree": tree["sha"],
                "parents": [parent_sha],
            },
        )

        # 4. Move the branch ref.
        self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
            json={"sha": commit["sha"], "force": False},
        )

        return commit["sha"]

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = False,
    ) -> PullRequest:
        data = self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": draft,
            },
        )
        return PullRequest.from_api(data)

    def add_pr_comment(
        self, owner: str, repo: str, *, pr_number: int, body: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
