"""Abstract interfaces that ConfigManager depends on.

Any class with matching methods satisfies these protocols; it does not need
to inherit from them. This lets ConfigManager work with the real classes,
or with test doubles, without knowing which one it has.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from configctl.config_parser import ConfigData
from configctl.git_repository import CommitInfo


class ConfigFormat(Protocol):
    """Something that converts configuration text to and from dictionaries."""

    def parse(self, content: str, filename: str) -> ConfigData:
        """Parse configuration text into a dictionary."""

    def write(self, path: Path, data: ConfigData) -> None:
        """Serialize a configuration and save it to disk."""


class VersionControl(Protocol):
    """Something that stores versions of files on branches."""

    @property
    def root(self) -> Path:
        """The top-level folder of the repository."""

    @property
    def current_branch(self) -> str:
        """The name of the branch that is currently checked out."""

    def is_dirty(self) -> bool:
        """Return True if there are uncommitted or untracked changes."""

    def branch_exists(self, name: str) -> bool:
        """Return True if a branch with this name exists."""

    def create_branch(self, name: str, start_point: str = "main") -> None:
        """Create a new branch without switching to it."""

    def checkout(self, name: str) -> None:
        """Switch to an existing branch."""

    def merge(self, source: str, target: str, message: str) -> str:
        """Merge one branch into another and return the merge commit SHA."""

    def commit_files(self, relative_paths: Sequence[str], message: str) -> str:
        """Stage files, commit them, and return the commit SHA."""

    def read_file(self, relative_path: str, revision: str = "HEAD") -> str:
        """Read a file's content as it was at a given revision."""

    def history(self, relative_path: str, revision: str = "HEAD") -> list[CommitInfo]:
        """List the commits that changed a file, newest first."""
