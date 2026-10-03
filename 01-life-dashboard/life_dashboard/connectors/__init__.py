"""Data-source connectors. Importing this package registers all built-ins."""
from .base import REGISTRY, Connector, ConnectorError, build_connector, register
from . import ics, imap, outlook, tasks_file, todoist, sample  # noqa: F401  (registration side effects)

__all__ = ["REGISTRY", "Connector", "ConnectorError", "build_connector", "register"]
