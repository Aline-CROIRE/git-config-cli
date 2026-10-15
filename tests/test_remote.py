"""Tests for remotes: set_remote, push, clone and temporary clones."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from git import Repo
from git.cmd import Git
from git.exc import GitCommandError

from configctl.cli import main
from configctl.config_parser import ConfigParser
from configctl.exceptions import InvalidRepoError, RemoteError
from configctl.git_repository import GitRepository
from configctl.manager import ConfigManager


@pytest.fixture
def server(tmp_path: Path) -> Path:
    """Create an empty bare repository that acts as the remote server."""
    path = tmp_path / "server.git"
    Repo.init(path, bare=True, initial_branch="main").close()
    return path


def publish_timeout(repo: GitRepository) -> None:
    """Publish ``timeout: 30`` in app.json on the repository's main branch."""
    manager = ConfigManager(repo, ConfigParser())
    manager.create_draft("timeout")
    manager.set_value("timeout", "app.json", "timeout", 30)
    manager.publish("timeout")


# --- set_remote and push ----------------------------------------------------


def test_set_remote_adds_origin(config_repo: GitRepository, server: Path) -> None:
    config_repo.set_remote(str(server))

    with Repo(config_repo.root) as raw:
        assert Path(raw.remote("origin").url) == server


def test_set_remote_replaces_existing_address(
    config_repo: GitRepository, server: Path, tmp_path: Path
) -> None:
    config_repo.set_remote(str(tmp_path / "old.git"))

    config_repo.set_remote(str(server))

    with Repo(config_repo.root) as raw:
        assert Path(raw.remote("origin").url) == server


def test_push_sends_main_to_server(config_repo: GitRepository, server: Path) -> None:
    config_repo.set_remote(str(server))

    config_repo.push()

    with Repo(config_repo.root) as local, Repo(server) as remote:
        assert remote.commit("main").hexsha == local.head.commit.hexsha


def test_push_without_remote_raises_remote_error(
    config_repo: GitRepository,
) -> None:
    with pytest.raises(RemoteError, match="No remote"):
        config_repo.push()


def test_failed_push_raises_remote_error(
    config_repo: GitRepository, server: Path
) -> None:
    config_repo.set_remote(str(server))
    failure = GitCommandError("git push", 1, "rejected: simulated failure")

    with patch.object(Git, "push", create=True, side_effect=failure):
        with pytest.raises(RemoteError, match="Could not push"):
            config_repo.push()


# --- clone and temporary_clone ----------------------------------------------


def test_clone_copies_published_configuration(
    config_repo: GitRepository, server: Path, tmp_path: Path
) -> None:
    publish_timeout(config_repo)
    config_repo.set_remote(str(server))
    config_repo.push()

    with GitRepository.clone(str(server), tmp_path / "teammate") as copy:
        assert copy.current_branch == "main"
        assert ConfigManager(copy, ConfigParser()).show("app.json") == {"timeout": 30}


def test_clone_missing_remote_raises_invalid_repo_error(tmp_path: Path) -> None:
    with pytest.raises(InvalidRepoError, match="Could not clone"):
        GitRepository.clone(str(tmp_path / "missing.git"), tmp_path / "copy")


def test_clone_inside_repository_is_refused(
    config_repo: GitRepository, server: Path
) -> None:
    with pytest.raises(InvalidRepoError, match="inside a Git repository"):
        GitRepository.clone(str(server), config_repo.root / "nested")


def test_temporary_clone_is_deleted_afterwards(
    config_repo: GitRepository, server: Path
) -> None:
    config_repo.set_remote(str(server))
    config_repo.push()

    with GitRepository.temporary_clone(str(server)) as temporary:
        folder = temporary.root
        assert (folder / ".gitignore").is_file()

    assert not folder.exists()


# --- CLI ----------------------------------------------------------------------


def test_cli_remote_push_inspect_and_clone(
    config_repo: GitRepository, server: Path, tmp_path: Path
) -> None:
    publish_timeout(config_repo)
    runner = CliRunner()
    root = str(config_repo.root)

    remote_result = runner.invoke(main, ["--repo", root, "remote", str(server)])
    push_result = runner.invoke(main, ["--repo", root, "push"])
    inspect_result = runner.invoke(main, ["inspect", str(server), "app.json"])
    clone_result = runner.invoke(
        main, ["clone", str(server), str(tmp_path / "teammate")]
    )

    assert remote_result.exit_code == 0
    assert "Pushed main to origin" in push_result.output
    assert '"timeout": 30' in inspect_result.output
    assert clone_result.exit_code == 0
    assert (tmp_path / "teammate" / "app.json").is_file()


def test_cli_push_without_remote_reports_error(config_repo: GitRepository) -> None:
    result = CliRunner().invoke(main, ["--repo", str(config_repo.root), "push"])

    assert result.exit_code == 1
    assert "No remote" in result.output


def test_cli_clone_failure_reports_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main, ["clone", str(tmp_path / "missing.git"), str(tmp_path / "copy")]
    )

    assert result.exit_code == 1
    assert "Could not clone" in result.output
