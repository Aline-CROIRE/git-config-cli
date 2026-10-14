"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from configctl.git_repository import GitRepository


@pytest.fixture
def config_repo(tmp_path: Path) -> Iterator[GitRepository]:
    """Create a fresh configuration repository for a single test."""
    with GitRepository.init(tmp_path / "configs") as repo:
        yield repo
