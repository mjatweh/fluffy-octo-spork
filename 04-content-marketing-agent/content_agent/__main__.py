import os
import sys
from pathlib import Path

from .cli import main


def _load_dotenv(path: Path) -> None:
    """Minimal .env support (KEY=VALUE lines); real environment variables win."""
    if path.is_file():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#") and value.strip():
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(Path.cwd() / ".env")
sys.exit(main())
