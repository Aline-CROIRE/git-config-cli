"""Git operations for the configuration repository, implemented with GitPython."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from git import Repo
from git.exc import BadName, BadObject, InvalidGitRepositoryError, NoSuchPathError
from git.objects.blob import Blob

from configctl.exceptions import BranchError, ConfigNotFound, InvalidRepoError

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


@dataclass(frozen=True)
class CommitInfo:
    """A short description of one commit.

    Attributes:
        sha: The full commit SHA.
        message: The first line of the commit message.
        author: The name of the commit author.
        date: When the commit was made.
    """

    sha: str
    message: str
    author: str
    date: datetime

    @property
    def short_sha(self) -> str:
        """The first seven characters of the SHA, as Git usually shows it."""
        return self.sha[:7]


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
            InvalidRepoError: If ``path`` already is, or is inside, a Git
                repository.
        """
        enclosing = _find_enclosing_repository(path)
        if enclosing == path.resolve():
            raise InvalidRepoError(f"A Git repository already exists at {path}")
        if enclosing is not None:
            raise InvalidRepoError(
                f"Cannot create a repository inside another Git repository "
                f"({enclosing})"
            )
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

    def is_dirty(self) -> bool:
        """Return True if there are uncommitted or untracked changes."""
        return self._repo.is_dirty(untracked_files=True)

    def list_branches(self) -> list[str]:
        """Return the names of all local branches, sorted alphabetically."""
        return sorted(head.name for head in self._repo.heads)

    def branch_exists(self, name: str) -> bool:
        """Return True if a local branch with this name exists."""
        return name in self.list_branches()

    def create_branch(self, name: str, start_point: str = DEFAULT_BRANCH) -> None:
        """Create a new branch without switching to it.

        Args:
            name: Name of the new branch, for example ``draft/timeout``.
            start_point: The branch or commit the new branch starts from.

        Raises:
            BranchError: If a branch with this name already exists.
        """
        if self.branch_exists(name):
            raise BranchError(f"Branch '{name}' already exists")
        self._repo.create_head(name, start_point)

    def checkout(self, name: str) -> None:
        """Switch to an existing branch.

        Args:
            name: The branch to switch to.

        Raises:
            BranchError: If the branch does not exist or the repository has
                uncommitted changes.
        """
        if not self.branch_exists(name):
            raise BranchError(f"Branch '{name}' does not exist")
        if self.is_dirty():
            raise BranchError(
                "Cannot switch branches: the repository has uncommitted changes"
            )
        self._repo.heads[name].checkout()

    def merge(self, source: str, target: str, message: str) -> str:
        """Merge one branch into another, always creating a merge commit.

        Args:
            source: The branch whose changes are merged.
            target: The branch that receives the changes.
            message: The merge commit message.

        Returns:
            The SHA of the new merge commit.

        Raises:
            BranchError: If a branch does not exist or the repository has
                uncommitted changes.
        """
        if not self.branch_exists(source):
            raise BranchError(f"Branch '{source}' does not exist")
        self.checkout(target)
        self._repo.git.merge(source, "--no-ff", "-m", message)
        return self._repo.head.commit.hexsha

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
        try:
            commit = self._repo.commit(revision)
        except (BadName, BadObject, ValueError):
            raise ConfigNotFound(f"Revision '{revision}' was not found") from None
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

    def history(self, relative_path: str, revision: str = "HEAD") -> list[CommitInfo]:
        """List the commits that changed a file, newest first.

        Args:
            relative_path: Path of the file, relative to ``root``.
            revision: The branch or commit to start from.

        Returns:
            One entry per commit that changed the file. Empty if none did.
        """
        return [
            CommitInfo(
                sha=commit.hexsha,
                message=str(commit.summary),
                author=commit.author.name or "",
                date=commit.committed_datetime,
            )
            for commit in self._repo.iter_commits(revision, paths=relative_path)
        ]


def _find_enclosing_repository(path: Path) -> Path | None:
    """Return the folder of a Git repository that contains ``path``, if any."""
    resolved = path.resolve()
    for folder in (resolved, *resolved.parents):
        if (folder / ".git").exists():
            return folder
    return None
