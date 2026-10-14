"""Command-line interface for configctl."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click

from configctl import __version__
from configctl.config_parser import ConfigParser
from configctl.exceptions import ConfigCtlError
from configctl.git_repository import GitRepository
from configctl.manager import ConfigManager


@contextmanager
def _open_manager(repo_path: Path) -> Iterator[ConfigManager]:
    """Open the repository, build a ConfigManager, and report errors cleanly.

    This is the only place where the concrete classes are chosen (the
    composition root); every command works through ConfigManager.
    """
    try:
        with GitRepository.open(repo_path) as repo:
            yield ConfigManager(repo, ConfigParser())
    except ConfigCtlError as error:
        raise click.ClickException(str(error)) from error


def _parse_value(raw: str) -> Any:
    """Interpret a command-line value as JSON when possible, otherwise as text.

    ``30`` becomes a number, ``true`` a boolean and ``[1, 2]`` a list.
    Anything that is not valid JSON, such as ``localhost``, stays text.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


@click.group()
@click.version_option(version=__version__, prog_name="configctl")
@click.option(
    "--repo",
    "repo_path",
    type=click.Path(file_okay=False, path_type=Path),
    default=".",
    show_default=True,
    envvar="CONFIGCTL_REPO",
    help="Folder of the configuration repository.",
)
@click.pass_context
def main(ctx: click.Context, repo_path: Path) -> None:
    """Manage configuration files stored in a Git repository."""
    ctx.obj = repo_path


@main.command()
@click.pass_obj
def init(repo_path: Path) -> None:
    """Create a new configuration repository at the --repo folder."""
    try:
        with GitRepository.init(repo_path) as repo:
            click.echo(f"Initialized configuration repository at {repo.root}")
    except ConfigCtlError as error:
        raise click.ClickException(str(error)) from error


@main.command()
@click.argument("name")
@click.pass_obj
def draft(repo_path: Path, name: str) -> None:
    """Create a draft named NAME, branched from main."""
    with _open_manager(repo_path) as manager:
        branch = manager.create_draft(name)
    click.echo(f"Created draft '{name}' on branch {branch}")


@main.command(name="set")
@click.argument("draft_name", metavar="DRAFT")
@click.argument("filename", metavar="FILE")
@click.argument("key")
@click.argument("value")
@click.pass_obj
def set_value(
    repo_path: Path, draft_name: str, filename: str, key: str, value: str
) -> None:
    """Set KEY to VALUE in FILE on DRAFT and commit the change.

    KEY may use dots for nested sections, for example database.port.
    VALUE is read as JSON when possible (30, true, [1, 2]); otherwise as text.
    """
    with _open_manager(repo_path) as manager:
        sha = manager.set_value(draft_name, filename, key, _parse_value(value))
    click.echo(f"Set {key} in {filename} on draft '{draft_name}' (commit {sha[:7]})")


@main.command()
@click.argument("filename", metavar="FILE")
@click.option("--draft", "draft_name", help="Show a draft instead of main.")
@click.pass_obj
def show(repo_path: Path, filename: str, draft_name: str | None) -> None:
    """Print FILE as it is on main, or on a draft with --draft."""
    with _open_manager(repo_path) as manager:
        data = manager.show(filename, draft=draft_name)
    click.echo(json.dumps(data, indent=2, sort_keys=True))


@main.command()
@click.argument("draft_name", metavar="DRAFT")
@click.pass_obj
def publish(repo_path: Path, draft_name: str) -> None:
    """Publish DRAFT by merging it into main."""
    with _open_manager(repo_path) as manager:
        sha = manager.publish(draft_name)
    click.echo(f"Published draft '{draft_name}' into main (commit {sha[:7]})")


@main.command()
@click.argument("filename", metavar="FILE")
@click.pass_obj
def history(repo_path: Path, filename: str) -> None:
    """List the changes to FILE on main, newest first."""
    with _open_manager(repo_path) as manager:
        entries = manager.history(filename)
    if not entries:
        click.echo(f"No history for {filename}")
        return
    for entry in entries:
        when = f"{entry.date:%Y-%m-%d %H:%M}"
        click.echo(f"{entry.short_sha}  {when}  {entry.author}  {entry.message}")


@main.command()
@click.argument("filename", metavar="FILE")
@click.argument("revision")
@click.pass_obj
def rollback(repo_path: Path, filename: str, revision: str) -> None:
    """Restore FILE on main to how it was at REVISION, as a new commit."""
    with _open_manager(repo_path) as manager:
        sha = manager.rollback(filename, revision)
    click.echo(f"Rolled back {filename} to {revision} (new commit {sha[:7]})")
