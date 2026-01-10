"""Thread pool helpers used across the GUI."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

WORKER_FAILED = object()


@dataclass(frozen=True)
class WorkerError:
    context: Optional[str]
    message: str
    exc_type: str
    traceback: str


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(object)


class Worker(QRunnable):
    def __init__(self, fn, *args, progress=False, context: Optional[str] = None, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.progress = progress
        self.signals = WorkerSignals()
        self.context = context

    def run(self) -> None:
        result = WORKER_FAILED
        try:
            kwargs = dict(self.kwargs)
            if self.progress:
                kwargs["progress_callback"] = self.signals.progress.emit
            result = self.fn(*self.args, **kwargs)
        except Exception as exc:
            self.signals.error.emit(
                WorkerError(
                    context=self.context,
                    message=str(exc),
                    exc_type=exc.__class__.__name__,
                    traceback=traceback.format_exc(),
                )
            )
        finally:
            self.signals.finished.emit(result)
