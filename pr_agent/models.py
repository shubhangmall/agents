from typing import Literal

from pydantic import BaseModel, Field


class PRFileChange(BaseModel):
    path: str
    additions: int = 0
    deletions: int = 0


class PRCheck(BaseModel):
    name: str
    state: str
    link: str = ""
    description: str = ""


class PRComment(BaseModel):
    author: str
    body: str
    path: str | None = None
    line: int | None = None
    url: str = ""


class PRContext(BaseModel):
    url: str
    title: str
    body: str
    state: str
    head_ref: str
    base_ref: str
    mergeable: str | None
    additions: int
    deletions: int
    files: list[PRFileChange]
    diff: str
    checks: list[PRCheck]
    comments: list[PRComment]
    truncated: bool = False
    truncation_note: str = ""

    def to_prompt(self) -> str:
        """Serialize PR context for agent consumption."""
        files_text = "\n".join(f"  - {f.path} (+{f.additions}/-{f.deletions})" for f in self.files)
        checks_text = (
            "\n".join(f"  - [{c.state}] {c.name}: {c.description}" for c in self.checks)
            or "  (no checks reported)"
        )
        comments_text = (
            "\n".join(
                f"  - @{c.author} on {c.path or 'general'}"
                f"{f' line {c.line}' if c.line else ''}: {c.body[:500]}"
                for c in self.comments
            )
            or "  (no unresolved review comments)"
        )

        return (
            f"PR URL: {self.url}\n"
            f"Title: {self.title}\n"
            f"State: {self.state}\n"
            f"Branch: {self.head_ref} -> {self.base_ref}\n"
            f"Mergeable: {self.mergeable}\n"
            f"Changes: +{self.additions}/-{self.deletions}\n\n"
            f"Changed files:\n{files_text}\n\n"
            f"CI checks:\n{checks_text}\n\n"
            f"Unresolved review comments:\n{comments_text}\n\n"
            f"Diff:\n{self.diff}\n"
            f"{self.truncation_note}"
        )


class Issue(BaseModel):
    id: str
    type: Literal["ci_failure", "review_comment", "merge_conflict", "out_of_scope"]
    severity: Literal["blocking", "suggestion"]
    summary: str
    source: str
    actionable: bool
    related_files: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    issues: list[Issue]

    @property
    def actionable_issues(self) -> list[Issue]:
        blocking = [i for i in self.issues if i.actionable and i.severity == "blocking"]
        suggestions = [i for i in self.issues if i.actionable and i.severity == "suggestion"]
        return blocking + suggestions


class ProposedFix(BaseModel):
    issue_id: str
    file_path: str | None = None
    explanation: str
    patch: str
    confidence: Literal["high", "medium", "low"]
    needs_human: bool


class BabysitReport(BaseModel):
    verdict: Literal["ready", "blocked", "needs_review"]
    executive_summary: list[str]
    markdown: str
