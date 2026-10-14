"""Tests for the command-line interface."""

from pathlib import Path

from click.testing import CliRunner

from configctl import __version__
from configctl.cli import main


def test_version_option_shows_version() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_creates_repository(tmp_path: Path) -> None:
    target = tmp_path / "configs"

    result = CliRunner().invoke(main, ["--repo", str(target), "init"])

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
    runner = CliRunner()
    runner.invoke(main, ["--repo", str(target), "init"])

    result = runner.invoke(main, ["--repo", str(target), "init"])

    assert result.exit_code == 1
    assert "already exists" in result.output
