"""Command-line interface for configctl."""

from pathlib import Path

import click

from configctl import __version__
from configctl.exceptions import ConfigCtlError
from configctl.git_repository import GitRepository


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
