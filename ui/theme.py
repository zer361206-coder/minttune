import subprocess
from PyQt6.QtGui import QPalette, QColor

def get_mint_system_theme():
    theme_name = ""
    try:
        theme_name = subprocess.check_output(
            ['gsettings', 'get', 'org.cinnamon.desktop.interface', 'gtk-theme'],
            text=True, stderr=subprocess.DEVNULL
        ).strip().strip("'")
    except Exception:
        pass

    is_dark = "dark" in theme_name.lower()

    mint_accents = {
        "aqua": "#3fa3b4",
        "blue": "#417db7",
        "brown": "#997352",
        "grey": "#808080",
        "orange": "#e48a3c",
        "pink": "#e91e63",
        "purple": "#905bb6",
        "red": "#d34141",
        "sand": "#b89f5c",
        "teal": "#2ea586",
        "y": "#87ab63",
    }

    accent_color = "#87ab63"
    for name, hex_val in mint_accents.items():
        if name in theme_name.lower():
            accent_color = hex_val
            break

    return is_dark, accent_color

def apply_mint_theme(app, theme_mode="system", accent_override=""):
    app.setStyle("Fusion")
    sys_dark, sys_accent = get_mint_system_theme()

    if theme_mode == "dark":
        is_dark = True
    elif theme_mode == "light":
        is_dark = False
    else:
        is_dark = sys_dark

    accent_hex = accent_override if accent_override else sys_accent
    accent = QColor(accent_hex)
    palette = QPalette()

    if is_dark:
        window_bg = QColor(24, 24, 24)
        base_bg = QColor(36, 36, 36)
        text_color = QColor(235, 235, 235)
        button_bg = QColor(48, 48, 48)
        border_color = QColor(58, 58, 58)
    else:
        window_bg = QColor(232, 234, 237)
        base_bg = QColor(255, 255, 255)
        text_color = QColor(38, 38, 38)
        button_bg = QColor(240, 242, 245)
        border_color = QColor(212, 215, 220)

    palette.setColor(QPalette.ColorRole.Window, window_bg)
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Base, base_bg)
    palette.setColor(QPalette.ColorRole.AlternateBase, button_bg)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, button_bg)
    palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Mid, border_color)

    app.setPalette(palette)

    app.setStyleSheet("""
        QWidget {
            font-family: "Ubuntu", "Cantarell", "Noto Sans", sans-serif;
        }
        QFrame#bentoCard {
            background-color: palette(base);
            border: 1px solid palette(mid);
            border-radius: 14px;
        }
        QFrame#innerCard {
            background-color: palette(alternate-base);
            border: 1px solid palette(mid);
            border-radius: 12px;
        }
        QFrame#heroBanner {
            background-color: palette(highlight);
            border-radius: 14px;
        }
        QFrame#floatingPill {
            background-color: palette(alternate-base);
            border: 1px solid palette(mid);
            border-radius: 20px;
        }
        QPushButton#dockBtn {
            background-color: transparent;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            padding: 0px;
        }
        QPushButton#dockBtn:hover {
            background-color: palette(button);
        }
        QPushButton#dockBtnActive {
            background-color: palette(highlight);
            color: palette(highlighted-text);
            border: none;
            border-radius: 10px;
            font-size: 18px;
            padding: 0px;
        }
        /* --- TOMBOL MINIPLAYER BESAR & JELAS --- */
        QPushButton#pillBtn {
            background-color: transparent;
            color: palette(window-text);
            border: none;
            border-radius: 18px;
            font-size: 17px;
            padding: 0px;
        }
        QPushButton#pillBtn:hover {
            background-color: palette(mid);
        }
        QPushButton#pillBtnActive {
            background-color: palette(highlight);
            color: palette(highlighted-text);
            border: none;
            border-radius: 18px;
            font-size: 17px;
            padding: 0px;
        }
        QPushButton#pillPlayBtn {
            background-color: palette(highlight);
            color: palette(highlighted-text);
            border: none;
            border-radius: 21px;
            font-size: 18px;
            font-weight: bold;
            padding: 0px;
        }
        QPushButton#pillPlayBtn:hover {
            border: 2px solid palette(window-text);
        }
        QPushButton#accentCircleBtn {
            background-color: palette(highlight);
            color: palette(highlighted-text);
            border: none;
            border-radius: 22px;
            font-size: 16px;
            font-weight: bold;
            padding: 0px;
        }
        QPushButton#accentCircleBtn:hover {
            border: 2px solid palette(window-text);
        }
        QPushButton#circleBtn {
            background-color: palette(button);
            color: palette(button-text);
            border: 1px solid palette(mid);
            border-radius: 18px;
            font-size: 15px;
            padding: 0px;
        }
        QPushButton#circleBtn:hover {
            border-color: palette(highlight);
        }
        /* --- PILL TAB UNTUK SETTINGS ALA DRIBBBLE --- */
        QPushButton#tabPill {
            background-color: palette(alternate-base);
            color: palette(window-text);
            border: 1px solid palette(mid);
            border-radius: 16px;
            padding: 7px 16px;
            font-size: 13px;
            font-weight: bold;
        }
        QPushButton#tabPill:hover {
            border-color: palette(highlight);
        }
        QPushButton#tabPillActive {
            background-color: palette(window-text);
            color: palette(window);
            border: none;
            border-radius: 16px;
            padding: 7px 16px;
            font-size: 13px;
            font-weight: bold;
        }
        QLineEdit#pillSearch {
            background-color: palette(alternate-base);
            color: palette(text);
            border: 1px solid palette(mid);
            border-radius: 16px;
            padding: 6px 14px;
            font-size: 13px;
        }
        QLineEdit#pillSearch:focus {
            border: 1px solid palette(highlight);
        }
        QLineEdit {
            background-color: palette(base);
            color: palette(text);
            border: 1px solid palette(mid);
            border-radius: 8px;
            padding: 6px 10px;
        }
        QTableView {
            background-color: transparent;
            color: palette(text);
            border: none;
            gridline-color: transparent;
            selection-background-color: palette(highlight);
            selection-color: palette(highlighted-text);
            outline: none;
        }
        QTableView::item {
            padding: 6px 8px;
            border: none;
        }
        QHeaderView::section {
            background-color: transparent;
            color: palette(window-text);
            padding: 6px 8px;
            border: none;
            border-bottom: 1px solid palette(mid);
            font-weight: bold;
        }
        QListWidget {
            background-color: transparent;
            color: palette(text);
            border: none;
            outline: none;
            selection-background-color: palette(highlight);
            selection-color: palette(highlighted-text);
        }
        QListWidget::item {
            border-radius: 8px;
            padding: 5px;
        }
        QPushButton {
            background-color: palette(button);
            color: palette(button-text);
            border: 1px solid palette(mid);
            border-radius: 8px;
            padding: 6px 14px;
        }
        QPushButton:hover {
            border-color: palette(highlight);
        }
        QCheckBox {
            spacing: 10px;
            font-size: 13px;
        }
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 5px;
            border: 1px solid palette(mid);
            background-color: palette(base);
        }
        QCheckBox::indicator:checked {
            background-color: palette(highlight);
            border-color: palette(highlight);
        }
        QSlider::groove:horizontal {
            height: 4px;
            background: palette(mid);
            border-radius: 2px;
        }
        QSlider::sub-page:horizontal {
            background: palette(highlight);
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: palette(highlight);
            width: 12px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 6px;
        }
        QScrollArea {
            background: transparent;
            border: none;
        }
        QScrollBar:vertical {
            width: 6px;
            background: transparent;
        }
        QScrollBar::handle:vertical {
            background: palette(mid);
            border-radius: 3px;
        }
    """)
