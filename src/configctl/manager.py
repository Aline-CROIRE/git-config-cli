"""Business logic for drafting, publishing and rolling back configurations."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from configctl.config_parser import ConfigData
from configctl.exceptions import BranchError, ConfigNotFound, InvalidConfigError
from configctl.git_repository import CommitInfo
from configctl.protocols import ConfigFormat, VersionControl

MAIN_BRANCH = "main"
DRAFT_PREFIX = "draft/"
_DRAFT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ConfigManager:
    """Coordinate configuration changes between a parser and version control.

    The manager depends only on the ConfigFormat and VersionControl protocols,
    so it never needs to know about GitPython, JSON or YAML directly.
    """

    def __init__(self, repo: VersionControl, parser: ConfigFormat) -> None:
        """Create a manager.

        Args:
            repo: Stores the configuration files and their history.
            parser: Reads and writes the configuration file formats.
        """
        self._repo = repo
        self._parser = parser

    @staticmethod
    def draft_branch(name: str) -> str:
        """Return the branch name used for a draft.

        Args:
            name: The draft name, for example ``timeout``.

        Returns:
            The branch name, for example ``draft/timeout``.

        Raises:
            BranchError: If the name contains characters that are not allowed.
        """
        if not _DRAFT_NAME.match(name):
            raise BranchError(
                f"Invalid draft name '{name}'. "
                "Use letters, numbers, '.', '_' or '-'."
            )
        return f"{DRAFT_PREFIX}{name}"

    def create_draft(self, name: str) -> str:
        """Create a draft branch from ``main``.

        Args:
            name: The draft name.

        Returns:
            The new branch name.

        Raises:
            BranchError: If the name is invalid or the draft already exists.
        """
        branch = self.draft_branch(name)
        self._repo.create_branch(branch, MAIN_BRANCH)
        return branch

    def set_value(self, draft: str, filename: str, key: str, value: Any) -> str:
        """Set one value in a configuration file on a draft and commit it.

        Args:
            draft: The draft name.
            filename: The configuration file, relative to the repository.
            key: The key to set. Dots reach into sections: ``database.port``.
            value: The new value. Any JSON or YAML compatible value.

        Returns:
            The SHA of the new commit.

        Raises:
            BranchError: If the draft does not exist.
            InvalidConfigError: If the key or file name is invalid.
        """
        branch = self._existing_draft(draft)
        path = self._config_path(filename)
        with self._on_branch(branch):
            data = self._load_or_empty(filename, branch)
            _set_nested(data, key, value)
            self._parser.write(path, data)
            return self._repo.commit_files([filename], f"Set {key} in {filename}")

    def show(self, filename: str, draft: str | None = None) -> ConfigData:
        """Return a configuration from ``main`` or from a draft.

        Args:
            filename: The configuration file, relative to the repository.
            draft: The draft to read from. Reads ``main`` when not given.

        Returns:
            The parsed configuration.

        Raises:
            BranchError: If the draft does not exist.
            ConfigNotFound: If the file does not exist there.
        """
        revision = self._existing_draft(draft) if draft else MAIN_BRANCH
        return self._parser.parse(self._repo.read_file(filename, revision), filename)

    def publish(self, draft: str) -> str:
        """Publish a draft by merging it into ``main``.

        Args:
            draft: The draft name.

        Returns:
            The SHA of the merge commit.

        Raises:
            BranchError: If the draft does not exist.
        """
        branch = self._existing_draft(draft)
        return self._repo.merge(branch, MAIN_BRANCH, f"Publish {branch}")

    def history(self, filename: str) -> list[CommitInfo]:
        """List the commits that changed a configuration on ``main``.

        Args:
            filename: The configuration file, relative to the repository.

        Returns:
            The commits, newest first.
        """
        return self._repo.history(filename, MAIN_BRANCH)

    def rollback(self, filename: str, revision: str) -> str:
        """Restore an older version of a configuration as a new commit on main.

        History is never rewritten: the old content is committed again.

        Args:
            filename: The configuration file, relative to the repository.
            revision: The commit to restore the file from.

        Returns:
            The SHA of the new rollback commit.

        Raises:
            ConfigNotFound: If the revision or the file does not exist.
            InvalidConfigError: If the file name is invalid.
        """
        path = self._config_path(filename)
        with self._on_branch(MAIN_BRANCH):
            old_content = self._repo.read_file(filename, revision)
            self._parser.write(path, self._parser.parse(old_content, filename))
            return self._repo.commit_files(
                [filename], f"Rollback {filename} to {revision}"
            )

    def _existing_draft(self, draft: str) -> str:
        """Return the draft's branch name, checking that it exists."""
        branch = self.draft_branch(draft)
        if not self._repo.branch_exists(branch):
            raise BranchError(f"Draft '{draft}' does not exist")
        return branch

    def _config_path(self, filename: str) -> Path:
        """Return the file's full path, refusing paths outside the repository."""
        root = self._repo.root.resolve()
        path = (root / filename).resolve()
        if root not in path.parents:
            raise InvalidConfigError(
                f"'{filename}' must be a file inside the configuration repository"
            )
        return path

    def _load_or_empty(self, filename: str, revision: str) -> ConfigData:
        """Load a configuration, or return an empty one if it does not exist."""
        try:
            content = self._repo.read_file(filename, revision)
        except ConfigNotFound:
            return {}
        return self._parser.parse(content, filename)

    @contextmanager
    def _on_branch(self, branch: str) -> Iterator[None]:
        """Check out a branch for a ``with`` block, then return to main.

        If the block fails and leaves uncommitted changes behind, the
        repository stays on the branch so no work is silently thrown away.
        """
        self._repo.checkout(branch)
        try:
            yield
        except BaseException:
            if not self._repo.is_dirty():
                self._repo.checkout(MAIN_BRANCH)
            raise
        self._repo.checkout(MAIN_BRANCH)


def _set_nested(data: ConfigData, key: str, value: Any) -> None:
    """Set a value at a dotted key such as ``database.port``.

    Missing sections are created. Raises InvalidConfigError if the key is
    empty or passes through a value that is not a section.
    """
    parts = key.split(".")
    if not all(parts):
        raise InvalidConfigError(f"Invalid key '{key}'")
    current = data
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        elif not isinstance(child, dict):
            raise InvalidConfigError(f"Cannot set '{key}': '{part}' is not a section")
        current = child
    current[parts[-1]] = value
