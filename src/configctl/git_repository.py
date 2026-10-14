"""Git operations for the configuration repository, implemented with GitPython."""

from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from git.objects.blob import Blob

from configctl.exceptions import ConfigNotFound, InvalidRepoError

DEFAULT_BRANCH = "main"

GITIGNORE_CONTENT = """\
# Files the configuration repository should never track
*.bak
*.tmp
*.swp
*~
.DS_Store
Thumbs.db
"""


class GitRepository:
    """Perform all Git operations on a configuration repository.

    This is the only class in configctl that talks to Git. It knows nothing
    about JSON or YAML; it only stores and reads text files.
    """

    def __init__(self, repo: Repo) -> None:
        """Wrap an existing GitPython repository.

        Prefer the ``init`` and ``open`` class methods over calling this.

        Args:
            repo: The GitPython repository to wrap.
        """
        self._repo = repo

    @classmethod
    def init(cls, path: Path) -> Self:
        """Create a new configuration repository.

        The repository starts on the ``main`` branch with one commit that
        adds a ``.gitignore`` file.

        Args:
            path: Folder for the new repository. Created if it does not exist.

        Returns:
            The new repository.

        Raises:
            InvalidRepoError: If a Git repository already exists at ``path``.
        """
        if (path / ".git").exists():
            raise InvalidRepoError(f"A Git repository already exists at {path}")
        path.mkdir(parents=True, exist_ok=True)
        repository = cls(Repo.init(path, initial_branch=DEFAULT_BRANCH))
        (path / ".gitignore").write_text(
            GITIGNORE_CONTENT, encoding="utf-8", newline="\n"
        )
        repository.commit_files(
            [".gitignore"], "chore: initialize configuration repository"
        )
        return repository

    @classmethod
    def open(cls, path: Path) -> Self:
        """Open an existing configuration repository.

        Args:
            path: The top-level folder of the repository.

        Returns:
            The opened repository.

        Raises:
            InvalidRepoError: If ``path`` is missing, is not a Git repository,
                or has no working folder.
        """
        try:
            repo = Repo(path)
        except (InvalidGitRepositoryError, NoSuchPathError) as error:
            raise InvalidRepoError(f"Not a Git repository: {path}") from error
        if repo.bare:
            repo.close()
            raise InvalidRepoError(f"Repository at {path} has no working folder")
        return cls(repo)

    def __enter__(self) -> Self:
        """Return the repository when entering a ``with`` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the repository when leaving a ``with`` block."""
        self.close()

    def close(self) -> None:
        """Release files and processes held open by GitPython."""
        self._repo.close()

    @property
    def root(self) -> Path:
        """The top-level folder of the repository."""
        return Path(self._repo.working_dir)

    @property
    def current_branch(self) -> str:
        """The name of the branch that is currently checked out."""
        return self._repo.active_branch.name

    def commit_files(self, relative_paths: Sequence[str], message: str) -> str:
        """Stage files and create a commit.

        Args:
            relative_paths: Paths of the files to commit, relative to ``root``.
            message: The commit message.

        Returns:
            The full SHA of the new commit.
        """
        self._repo.index.add(list(relative_paths))
        commit = self._repo.index.commit(message)
        return commit.hexsha

    def read_file(self, relative_path: str, revision: str = "HEAD") -> str:
        """Read a file's content as it was at a given commit.

        Args:
            relative_path: Path of the file, relative to ``root``.
            revision: A commit SHA, branch name, or expression like ``HEAD~1``.

        Returns:
            The file content as text.

        Raises:
            ConfigNotFound: If the file does not exist at that revision.
        """
        commit = self._repo.commit(revision)
        try:
            item = commit.tree / relative_path
        except KeyError:
            raise ConfigNotFound(
                f"'{relative_path}' does not exist at revision {revision}"
            ) from None
        if not isinstance(item, Blob):
            raise ConfigNotFound(
                f"'{relative_path}' is not a file at revision {revision}"
            )
        content: bytes = item.data_stream.read()
        return content.decode("utf-8")
