"""Tests for the configuration parser."""

from pathlib import Path

import pytest

from configctl.config_parser import ConfigParser
from configctl.exceptions import (
    ConfigNotFound,
    InvalidConfigError,
    UnsupportedFormatError,
)


@pytest.fixture
def parser() -> ConfigParser:
    return ConfigParser()


@pytest.mark.parametrize("filename", ["app.json", "app.yaml", "app.yml"])
def test_write_then_read_returns_same_data(
    parser: ConfigParser, tmp_path: Path, filename: str
) -> None:
    path = tmp_path / filename
    data = {"database": {"host": "localhost", "port": 5432}, "debug": True}

    parser.write(path, data)

    assert parser.read(path) == data


def test_json_output_is_sorted_and_indented(parser: ConfigParser) -> None:
    text = parser.serialize({"b": 1, "a": 2}, "app.json")

    assert text == '{\n  "a": 2,\n  "b": 1\n}\n'


def test_write_uses_unix_line_endings(parser: ConfigParser, tmp_path: Path) -> None:
    path = tmp_path / "app.json"

    parser.write(path, {"a": 1})

    assert b"\r\n" not in path.read_bytes()


def test_read_missing_file_raises_config_not_found(
    parser: ConfigParser, tmp_path: Path
) -> None:
    with pytest.raises(ConfigNotFound):
        parser.read(tmp_path / "missing.json")


@pytest.mark.parametrize(
    ("content", "filename"),
    [("{not json", "app.json"), ("key: [unclosed", "app.yaml")],
)
def test_parse_invalid_content_raises_invalid_config_error(
    parser: ConfigParser, content: str, filename: str
) -> None:
    with pytest.raises(InvalidConfigError):
        parser.parse(content, filename)


def test_parse_non_mapping_raises_invalid_config_error(parser: ConfigParser) -> None:
    with pytest.raises(InvalidConfigError, match="mapping"):
        parser.parse("[1, 2, 3]", "app.json")


def test_unsupported_extension_raises_error(parser: ConfigParser) -> None:
    with pytest.raises(UnsupportedFormatError):
        parser.parse("x = 1", "app.toml")


def test_extension_detection_is_case_insensitive(parser: ConfigParser) -> None:
    result = parser.parse('{"a": 1}', "APP.JSON")

    assert result == {"a": 1}
