"""Structured (JSON Lines) logging for configctl's audit trail."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

LOGGER_NAME = "configctl"
_STANDARD_FIELDS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def default_log_file() -> Path:
    """Return the default audit log location: ``~/.configctl/audit.log``."""
    return Path.home() / ".configctl" / "audit.log"


class JsonFormatter(logging.Formatter):
    """Format each log record as one line of JSON.

    Fields passed with ``extra=`` (for example ``action`` or ``draft``) are
    added to the JSON object, so the log can be searched and filtered.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a single-line JSON string."""
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_FIELDS:
                entry[key] = value
        return json.dumps(entry, default=str)


def configure_logging(log_file: Path, verbose: bool = False) -> None:
    """Send configctl's log records to an audit file, and optionally the terminal.

    Calling this again replaces the previous handlers instead of adding more.

    Args:
        log_file: JSON Lines file that receives every INFO and higher record.
        verbose: Also print DEBUG and higher records to the terminal.
    """
    reset_logging()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    if verbose:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(console)


def reset_logging() -> None:
    """Remove and close every handler attached to configctl's logger."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
