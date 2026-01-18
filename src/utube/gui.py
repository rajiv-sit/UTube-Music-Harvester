"""PyQt6 GUI entry points and re-exports for tests."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

from .ui import main as _main
from .ui.main import UTubeGui, run_gui
from .ui.models import TrackFilterProxyModel, TrackTableModel
from .ui.views.library import LibraryView
from .ui.workers import Worker, WorkerError

_main.shutil = shutil
_main.socket = socket
_main.Path = Path

__all__ = [
    "LibraryView",
    "TrackFilterProxyModel",
    "TrackTableModel",
    "UTubeGui",
    "Worker",
    "WorkerError",
    "run_gui",
]

if __name__ == "__main__":
    run_gui()
