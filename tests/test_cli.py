"""Tests for the command-line interface."""

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from configctl import __version__
from configctl.cli import _parse_value, main
from configctl.git_repository import GitRepository


def run(repo: Path, *args: str) -> Result:
    """Run configctl against a repository and return the result."""
    return CliRunner().invoke(main, ["--repo", str(repo), *args])


# --- Basics and init ------------------------------------------------------


def test_version_option_shows_version() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_creates_repository(tmp_path: Path) -> None:
    target = tmp_path / "configs"

    result = run(target, "init")

    assert result.exit_code == 0
    assert "Initialized configuration repository" in result.output
    assert (target / ".git").is_dir()


def test_init_uses_repo_from_environment_variable(tmp_path: Path) -> None:
    target = tmp_path / "configs"

    result = CliRunner().invoke(main, ["init"], env={"CONFIGCTL_REPO": str(target)})

    assert result.exit_code == 0
    assert (target / ".git").is_dir()


def test_init_twice_reports_error(tmp_path: Path) -> None:
    target = tmp_path / "configs"
    run(target, "init")

    result = run(target, "init")

    assert result.exit_code == 1
    assert "already exists" in result.output


# --- Value parsing --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30", 30),
        ("true", True),
        ("[1, 2]", [1, 2]),
        ("localhost", "localhost"),
        ('"30"', "30"),
    ],
)
def test_parse_value(raw: str, expected: Any) -> None:
    assert _parse_value(raw) == expected


# --- Draft workflow -------------------------------------------------------


def test_draft_command_creates_draft(config_repo: GitRepository) -> None:
    result = run(config_repo.root, "draft", "timeout")

    assert result.exit_code == 0
    assert "Created draft 'timeout'" in result.output


def test_full_workflow_draft_set_show_publish(config_repo: GitRepository) -> None:
    root = config_repo.root
    run(root, "draft", "timeout")

    set_result = run(root, "set", "timeout", "app.json", "timeout", "30")
    draft_view = run(root, "show", "app.json", "--draft", "timeout")
    publish_result = run(root, "publish", "timeout")
    main_view = run(root, "show", "app.json")

    assert set_result.exit_code == 0
    assert '"timeout": 30' in draft_view.output
    assert publish_result.exit_code == 0
    assert "Published draft 'timeout'" in publish_result.output
    assert '"timeout": 30' in main_view.output


def test_history_lists_published_changes(config_repo: GitRepository) -> None:
    root = config_repo.root
    run(root, "draft", "timeout")
    run(root, "set", "timeout", "app.json", "timeout", "30")
    run(root, "publish", "timeout")

    result = run(root, "history", "app.json")

    assert result.exit_code == 0
    assert "Set timeout in app.json" in result.output
    assert "Test User" in result.output


def test_history_of_unknown_file_says_so(config_repo: GitRepository) -> None:
    result = run(config_repo.root, "history", "missing.json")

    assert result.exit_code == 0
    assert "No history for missing.json" in result.output


def test_rollback_restores_previous_value(config_repo: GitRepository) -> None:
    root = config_repo.root
    run(root, "draft", "first")
    run(root, "set", "first", "app.json", "timeout", "30")
    run(root, "publish", "first")
    old_sha = config_repo.history("app.json", "main")[0].short_sha
    run(root, "draft", "second")
    run(root, "set", "second", "app.json", "timeout", "60")
    run(root, "publish", "second")

    result = run(root, "rollback", "app.json", old_sha)
    main_view = run(root, "show", "app.json")

    assert result.exit_code == 0
    assert "Rolled back app.json" in result.output
    assert '"timeout": 30' in main_view.output


# --- Error reporting ------------------------------------------------------


def test_show_missing_file_reports_error(config_repo: GitRepository) -> None:
    result = run(config_repo.root, "show", "missing.json")

    assert result.exit_code == 1
    assert "Error:" in result.output


def test_command_on_folder_without_repository_reports_error(
    tmp_path: Path,
) -> None:
    result = run(tmp_path, "draft", "timeout")

    assert result.exit_code == 1
    assert "Not a Git repository" in result.output
