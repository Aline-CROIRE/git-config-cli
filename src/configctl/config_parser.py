"""Read, write, and validate JSON and YAML configuration files."""

import json
from pathlib import Path, PurePath
from typing import Any

import yaml

from configctl.exceptions import (
    ConfigNotFound,
    InvalidConfigError,
    UnsupportedFormatError,
)

ConfigData = dict[str, Any]
"""A parsed configuration: string keys mapped to any JSON or YAML value."""

_FORMATS: dict[str, str] = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}


class ConfigParser:
    """Convert configuration files between text and Python dictionaries.

    The format (JSON or YAML) is chosen from the file extension. This class
    knows nothing about Git; it only handles file content.
    """

    def parse(self, content: str, filename: str) -> ConfigData:
        """Parse configuration text into a dictionary.

        Args:
            content: The raw text of the configuration file.
            filename: The file name, used to choose the format.

        Returns:
            The parsed configuration.

        Raises:
            UnsupportedFormatError: If the file extension is not supported.
            InvalidConfigError: If the content is invalid or not a mapping.
        """
        file_format = self._detect_format(filename)
        try:
            if file_format == "json":
                data = json.loads(content)
            else:
                data = yaml.safe_load(content)
        except (json.JSONDecodeError, yaml.YAMLError) as error:
            raise InvalidConfigError(
                f"Invalid {file_format.upper()} in '{filename}': {error}"
            ) from error

        if not isinstance(data, dict):
            raise InvalidConfigError(
                f"'{filename}' must contain a mapping of keys to values."
            )
        return data

    def serialize(self, data: ConfigData, filename: str) -> str:
        """Convert a dictionary into configuration text.

        Keys are sorted so the same data always produces the same text,
        which keeps Git diffs small and predictable.

        Args:
            data: The configuration to convert.
            filename: The file name, used to choose the format.

        Returns:
            The configuration as text, ending with a newline.

        Raises:
            UnsupportedFormatError: If the file extension is not supported.
        """
        file_format = self._detect_format(filename)
        if file_format == "json":
            return json.dumps(data, indent=2, sort_keys=True) + "\n"
        text: str = yaml.safe_dump(data, sort_keys=True, default_flow_style=False)
        return text

    def read(self, path: Path) -> ConfigData:
        """Read and parse a configuration file from disk.

        Args:
            path: Path to the configuration file.

        Returns:
            The parsed configuration.

        Raises:
            ConfigNotFound: If the file does not exist.
            UnsupportedFormatError: If the file extension is not supported.
            InvalidConfigError: If the content is invalid or not a mapping.
        """
        if not path.is_file():
            raise ConfigNotFound(f"Configuration file not found: {path}")
        return self.parse(path.read_text(encoding="utf-8"), path.name)

    def write(self, path: Path, data: ConfigData) -> None:
        """Serialize a configuration and save it to disk.

        Args:
            path: Destination path for the configuration file.
            data: The configuration to save.

        Raises:
            UnsupportedFormatError: If the file extension is not supported.
        """
        content = self.serialize(data, path.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    @staticmethod
    def _detect_format(filename: str) -> str:
        """Return "json" or "yaml" based on the file extension."""
        suffix = PurePath(filename).suffix.lower()
        try:
            return _FORMATS[suffix]
        except KeyError:
            supported = ", ".join(_FORMATS)
            raise UnsupportedFormatError(
                f"Unsupported file type '{suffix}' for '{filename}'. "
                f"Supported: {supported}"
            ) from None
