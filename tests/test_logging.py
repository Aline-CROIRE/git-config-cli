"""Tests for structured audit logging."""

import json
import logging
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from configctl.cli import main
from configctl.config_parser import ConfigParser
from configctl.git_repository import GitRepository
from configctl.logging_config import (
    JsonFormatter,
    configure_logging,
    default_log_file,
)
from configctl.manager import ConfigManager


def run(repo: Path, *args: str) -> Result:
    """Run configctl against a repository and return the result."""
    return CliRunner().invoke(main, ["--repo", str(repo), *args])


def read_entries(log_file: Path) -> list[dict[str, object]]:
    """Parse every JSON line in the audit log."""
    lines = log_file.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


# --- The formatter and configuration ----------------------------------------


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.makeLogRecord(
        {
            "name": "configctl.test",
            "levelname": "INFO",
            "msg": "Draft created",
            "action": "draft.create",
            "draft": "timeout",
        }
    )

    entry = json.loads(JsonFormatter().format(record))

    assert entry["message"] == "Draft created"
    assert entry["level"] == "INFO"
    assert entry["action"] == "draft.create"
    assert entry["draft"] == "timeout"
    assert "time" in entry
    assert "lineno" not in entry


def test_default_log_file_is_in_home_folder() -> None:
    assert default_log_file() == Path.home() / ".configctl" / "audit.log"


def test_configure_logging_twice_does_not_duplicate_handlers(tmp_path: Path) -> None:
    configure_logging(tmp_path / "audit.log")
    configure_logging(tmp_path / "audit.log")
    assert len(logging.getLogger("configctl").handlers) == 1

    configure_logging(tmp_path / "audit.log", verbose=True)
    assert len(logging.getLogger("configctl").handlers) == 2


# --- What gets logged -----------------------------------------------------------


def test_manager_logs_business_events(
    config_repo: GitRepository, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="configctl")
    manager = ConfigManager(config_repo, ConfigParser())

    manager.create_draft("timeout")
    manager.set_value("timeout", "app.json", "timeout", 30)

    actions = [getattr(record, "action", None) for record in caplog.records]
    assert actions == ["draft.create", "draft.set"]


def test_audit_log_records_each_change_but_never_values(
    config_repo: GitRepository, audit_log: Path
) -> None:
    root = config_repo.root

    run(root, "draft", "secrets")
    run(root, "set", "secrets", "app.json", "api_key", "s3cr3t-value")
    run(root, "publish", "secrets")

    actions = [entry["action"] for entry in read_entries(audit_log)]
    assert actions == ["draft.create", "draft.set", "draft.publish"]
    assert "s3cr3t-value" not in audit_log.read_text(encoding="utf-8")


def test_setup_commands_are_logged(tmp_path: Path, audit_log: Path) -> None:
    run(tmp_path / "configs", "init")

    entries = read_entries(audit_log)

    assert entries[-1]["action"] == "repo.init"


def test_audit_log_records_errors(config_repo: GitRepository, audit_log: Path) -> None:
    run(config_repo.root, "publish", "missing")

    entry = read_entries(audit_log)[-1]

    assert entry["level"] == "ERROR"
    assert entry["command"] == "publish"
    assert entry["error_type"] == "BranchError"


def test_audit_log_records_merge_conflicts(
    config_repo: GitRepository, audit_log: Path
) -> None:
    manager = ConfigManager(config_repo, ConfigParser())
    manager.create_draft("thirty")
    manager.create_draft("sixty")
    manager.set_value("thirty", "app.json", "timeout", 30)
    manager.set_value("sixty", "app.json", "timeout", 60)
    manager.publish("thirty")

    run(config_repo.root, "publish", "sixty")

    entry = read_entries(audit_log)[-1]
    assert entry["level"] == "WARNING"
    assert entry["conflicted_files"] == ["app.json"]


def test_verbose_flag_prints_log_messages(config_repo: GitRepository) -> None:
    result = run(config_repo.root, "--verbose", "draft", "timeout")

    assert result.exit_code == 0
    assert "Draft created" in result.output
