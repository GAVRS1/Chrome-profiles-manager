"""Тёмная тема оформления (QSS) для всего приложения."""

ACCENT = "#4f8cff"
ACCENT_HOVER = "#6ba1ff"
ACCENT_PRESSED = "#3d74db"
BG = "#1e2126"
BG_PANEL = "#262a31"
BG_INPUT = "#2d323b"
BORDER = "#3a404b"
TEXT = "#e8eaed"
TEXT_DIM = "#9aa0a6"
GREEN = "#34c759"
RED = "#ff5f57"

APP_STYLE = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 13px;
}}

QMainWindow, QStatusBar {{
    background: {BG};
}}
QStatusBar {{
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 8px 20px;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-bottom-color: {BG_PANEL};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}

QListWidget {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 7px 10px;
    border-radius: 4px;
    margin: 1px 2px;
}}
QListWidget::item:hover {{
    background: {BG_INPUT};
}}
QListWidget::item:selected {{
    background: rgba(79, 140, 255, 0.25);
    color: {TEXT};
}}

QPushButton {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: #363c47;
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: {BG_PANEL};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    background: {BG_PANEL};
    border-color: {BORDER};
}}
QPushButton[accent="true"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton[accent="true"]:pressed {{
    background: {ACCENT_PRESSED};
}}
QPushButton[danger="true"]:hover {{
    background: {RED};
    border-color: {RED};
    color: white;
}}

QLineEdit, QSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled {{
    color: {TEXT_DIM};
    background: {BG_PANEL};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {BG_PANEL};
    border: none;
    width: 16px;
}}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {TEXT_DIM};
}}

QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}

QLabel[hint="true"] {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QLabel[sectionTitle="true"] {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QMessageBox {{
    background: {BG_PANEL};
}}
QToolTip {{
    background: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 8px;
}}
"""
