import asyncio
import json
import os
import re
import subprocess
from urllib.parse import urlparse

from models import PRCheck, PRComment, PRContext, PRFileChange

MAX_DIFF_CHARS = 80_000

PR_URL_PATTERN = re.compile(
    r"https?://github\.com/[^/]+/[^/]+/pull/\d+",
    re.IGNORECASE,
)

REVIEW_THREADS_QUERY = (
    "query($owner: String!, $repo: String!, $number: Int!) {"
    " repository(owner: $owner, name: $repo) {"
    " pullRequest(number: $number) {"
    " reviewThreads(first: 100) {"
    " nodes { isResolved comments(first: 10) { nodes {"
    " author { login } body path line url"
    " } } } } } } }"
)


class GitHubAuthError(Exception):
    pass


class GitHubClient:
    def __init__(self) -> None:
        self._env = os.environ.copy()
        token = os.getenv("GITHUB_TOKEN")
        if token:
            self._env["GH_TOKEN"] = token

    async def fetch(self, pr_url: str) -> PRContext:
        self._validate_pr_url(pr_url)
        await self._ensure_authenticated()

        metadata, diff, checks, comments = await asyncio.gather(
            self._fetch_metadata(pr_url),
            self._fetch_diff(pr_url),
            self._fetch_checks(pr_url),
            self._fetch_unresolved_comments(pr_url),
        )

        diff, truncated, truncation_note = self._truncate_diff(diff)
        files = self._parse_files(metadata.get("files", []))

        return PRContext(
            url=pr_url,
            title=metadata.get("title", ""),
            body=metadata.get("body") or "",
            state=metadata.get("state", ""),
            head_ref=metadata.get("headRefName", ""),
            base_ref=metadata.get("baseRefName", ""),
            mergeable=metadata.get("mergeable"),
            additions=metadata.get("additions", 0),
            deletions=metadata.get("deletions", 0),
            files=files,
            diff=diff,
            checks=checks,
            comments=comments,
            truncated=truncated,
            truncation_note=truncation_note,
        )

    async def fetch_file_content(self, pr_url: str, file_path: str, ref: str) -> str | None:
        import base64
        from urllib.parse import quote

        owner, repo, _ = self._parse_pr_url(pr_url)
        encoded_path = quote(file_path, safe="/")
        try:
            result = await self._run_gh(
                [
                    "api",
                    f"/repos/{owner}/{repo}/contents/{encoded_path}?ref={ref}",
                    "--jq",
                    ".content",
                ]
            )
            if not result.strip():
                return None
            return base64.b64decode(result.strip()).decode("utf-8", errors="replace")
        except subprocess.CalledProcessError:
            return None

    async def post_comment(self, pr_url: str, body: str) -> None:
        self._validate_pr_url(pr_url)
        await self._ensure_authenticated()
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "comment",
            pr_url,
            "--body-file",
            "-",
            env=self._env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(body.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())

    def _validate_pr_url(self, pr_url: str) -> None:
        if not PR_URL_PATTERN.match(pr_url.strip()):
            raise ValueError(
                "Invalid PR URL. Expected format: https://github.com/owner/repo/pull/123"
            )

    async def _ensure_authenticated(self) -> None:
        try:
            await self._run_gh(["auth", "status"])
        except subprocess.CalledProcessError as exc:
            raise GitHubAuthError(
                "GitHub CLI is not authenticated. Run `gh auth login` and try again."
            ) from exc

    async def _fetch_metadata(self, pr_url: str) -> dict:
        result = await self._run_gh(
            [
                "pr",
                "view",
                pr_url,
                "--json",
                "title,body,state,headRefName,baseRefName,mergeable,additions,deletions,files,commits",
            ]
        )
        return json.loads(result)

    async def _fetch_diff(self, pr_url: str) -> str:
        return await self._run_gh(["pr", "diff", pr_url])

    async def _fetch_checks(self, pr_url: str) -> list[PRCheck]:
        try:
            result = await self._run_gh(
                ["pr", "checks", pr_url, "--json", "name,state,link,description"]
            )
            data = json.loads(result)
            if isinstance(data, list):
                return [PRCheck(**item) for item in data]
        except subprocess.CalledProcessError:
            pass
        return []

    async def _fetch_unresolved_comments(self, pr_url: str) -> list[PRComment]:
        owner, repo, number = self._parse_pr_url(pr_url)
        try:
            result = await self._run_gh(
                [
                    "api",
                    "graphql",
                    "-f",
                    f"query={REVIEW_THREADS_QUERY}",
                    "-f",
                    f"owner={owner}",
                    "-f",
                    f"repo={repo}",
                    "-F",
                    f"number={number}",
                ]
            )
            data = json.loads(result)
            threads = (
                data.get("data", {})
                .get("repository", {})
                .get("pullRequest", {})
                .get("reviewThreads", {})
                .get("nodes", [])
            )
            comments: list[PRComment] = []
            for thread in threads:
                if thread.get("isResolved"):
                    continue
                for node in thread.get("comments", {}).get("nodes", []):
                    comments.append(
                        PRComment(
                            author=node.get("author", {}).get("login", "unknown"),
                            body=node.get("body", ""),
                            path=node.get("path"),
                            line=node.get("line"),
                            url=node.get("url", ""),
                        )
                    )
            return comments
        except subprocess.CalledProcessError:
            return []

    async def _run_gh(self, args: list[str]) -> str:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            *args,
            env=self._env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, ["gh", *args], stdout, stderr)
        return stdout.decode("utf-8", errors="replace")

    def _parse_pr_url(self, pr_url: str) -> tuple[str, str, int]:
        parsed = urlparse(pr_url.strip())
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[2] != "pull":
            raise ValueError(f"Cannot parse PR URL: {pr_url}")
        owner, repo = parts[0], parts[1]
        number = int(parts[3])
        return owner, repo, number

    def _parse_files(self, raw_files: list) -> list[PRFileChange]:
        files = []
        for item in raw_files:
            if isinstance(item, str):
                files.append(PRFileChange(path=item))
            elif isinstance(item, dict):
                files.append(
                    PRFileChange(
                        path=item.get("path", ""),
                        additions=item.get("additions", 0),
                        deletions=item.get("deletions", 0),
                    )
                )
        return files

    def _truncate_diff(self, diff: str) -> tuple[str, bool, str]:
        if len(diff) <= MAX_DIFF_CHARS:
            return diff, False, ""
        truncated = diff[:MAX_DIFF_CHARS]
        note = (
            "\n\n[Note: diff was truncated to fit context limits. "
            "Some changes may not be visible to agents.]\n"
        )
        return truncated + note, True, note
