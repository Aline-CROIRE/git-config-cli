"""Tests for the command-line interface."""

from click.testing import CliRunner

from configctl import __version__
from configctl.cli import main


def test_version_option_shows_version() -> None:
    runner = CliRunner()

    result = runner.invoke(main, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output
