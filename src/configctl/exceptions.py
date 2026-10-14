"""Custom exceptions raised by configctl."""

from collections.abc import Sequence


class ConfigCtlError(Exception):
    """Base class for all errors raised by configctl."""


# The lab requires this exact name, so we allow it to skip the "Error" suffix rule.
class ConfigNotFound(ConfigCtlError):  # noqa: N818
    """Raised when a requested configuration file does not exist."""


class InvalidRepoError(ConfigCtlError):
    """Raised when a path is not a valid configuration repository."""


class MergeConflictError(ConfigCtlError):
    """Raised when publishing a draft causes a merge conflict.

    Attributes:
        branch: The draft branch that could not be merged.
        conflicted_files: Paths of the files that contain conflicts.
    """

    def __init__(self, branch: str, conflicted_files: Sequence[str]) -> None:
        """Initialise the error with the branch and the conflicting files.

        Args:
            branch: The draft branch that could not be merged.
            conflicted_files: Paths of the files that contain conflicts.
        """
        self.branch = branch
        self.conflicted_files = list(conflicted_files)
        files = ", ".join(self.conflicted_files)
        super().__init__(f"Merge conflict while publishing '{branch}' in: {files}")
