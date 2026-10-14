"""Command-line interface for configctl."""

import click

from configctl import __version__


@click.group()
@click.version_option(version=__version__, prog_name="configctl")
def main() -> None:
    """Manage configuration files stored in a Git repository."""
