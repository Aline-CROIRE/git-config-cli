"""Tests that publishing refuses drafts containing invalid configuration files."""

import pytest
from click.testing import CliRunner
from git import Repo

from configctl.cli import main
from configctl.config_parser import ConfigParser
from configctl.exceptions import ConfigNotFound, InvalidConfigError
from configctl.git_repository import GitRepository
from configctl.manager import ConfigManager

CONFLICTED_JSON = (
    "{\n"
    "<<<<<<< HEAD\n"
    '  "timeout": 10\n'
    "=======\n"
    '  "timeout": 90\n'
    ">>>>>>> main\n"
    "}\n"
)


@pytest.fixture
def manager(config_repo: GitRepository) -> ConfigManager:
    return ConfigManager(config_repo, ConfigParser())


def commit_on_branch(
    repo: GitRepository, branch: str, filename: str, content: str
) -> None:
    """Commit a file with exact content on a branch, then return to main."""
    repo.checkout(branch)
    (repo.root / filename).write_text(content, encoding="utf-8", newline="\n")
    repo.commit_files([filename], f"Add {filename}")
    repo.checkout("main")


# --- GitRepository.changed_files ------------------------------------------


def test_changed_files_lists_only_draft_changes(config_repo: GitRepository) -> None:
    config_repo.create_branch("draft/x")
    commit_on_branch(config_repo, "draft/x", "app.json", "{}\n")
    (config_repo.root / "main-only.json").write_text(
        "{}\n", encoding="utf-8", newline="\n"
    )
    config_repo.commit_files(["main-only.json"], "Change main directly")

    assert config_repo.changed_files("draft/x", "main") == ["app.json"]


def test_changed_files_ignores_deleted_files(config_repo: GitRepository) -> None:
    config_repo.create_branch("draft/x")
    with Repo(config_repo.root) as raw:
        raw.git.switch("draft/x")
        raw.git.rm(".gitignore")
        raw.git.commit("-m", "Remove .gitignore")
        raw.git.switch("main")

    assert config_repo.changed_files("draft/x", "main") == []


# --- Publishing -------------------------------------------------------------


def test_publish_refuses_draft_with_conflict_markers(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    manager.create_draft("broken")
    commit_on_branch(config_repo, "draft/broken", "app.json", CONFLICTED_JSON)

    with pytest.raises(InvalidConfigError, match="cannot be published"):
        manager.publish("broken")

    assert config_repo.current_branch == "main"
    with pytest.raises(ConfigNotFound):
        manager.show("app.json")


def test_publish_ignores_files_that_are_not_configs(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    manager.create_draft("docs")
    commit_on_branch(config_repo, "draft/docs", "README.md", "# Notes\n")
    manager.set_value("docs", "app.json", "timeout", 30)

    manager.publish("docs")

    assert manager.show("app.json") == {"timeout": 30}


def test_cli_publish_reports_invalid_draft(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    manager.create_draft("broken")
    commit_on_branch(config_repo, "draft/broken", "app.json", CONFLICTED_JSON)

    result = CliRunner().invoke(
        main, ["--repo", str(config_repo.root), "publish", "broken"]
    )

    assert result.exit_code == 1
    assert "cannot be published" in result.output
