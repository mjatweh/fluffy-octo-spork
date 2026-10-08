"""Connector interface + registry.

A connector turns one external source into normalized model objects. To add a
new one, subclass :class:`Connector`, set ``type`` (the TOML ``type =`` value)
and ``kind`` (``calendar`` / ``email`` / ``tasks``), implement ``fetch`` and
decorate the class with ``@register``.
"""
from __future__ import annotations

import os
import urllib.request
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar

from .. import tls

if TYPE_CHECKING:
    from ..config import Config
    from ..models import Email, Event, Task

REGISTRY: dict[str, type["Connector"]] = {}


class ConnectorError(RuntimeError):
    """Raised for configuration or fetch problems (shown in the status panel)."""


class Connector(ABC):
    type: ClassVar[str]
    kind: ClassVar[str]  # "calendar" | "email" | "tasks"

    def __init__(self, options: dict[str, Any], config: "Config"):
        self.options = options
        self.config = config
        self.name = options.get("name") or self.type

    @abstractmethod
    def fetch(self, day: date) -> list["Event | Email | Task"]:
        """Return items relevant to ``day`` (already normalized)."""

    # -- helpers ---------------------------------------------------------
    def option(self, key: str, default: Any = None, required: bool = False) -> Any:
        value = self.options.get(key, default)
        if required and value in (None, ""):
            raise ConnectorError(f"{self.name}: missing required option '{key}'")
        return value

    def secret(self, key: str) -> str:
        """Read a secret from the env var named by option ``<key>_env``."""
        env_name = self.option(f"{key}_env", required=True)
        value = os.environ.get(env_name, "")
        if not value:
            raise ConnectorError(f"{self.name}: environment variable {env_name} is not set")
        return value

    def read_text(self, source: str, timeout: float = 20) -> str:
        """Read a local path or http(s) URL (webcal:// is treated as https://)."""
        if source.startswith("webcal://"):
            source = "https://" + source[len("webcal://"):]
        if source.startswith(("http://", "https://")):
            req = urllib.request.Request(source, headers={"User-Agent": "life-dashboard/1.0"})
            with urllib.request.urlopen(req, timeout=timeout, context=tls.context()) as resp:
                return resp.read().decode("utf-8", errors="replace")
        path = self.config.resolve(source)
        if not path.is_file():
            raise ConnectorError(f"{self.name}: file not found: {path}")
        return path.read_text(encoding="utf-8")


def register(cls: type[Connector]) -> type[Connector]:
    REGISTRY[cls.type] = cls
    return cls


def build_connector(options: dict[str, Any], config: "Config") -> Connector:
    ctype = options.get("type", "")
    if ctype not in REGISTRY:
        raise ConnectorError(f"Unknown connector type '{ctype}'. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[ctype](options, config)
