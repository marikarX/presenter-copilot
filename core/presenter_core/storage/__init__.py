"""SQLite and project-vault storage for the local core."""

from .database import (
    APP_SCHEMA_VERSION,
    PROJECT_SCHEMA_VERSION,
    connect_app_database,
    connect_project_database,
    current_schema_version,
)
from .paths import AppPaths, ProjectPaths, resolve_app_data_root
from .service import StorageManager

__all__ = [
    "APP_SCHEMA_VERSION",
    "PROJECT_SCHEMA_VERSION",
    "AppPaths",
    "ProjectPaths",
    "StorageManager",
    "connect_app_database",
    "connect_project_database",
    "current_schema_version",
    "resolve_app_data_root",
]
