"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from configctl.git_repository import GitRepository
from configctl.logging_config import reset_logging


@pytest.fixture(autouse=True)
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a fixed Git identity, independent of local settings."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test User")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.fixture(autouse=True)
def audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Send each test's audit log to a temporary file, never the home folder."""
    log_file = tmp_path / "audit.log"
    monkeypatch.setenv("CONFIGCTL_LOG_FILE", str(log_file))
    yield log_file
    reset_logging()


@pytest.fixture
def config_repo(tmp_path: Path) -> Iterator[GitRepository]:
    """Create a fresh configuration repository for a single test."""
    with GitRepository.init(tmp_path / "configs") as repo:
        yield repo
