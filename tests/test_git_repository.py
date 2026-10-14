"""Tests for GitRepository using real temporary Git repositories."""

from pathlib import Path

import pytest
from git import Repo

from configctl.exceptions import BranchError, ConfigNotFound, InvalidRepoError
from configctl.git_repository import GitRepository


def write(repo: GitRepository, relative_path: str, content: str) -> None:
    """Write a text file inside the repository with Unix line endings."""
    (repo.root / relative_path).write_text(content, encoding="utf-8", newline="\n")


# --- Creating and opening repositories ------------------------------------


def test_init_creates_repo_on_main_with_one_commit(
    config_repo: GitRepository,
) -> None:
    assert config_repo.current_branch == "main"
    with Repo(config_repo.root) as raw:
        assert len(list(raw.iter_commits())) == 1


def test_init_commits_a_gitignore(config_repo: GitRepository) -> None:
    content = config_repo.read_file(".gitignore")

    assert "*.bak" in content


def test_init_refuses_existing_repository(config_repo: GitRepository) -> None:
    with pytest.raises(InvalidRepoError, match="already exists"):
        GitRepository.init(config_repo.root)


def test_init_refuses_folder_inside_another_repository(tmp_path: Path) -> None:
    Repo.init(tmp_path / "outer").close()

    with pytest.raises(InvalidRepoError, match="inside another Git repository"):
        GitRepository.init(tmp_path / "outer" / "inner")


def test_open_existing_repository(config_repo: GitRepository) -> None:
    with GitRepository.open(config_repo.root) as opened:
        assert opened.current_branch == "main"


def test_open_folder_without_git_raises_invalid_repo_error(tmp_path: Path) -> None:
    with pytest.raises(InvalidRepoError):
        GitRepository.open(tmp_path)


def test_open_missing_folder_raises_invalid_repo_error(tmp_path: Path) -> None:
    with pytest.raises(InvalidRepoError):
        GitRepository.open(tmp_path / "does-not-exist")


def test_open_bare_repository_raises_invalid_repo_error(tmp_path: Path) -> None:
    Repo.init(tmp_path / "bare", bare=True).close()

    with pytest.raises(InvalidRepoError, match="no working folder"):
        GitRepository.open(tmp_path / "bare")


# --- Commits and reading files --------------------------------------------


def test_commit_files_creates_commit_with_content(
    config_repo: GitRepository,
) -> None:
    write(config_repo, "app.json", '{"debug": true}\n')

    sha = config_repo.commit_files(["app.json"], "feat: add app config")

    with Repo(config_repo.root) as raw:
        assert raw.head.commit.hexsha == sha
        assert raw.head.commit.message == "feat: add app config"
    assert config_repo.read_file("app.json") == '{"debug": true}\n'


def test_read_file_from_older_revision(config_repo: GitRepository) -> None:
    write(config_repo, "app.json", "version 1\n")
    config_repo.commit_files(["app.json"], "first version")
    write(config_repo, "app.json", "version 2\n")
    config_repo.commit_files(["app.json"], "second version")

    assert config_repo.read_file("app.json") == "version 2\n"
    assert config_repo.read_file("app.json", "HEAD~1") == "version 1\n"


def test_read_missing_file_raises_config_not_found(
    config_repo: GitRepository,
) -> None:
    with pytest.raises(ConfigNotFound):
        config_repo.read_file("missing.json")


def test_read_folder_raises_config_not_found(config_repo: GitRepository) -> None:
    (config_repo.root / "nested").mkdir()
    write(config_repo, "nested/app.json", "{}\n")
    config_repo.commit_files(["nested/app.json"], "add nested config")

    with pytest.raises(ConfigNotFound, match="not a file"):
        config_repo.read_file("nested")


# --- Branches, merging and history ----------------------------------------


def test_create_branch_and_list_branches(config_repo: GitRepository) -> None:
    config_repo.create_branch("draft/timeout")

    assert config_repo.list_branches() == ["draft/timeout", "main"]
    assert config_repo.current_branch == "main"


def test_create_existing_branch_raises_branch_error(
    config_repo: GitRepository,
) -> None:
    config_repo.create_branch("draft/timeout")

    with pytest.raises(BranchError, match="already exists"):
        config_repo.create_branch("draft/timeout")


def test_checkout_switches_branch_and_files(config_repo: GitRepository) -> None:
    config_repo.create_branch("draft/timeout")
    config_repo.checkout("draft/timeout")
    write(config_repo, "app.json", "{}\n")
    config_repo.commit_files(["app.json"], "add app config on draft")

    config_repo.checkout("main")

    assert config_repo.current_branch == "main"
    assert not (config_repo.root / "app.json").exists()


def test_checkout_missing_branch_raises_branch_error(
    config_repo: GitRepository,
) -> None:
    with pytest.raises(BranchError, match="does not exist"):
        config_repo.checkout("draft/missing")


def test_checkout_with_uncommitted_changes_raises_branch_error(
    config_repo: GitRepository,
) -> None:
    config_repo.create_branch("draft/timeout")
    write(config_repo, "unsaved.json", "{}\n")

    with pytest.raises(BranchError, match="uncommitted changes"):
        config_repo.checkout("draft/timeout")


def test_merge_creates_merge_commit_on_target(config_repo: GitRepository) -> None:
    config_repo.create_branch("draft/timeout")
    config_repo.checkout("draft/timeout")
    write(config_repo, "app.json", '{"timeout": 30}\n')
    config_repo.commit_files(["app.json"], "set timeout")

    sha = config_repo.merge("draft/timeout", "main", "Publish draft/timeout")

    assert config_repo.current_branch == "main"
    assert config_repo.read_file("app.json") == '{"timeout": 30}\n'
    with Repo(config_repo.root) as raw:
        assert raw.head.commit.hexsha == sha
        assert len(raw.head.commit.parents) == 2


def test_merge_missing_branch_raises_branch_error(
    config_repo: GitRepository,
) -> None:
    with pytest.raises(BranchError, match="does not exist"):
        config_repo.merge("draft/missing", "main", "Publish")


def test_history_lists_commits_for_one_file_newest_first(
    config_repo: GitRepository,
) -> None:
    write(config_repo, "app.json", "version 1\n")
    config_repo.commit_files(["app.json"], "first version")
    write(config_repo, "app.json", "version 2\n")
    config_repo.commit_files(["app.json"], "second version")

    history = config_repo.history("app.json")

    assert [entry.message for entry in history] == ["second version", "first version"]
    assert history[0].author == "Test User"
    assert len(history[0].short_sha) == 7


def test_history_of_never_committed_file_is_empty(
    config_repo: GitRepository,
) -> None:
    assert config_repo.history("missing.json") == []
