"""App-wide theme: Fusion palette + QSS for inputs/buttons/scrollbars/sidebar, in dark, light or following the system."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

THEME_MODES = ("system", "light", "dark")
DEFAULT_THEME_MODE = "dark"


@dataclass(frozen=True)
class ThemeColors:
    window: str
    base: str
    text: str
    accent: str
    button_bg: str
    button_hover: str
    button_pressed: str
    button_text: str
    disabled_text: str
    muted: str
    link: str
    placeholder: str
    input_bg: str
    border: str
    disabled_button: str
    scrollbar: str
    sidebar_bg: str
    sidebar_title: str
    sidebar_text: str
    sidebar_hover: str
    sidebar_selected: str
    sidebar_selected_text: str


DARK = ThemeColors(
    window="#1b1c21", base="#24252b", text="#e6e6e6", accent="#2d6cdf", button_bg="#2d6cdf", button_hover="#3a7bf0",
    button_pressed="#2458b8", button_text="#ffffff", disabled_text="#6b6c75", muted="#9a9ba5", link="#4da3ff",
    placeholder="#f0f0f0", input_bg="#2b2c34", border="#3a3b44", disabled_button="#3a3b44", scrollbar="#3a3b44",
    sidebar_bg="#24252b", sidebar_title="#ffffff", sidebar_text="#c7c7d1", sidebar_hover="#2c2d35",
    sidebar_selected="#35363f", sidebar_selected_text="#e2a63c",
)
LIGHT = ThemeColors(
    window="#f4f5f7", base="#ffffff", text="#1f2328", accent="#2d6cdf", button_bg="#e1e4ea", button_hover="#d2d7e0",
    button_pressed="#c3c9d5", button_text="#1f2328", disabled_text="#8b8f98", muted="#5f636c", link="#0b5fd1",
    placeholder="#6b6f78", input_bg="#ffffff", border="#c9ccd3", disabled_button="#d5d8de", scrollbar="#b8bcc6",
    sidebar_bg="#e8eaee", sidebar_title="#1f2328", sidebar_text="#3b3f48", sidebar_hover="#dcdfe5",
    sidebar_selected="#cfd5e0", sidebar_selected_text="#b9770e",
)

_STYLESHEET = """
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
    background-color: {input_bg};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 6px;
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox QAbstractItemView {{
    background-color: {input_bg}; color: {text}; border: 1px solid {border};
    selection-background-color: {accent}; selection-color: white; outline: none;
}}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 2px 6px; color: {text}; }}
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{
    background-color: {accent}; color: white;
}}
QLabel[muted="true"] {{ color: {muted}; }}
QPushButton {{
    background-color: {button_bg};
    color: {button_text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background-color: {button_hover}; }}
QPushButton:pressed {{ background-color: {button_pressed}; }}
QPushButton[checkable="true"] {{
    background-color: {sidebar_bg}; color: {sidebar_text}; border-color: {border};
}}
QPushButton[checkable="true"]:hover:!checked {{ background-color: {sidebar_hover}; }}
QPushButton[checkable="true"]:checked, QPushButton[checkable="true"]:checked:hover {{
    background-color: {accent}; color: white; border-color: {accent};
    border-bottom-color: {link}; font-weight: 600;
}}
QPushButton:disabled {{ background-color: {disabled_button}; color: {disabled_text}; }}
QPushButton[checkable="true"]:disabled, QPushButton[checkable="true"]:disabled:hover {{
    background-color: {disabled_button}; color: {disabled_text}; border-color: {border};
}}
QTabBar::tab {{
    background-color: {sidebar_bg}; color: {sidebar_text};
    border: 1px solid {border}; padding: 5px 11px;
}}
QTabBar::tab:hover:!selected {{ background-color: {sidebar_hover}; }}
QTabBar::tab:selected, QTabBar::tab:selected:hover {{
    background-color: {accent}; color: white; border-color: {accent}; border-bottom-color: {link};
}}
QTabBar::tab:disabled {{ background-color: {disabled_button}; color: {disabled_text}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {scrollbar}; border-radius: 5px; min-height: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
#Sidebar {{ background-color: {sidebar_bg}; }}
#sidebarTitle {{ color: {sidebar_title}; font-size: 15px; font-weight: 600; }}
#toggleButton {{
    background: transparent; border: none; color: {sidebar_text};
    padding: 0; margin: 0; border-radius: 4px;
}}
#toggleButton:hover {{ color: {sidebar_title}; background-color: {sidebar_hover}; }}
#sidebarList {{ background-color: transparent; border: none; outline: none; font-size: 13px; color: {sidebar_text}; }}
#sidebarList::item {{
    height: 36px; border-radius: 6px; margin: 2px 8px; padding-left: 4px;
    background-color: {sidebar_bg}; color: {sidebar_text}; border-left: 2px solid {sidebar_bg};
}}
#sidebarList::item:selected {{
    background-color: {accent}; color: white; border-left-color: {link};
}}
#sidebarList::item:hover:!selected {{ background-color: {sidebar_hover}; }}
"""

_MODE_PROPERTY = "autohubThemeMode"


def set_muted(label: QWidget, muted: bool) -> None:
    """Dim (or restore) a label with the theme's muted colour."""
    label.setProperty("muted", muted)
    label.style().unpolish(label)
    label.style().polish(label)


def normalize_theme_mode(value) -> str:
    return value if value in THEME_MODES else DEFAULT_THEME_MODE


def is_dark(mode: str, system_is_dark: bool) -> bool:
    mode = normalize_theme_mode(mode)
    return system_is_dark if mode == "system" else mode == "dark"


def _system_is_dark(app: QApplication) -> bool:
    return app.styleHints().colorScheme() != Qt.ColorScheme.Light


def apply_theme(app: QApplication, mode: str = DEFAULT_THEME_MODE) -> bool:
    """Applies the theme and returns True when it is dark. "system" follows the OS, also when it changes later."""
    mode = normalize_theme_mode(mode)
    first_time = app.property(_MODE_PROPERTY) is None
    app.setProperty(_MODE_PROPERTY, mode)
    if first_time:
        app.styleHints().colorSchemeChanged.connect(
            lambda *_: apply_theme(app, app.property(_MODE_PROPERTY)) if app.property(_MODE_PROPERTY) == "system" else None
        )
    dark = is_dark(mode, _system_is_dark(app))
    colors = DARK if dark else LIGHT

    app.setStyle("Fusion")
    palette = QPalette()
    window, base, text, accent = (QColor(c) for c in (colors.window, colors.base, colors.text, colors.accent))
    disabled = QColor(colors.disabled_text)
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, window)
    palette.setColor(QPalette.ToolTipBase, base)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, base)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Link, accent)
    palette.setColor(QPalette.Highlight, accent)
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text, disabled)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, disabled)
    palette.setColor(QPalette.Link, QColor(colors.link))
    palette.setColor(QPalette.PlaceholderText, QColor(colors.placeholder))
    app.setPalette(palette)
    app.setStyleSheet(_STYLESHEET.format(**vars(colors)))

    for widget in app.topLevelWidgets():
        if widget.isWindow() and widget.isVisible():
            set_dark_titlebar(widget, dark)
    return dark


def set_dark_titlebar(window: QWidget, dark: bool = True) -> None:
    """Switch the native Windows title bar to dark or light via DWM (Windows 10 1809+/11)."""
    if sys.platform != "win32":
        return

    import ctypes
    from ctypes import wintypes

    hwnd = wintypes.HWND(int(window.winId()))
    value = ctypes.c_int(1 if dark else 0)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on recent builds, 19 on early 1809
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, wintypes.DWORD(attribute), ctypes.byref(value), ctypes.sizeof(value)
        ) == 0:
            break
