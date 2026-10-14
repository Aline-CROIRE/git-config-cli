"""Command-line interface for configctl."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click

from configctl import __version__
from configctl.config_parser import ConfigParser
from configctl.exceptions import ConfigCtlError, MergeConflictError
from configctl.git_repository import GitRepository
from configctl.manager import DRAFT_PREFIX, ConfigManager


@contextmanager
def _reported_errors(repo_path: Path | None = None) -> Iterator[None]:
    """Turn configctl errors into clean ``Error: ...`` messages for the user."""
    try:
        yield
    except MergeConflictError as error:
        help_text = _conflict_help(error, repo_path or Path("."))
        raise click.ClickException(help_text) from error
    except ConfigCtlError as error:
        raise click.ClickException(str(error)) from error


@contextmanager
def _open_repository(repo_path: Path) -> Iterator[GitRepository]:
    """Open the configuration repository, reporting errors cleanly."""
    with _reported_errors(repo_path), GitRepository.open(repo_path) as repo:
        yield repo


@contextmanager
def _open_manager(repo_path: Path) -> Iterator[ConfigManager]:
    """Build a ConfigManager on the repository.

    This is where the concrete classes are chosen (the composition root);
    configuration commands work only through ConfigManager.
    """
    with _open_repository(repo_path) as repo:
        yield ConfigManager(repo, ConfigParser())


def _conflict_help(error: MergeConflictError, repo_path: Path) -> str:
    """Explain a merge conflict and the Git steps that resolve it."""
    draft_name = error.branch.removeprefix(DRAFT_PREFIX)
    files = "\n".join(f"  - {name}" for name in error.conflicted_files)
    return (
        f"Cannot publish draft '{draft_name}': it conflicts with main in:\n"
        f"{files}\n"
        "\n"
        "Nothing was changed on main. To resolve the conflict:\n"
        f"  1. cd {repo_path}\n"
        f"  2. git switch {error.branch}\n"
        "  3. git merge main\n"
        "  4. Edit each conflicted file: keep the values you want and delete\n"
        "     the <<<<<<<, ======= and >>>>>>> marker lines\n"
        "  5. git add <file>, then git commit\n"
        f"  6. configctl --repo {repo_path} publish {draft_name}"
    )


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


# --- Repository setup -------------------------------------------------------


@main.command()
@click.pass_obj
def init(repo_path: Path) -> None:
    """Create a new configuration repository at the --repo folder."""
    with _reported_errors(repo_path), GitRepository.init(repo_path) as repo:
        click.echo(f"Initialized configuration repository at {repo.root}")


@main.command()
@click.argument("url")
@click.argument("destination", type=click.Path(file_okay=False, path_type=Path))
def clone(url: str, destination: Path) -> None:
    """Clone the configuration repository at URL into DESTINATION."""
    with _reported_errors(destination), GitRepository.clone(url, destination) as repo:
        click.echo(f"Cloned {url} into {repo.root}")


@main.command()
@click.argument("url")
@click.pass_obj
def remote(repo_path: Path, url: str) -> None:
    """Set URL as the remote (origin) that push sends configurations to."""
    with _open_repository(repo_path) as repo:
        repo.set_remote(url)
    click.echo(f"Remote 'origin' set to {url}")


@main.command()
@click.pass_obj
def push(repo_path: Path) -> None:
    """Push the published configurations on main to the remote."""
    with _open_repository(repo_path) as repo:
        repo.push()
    click.echo("Pushed main to origin")


# --- Configuration workflow -------------------------------------------------


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


@main.command(name="inspect")
@click.argument("url")
@click.argument("filename", metavar="FILE")
def inspect_remote(url: str, filename: str) -> None:
    """Print FILE from main of the repository at URL, without keeping a copy."""
    with _reported_errors(), GitRepository.temporary_clone(url) as repo:
        data = ConfigManager(repo, ConfigParser()).show(filename)
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
