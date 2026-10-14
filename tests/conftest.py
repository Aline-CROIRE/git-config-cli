"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from configctl.git_repository import GitRepository


@pytest.fixture(autouse=True)
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a fixed Git identity, independent of local settings."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test User")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.fixture
def config_repo(tmp_path: Path) -> Iterator[GitRepository]:
    """Create a fresh configuration repository for a single test."""
    with GitRepository.init(tmp_path / "configs") as repo:
        yield repo
