"""Theme constants and stylesheet helpers for the Qt UI."""

from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

ACCENT_COLOR = "#4DA3FF"
BACKGROUND = "#121212"
PANEL = "#1E1E1E"
SECONDARY_PANEL = "#242424"
DIVIDER = "#333333"
TEXT_PRIMARY = "#E0E0E0"
DISABLED_TEXT = "#6A6A6A"

STYLE_SHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'Roboto', sans-serif;
}}
QFrame#card {{
    background-color: {PANEL};
    border: 1px solid {DIVIDER};
    border-radius: 8px;
    padding: 12px;
}}
QPushButton {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    border: 1px solid {DIVIDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover, QPushButton:focus {{
    border-color: {ACCENT_COLOR};
}}
QPushButton[primary="true"] {{
    background-color: {ACCENT_COLOR};
    border-color: {ACCENT_COLOR};
    color: white;
}}
QPushButton[primary="true"]:hover, QPushButton[primary="true"]:focus {{
    background-color: #6BB6FF;
    border-color: #6BB6FF;
}}
QLineEdit, QComboBox, QSpinBox {{
    background-color: {SECONDARY_PANEL};
    border: 1px solid {DIVIDER};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 4px 8px;
}}
QLabel {{
    color: {TEXT_PRIMARY};
}}
"""


def apply_dark_theme(app: QApplication) -> None:
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE_SHEET)
