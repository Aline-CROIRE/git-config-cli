"""Tests for ConfigManager using real temporary Git repositories."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from configctl.config_parser import ConfigData, ConfigParser
from configctl.exceptions import BranchError, ConfigNotFound, InvalidConfigError
from configctl.git_repository import GitRepository
from configctl.manager import ConfigManager


@pytest.fixture
def manager(config_repo: GitRepository) -> ConfigManager:
    return ConfigManager(config_repo, ConfigParser())


# --- Drafts ---------------------------------------------------------------


def test_create_draft_creates_branch_and_stays_on_main(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    branch = manager.create_draft("timeout")

    assert branch == "draft/timeout"
    assert "draft/timeout" in config_repo.list_branches()
    assert config_repo.current_branch == "main"


@pytest.mark.parametrize("bad_name", ["", "has space", "a/b", "-starts-with-dash"])
def test_invalid_draft_name_raises_branch_error(
    manager: ConfigManager, bad_name: str
) -> None:
    with pytest.raises(BranchError, match="Invalid draft name"):
        manager.create_draft(bad_name)


def test_create_existing_draft_raises_branch_error(manager: ConfigManager) -> None:
    manager.create_draft("timeout")

    with pytest.raises(BranchError, match="already exists"):
        manager.create_draft("timeout")


# --- Setting values -------------------------------------------------------


def test_set_value_changes_draft_only(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    manager.create_draft("timeout")

    manager.set_value("timeout", "app.json", "timeout", 30)

    assert manager.show("app.json", draft="timeout") == {"timeout": 30}
    assert config_repo.current_branch == "main"
    with pytest.raises(ConfigNotFound):
        manager.show("app.json")


def test_set_value_with_dotted_keys_creates_sections(manager: ConfigManager) -> None:
    manager.create_draft("db")

    manager.set_value("db", "app.yaml", "database.port", 5432)
    manager.set_value("db", "app.yaml", "database.host", "localhost")

    assert manager.show("app.yaml", draft="db") == {
        "database": {"host": "localhost", "port": 5432}
    }


def test_set_value_through_non_section_raises_and_returns_to_main(
    manager: ConfigManager, config_repo: GitRepository
) -> None:
    manager.create_draft("debug")
    manager.set_value("debug", "app.json", "debug", True)

    with pytest.raises(InvalidConfigError, match="not a section"):
        manager.set_value("debug", "app.json", "debug.level", 3)
    assert config_repo.current_branch == "main"


def test_set_value_with_empty_key_part_raises(manager: ConfigManager) -> None:
    manager.create_draft("bad")

    with pytest.raises(InvalidConfigError, match="Invalid key"):
        manager.set_value("bad", "app.json", "a..b", 1)


def test_set_value_outside_repository_raises(manager: ConfigManager) -> None:
    manager.create_draft("escape")

    with pytest.raises(InvalidConfigError, match="inside the configuration"):
        manager.set_value("escape", "../outside.json", "a", 1)


def test_set_value_on_missing_draft_raises_branch_error(
    manager: ConfigManager,
) -> None:
    with pytest.raises(BranchError, match="does not exist"):
        manager.set_value("missing", "app.json", "a", 1)


def test_show_missing_draft_raises_branch_error(manager: ConfigManager) -> None:
    with pytest.raises(BranchError, match="does not exist"):
        manager.show("app.json", draft="missing")


# --- Publishing, history and rollback ------------------------------------


def test_publish_makes_draft_visible_on_main(manager: ConfigManager) -> None:
    manager.create_draft("timeout")
    manager.set_value("timeout", "app.json", "timeout", 30)

    manager.publish("timeout")

    assert manager.show("app.json") == {"timeout": 30}


def test_history_lists_changes_newest_first(manager: ConfigManager) -> None:
    manager.create_draft("setup")
    manager.set_value("setup", "app.json", "timeout", 30)
    manager.set_value("setup", "app.json", "retries", 3)
    manager.publish("setup")

    messages = [entry.message for entry in manager.history("app.json")]

    assert messages == ["Set retries in app.json", "Set timeout in app.json"]


def test_rollback_restores_old_version_as_new_commit(manager: ConfigManager) -> None:
    manager.create_draft("first")
    manager.set_value("first", "app.json", "timeout", 30)
    manager.publish("first")
    manager.create_draft("second")
    manager.set_value("second", "app.json", "timeout", 60)
    manager.publish("second")
    old_sha = manager.history("app.json")[-1].sha

    manager.rollback("app.json", old_sha)

    assert manager.show("app.json") == {"timeout": 30}
    assert manager.history("app.json")[0].message.startswith("Rollback app.json")


def test_rollback_to_unknown_revision_raises_config_not_found(
    manager: ConfigManager,
) -> None:
    with pytest.raises(ConfigNotFound, match="Revision"):
        manager.rollback("app.json", "does-not-exist")


# --- Failure handling with mocks -----------------------------------------


def test_failure_before_writing_returns_to_main(config_repo: GitRepository) -> None:
    parser = Mock(wraps=ConfigParser())
    parser.write.side_effect = OSError("disk full")
    manager = ConfigManager(config_repo, parser)
    manager.create_draft("timeout")

    with pytest.raises(OSError, match="disk full"):
        manager.set_value("timeout", "app.json", "timeout", 30)
    assert config_repo.current_branch == "main"


def test_failure_after_writing_keeps_draft_checked_out(
    config_repo: GitRepository,
) -> None:
    def write_then_fail(path: Path, data: ConfigData) -> None:
        path.write_text("partial", encoding="utf-8")
        raise OSError("disk full")

    parser = Mock(wraps=ConfigParser())
    parser.write.side_effect = write_then_fail
    manager = ConfigManager(config_repo, parser)
    manager.create_draft("timeout")

    with pytest.raises(OSError, match="disk full"):
        manager.set_value("timeout", "app.json", "timeout", 30)
    assert config_repo.current_branch == "draft/timeout"
    assert config_repo.is_dirty()
