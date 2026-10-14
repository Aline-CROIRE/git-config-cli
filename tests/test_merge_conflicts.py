"""Tests that create real merge conflicts and check how they are handled."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner
from git import Repo
from git.cmd import Git
from git.exc import GitCommandError

from configctl.cli import main
from configctl.config_parser import ConfigParser
from configctl.exceptions import BranchError, MergeConflictError
from configctl.git_repository import GitRepository
from configctl.manager import ConfigManager


@pytest.fixture
def manager(config_repo: GitRepository) -> ConfigManager:
    return ConfigManager(config_repo, ConfigParser())


def make_conflict(manager: ConfigManager) -> None:
    """Publish one draft, leaving a second draft that changes the same value."""
    manager.create_draft("thirty")
    manager.create_draft("sixty")
    manager.set_value("thirty", "app.json", "timeout", 30)
    manager.set_value("sixty", "app.json", "timeout", 60)
    manager.publish("thirty")


def test_conflicting_publish_raises_merge_conflict_error(
    manager: ConfigManager,
) -> None:
    make_conflict(manager)

    with pytest.raises(MergeConflictError) as caught:
        manager.publish("sixty")

    assert caught.value.branch == "draft/sixty"
    assert caught.value.conflicted_files == ["app.json"]


def test_conflict_is_aborted_and_main_is_unchanged(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    make_conflict(manager)

    with pytest.raises(MergeConflictError):
        manager.publish("sixty")

    assert config_repo.current_branch == "main"
    assert not config_repo.is_dirty()
    assert not (config_repo.root / ".git" / "MERGE_HEAD").exists()
    assert manager.show("app.json") == {"timeout": 30}


def test_conflict_can_be_resolved_by_merging_main_into_draft(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    make_conflict(manager)

    with Repo(config_repo.root) as raw:
        raw.git.switch("draft/sixty")
        with pytest.raises(GitCommandError):
            raw.git.merge("main")
        (config_repo.root / "app.json").write_text(
            '{\n  "timeout": 60\n}\n', encoding="utf-8", newline="\n"
        )
        raw.git.add("app.json")
        raw.git.commit("-m", "Resolve conflict: keep timeout 60")
        raw.git.switch("main")
    manager.publish("sixty")

    assert manager.show("app.json") == {"timeout": 60}


def test_merge_failure_without_conflicts_raises_branch_error(
    config_repo: GitRepository,
) -> None:
    config_repo.create_branch("draft/x")
    failure = GitCommandError("git merge", 128, "fatal: simulated failure")

    with patch.object(Git, "merge", create=True, side_effect=failure):
        with pytest.raises(BranchError, match="Could not merge"):
            config_repo.merge("draft/x", "main", "Publish draft/x")


def test_cli_publish_conflict_explains_how_to_resolve(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    make_conflict(manager)

    result = CliRunner().invoke(
        main, ["--repo", str(config_repo.root), "publish", "sixty"]
    )

    assert result.exit_code == 1
    assert "conflicts with main" in result.output
    assert "app.json" in result.output
    assert "git merge main" in result.output
    assert "publish sixty" in result.output
