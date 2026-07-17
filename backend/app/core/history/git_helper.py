from __future__ import annotations

import subprocess
from pathlib import Path


class GitHelper:
    """Optional helper. Modules may use it, but the core does not force them to."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    def is_git_repo(self) -> bool:
        return (self.workspace_path / ".git").exists()

    def init(self) -> None:
        if not self.is_git_repo():
            subprocess.run(["git", "init"], cwd=self.workspace_path, check=False)

    def status(self) -> str:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.workspace_path,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def commit_all(self, message: str) -> None:
        subprocess.run(["git", "add", "."], cwd=self.workspace_path, check=False)
        subprocess.run(["git", "commit", "-m", message], cwd=self.workspace_path, check=False)
