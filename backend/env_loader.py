"""
Environment loading.

The project previously had a `.env` file that the application never read,
because `python-dotenv` was not installed and nothing called `load_dotenv()`.
That made `FLASK_DEBUG`, `FLASK_HOST` and friends behave unexpectedly.

This module loads `.env` reliably:

  * `python-dotenv` is used when installed (it handles quoting/escaping best).
  * Otherwise a small built-in parser handles the common `KEY=VALUE` format.

Existing environment variables always win, so a real deployment can override
the file without editing it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

_loaded = False


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip a single layer of matching quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            # Drop a trailing inline comment for unquoted values.
            if " #" in value:
                value = value.split(" #", 1)[0].rstrip()
        if key:
            values[key] = value
    return values


def load_env(path: Optional[os.PathLike | str] = None, override: bool = False) -> bool:
    """
    Load `.env` into ``os.environ``. Returns True when a file was read.

    Never raises: a malformed or missing `.env` must not stop the app from
    starting, it just means no additional variables were provided.
    """
    global _loaded
    env_path = Path(path) if path else DEFAULT_ENV_FILE

    if not env_path.exists():
        return False

    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path=str(env_path), override=override)
        _loaded = True
        return True
    except ImportError:
        pass

    try:
        for key, value in _parse_env_file(env_path).items():
            if override or key not in os.environ:
                os.environ[key] = value
        _loaded = True
        return True
    except OSError:
        return False


def is_loaded() -> bool:
    return _loaded


def env(name: str, default: str = "", *, strip: bool = True) -> str:
    """Read an environment variable, optionally trimming whitespace."""
    value = os.environ.get(name, default)
    if value is None:
        return default
    return value.strip() if strip else value


def env_bool(name: str, default: bool = False) -> bool:
    raw = env(name)
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name) or default)
    except (TypeError, ValueError):
        return default
