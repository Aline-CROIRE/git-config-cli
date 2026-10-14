"""Tests for custom exceptions."""

import pytest

from configctl.exceptions import (
    BranchError,
    ConfigCtlError,
    ConfigNotFound,
    InvalidConfigError,
    InvalidRepoError,
    MergeConflictError,
    UnsupportedFormatError,
)


@pytest.mark.parametrize(
    "error_class",
    [
        ConfigNotFound,
        InvalidRepoError,
        InvalidConfigError,
        UnsupportedFormatError,
        BranchError,
    ],
)
def test_simple_errors_inherit_from_base_error(
    error_class: type[ConfigCtlError],
) -> None:
    error = error_class("something went wrong")

    assert isinstance(error, ConfigCtlError)
    assert str(error) == "something went wrong"


def test_merge_conflict_error_stores_branch_and_files() -> None:
    error = MergeConflictError("draft/timeout", ["app.json", "db.yaml"])

    assert error.branch == "draft/timeout"
    assert error.conflicted_files == ["app.json", "db.yaml"]
    assert "app.json, db.yaml" in str(error)


def test_merge_conflict_error_can_be_caught_as_base_error() -> None:
    with pytest.raises(ConfigCtlError):
        raise MergeConflictError("draft/timeout", ["app.json"])
