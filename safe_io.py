"""Safer file and directory write helpers for data-maintenance scripts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import shutil


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_path(path: Path) -> Path:
    path = Path(path)
    return path.with_name(f"{path.name}.bak_{timestamp()}")


def backup_file(path: Path) -> Path | None:
    path = Path(path)
    if not path.exists():
        return None
    target = backup_path(path)
    shutil.copy2(path, target)
    return target


def backup_directory(path: Path) -> Path | None:
    path = Path(path)
    if not path.exists():
        return None
    target = backup_path(path)
    shutil.move(str(path), str(target))
    return target


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> Path | None:
    """Back up an existing file, then atomically replace it with text."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_file(path)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)
    return backup
