"""QSS stylesheet generation. Tokens substituted from theme.tokens — keeps
the design system in Python so we can compute derivatives at runtime."""

from print_desktop.theme import tokens as t


def stylesheet() -> str:
    return f"""
    QWidget {{
        background-color: {t.BG_PAGE};
        color: {t.TEXT_PRIMARY};
        font-family: {t.FONT_FAMILY};
        font-size: {t.FONT_SIZE_BODY}px;
    }}

    QMainWindow, QDialog {{
        background-color: {t.BG_PAGE};
    }}

    /* Inputs */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background-color: {t.BG_CARD};
        border: 1px solid {t.BORDER_SUBTLE};
        border-radius: {t.RADIUS_INPUT}px;
        padding: 10px 14px;
        color: {t.TEXT_PRIMARY};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
    QPlainTextEdit:focus, QTextEdit:focus {{
        border-color: {t.BORDER_FOCUS};
    }}
    QLineEdit::placeholder {{
        color: {t.TEXT_MUTED};
    }}

    /* Combobox dropdown */
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {t.BG_CARD};
        border: 1px solid {t.BORDER_SUBTLE};
        selection-background-color: {t.BG_CARD_RAISED};
        color: {t.TEXT_PRIMARY};
    }}

    /* Buttons */
    QPushButton {{
        background-color: {t.BG_CARD};
        border: 1px solid {t.BORDER_SUBTLE};
        border-radius: {t.RADIUS_BUTTON}px;
        padding: 8px 16px;
        color: {t.TEXT_PRIMARY};
    }}
    QPushButton:hover {{
        background-color: {t.BG_CARD_RAISED};
    }}
    QPushButton:disabled {{
        opacity: 0.4;
        color: {t.TEXT_DIM};
    }}
    QPushButton[primary="true"] {{
        background-color: {t.CTA_BG};
        color: {t.CTA_FG};
        border: none;
        font-weight: 600;
        padding: 12px 16px;
    }}
    QPushButton[primary="true"]:hover {{
        background-color: {t.CTA_HOVER};
    }}

    /* Tab strip (project tabs) */
    QPushButton[tab="true"] {{
        background-color: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        border-radius: 0;
        color: {t.TEXT_MUTED};
        padding: 4px 0 6px 0;
        margin-right: 16px;
        font-weight: 500;
    }}
    QPushButton[tab="true"]:hover {{
        color: {t.TEXT_PRIMARY};
    }}
    QPushButton[tab="true"][active="true"] {{
        color: {t.TEXT_PRIMARY};
        border-bottom-color: {t.TEXT_PRIMARY};
    }}

    /* Project card */
    QFrame[card="true"] {{
        background-color: {t.BG_CARD};
        border: 1px solid {t.BORDER_SUBTLE};
        border-radius: {t.RADIUS_CARD}px;
    }}
    QFrame[card="true"]:hover {{
        background-color: {t.BG_CARD_RAISED};
    }}

    /* Feature icon button (round) */
    QPushButton[feature="true"] {{
        background-color: {t.ICON_CIRCLE_BG};
        border: none;
        border-radius: 32px;
        min-width: 64px;
        max-width: 64px;
        min-height: 64px;
        max-height: 64px;
    }}
    QPushButton[feature="true"]:hover {{
        background-color: {t.ICON_CIRCLE_HOVER};
    }}

    /* Status badges */
    QLabel[badge="true"] {{
        padding: 2px 8px;
        border-radius: 10px;
        font-size: {t.FONT_SIZE_CAPTION}px;
        font-weight: 600;
    }}

    /* Captions */
    QLabel[muted="true"] {{
        color: {t.TEXT_MUTED};
    }}
    QLabel[error="true"] {{
        color: {t.STATUS_FAILED};
        font-weight: 600;
    }}
    QLabel[warning="true"] {{
        color: {t.STATUS_WARNING};
        font-weight: 600;
    }}
    QLabel[dim="true"] {{
        color: {t.TEXT_DIM};
        font-size: {t.FONT_SIZE_CAPTION}px;
    }}
    QLabel[heading="true"] {{
        font-size: {t.FONT_SIZE_HEADING}px;
        font-weight: 600;
    }}

    /* Watermark — ReelSmith analogue (kept optional; main_window decides
       whether to instantiate). */
    QLabel[watermark="true"] {{
        color: rgba(255, 255, 255, 0.04);
        font-weight: 700;
    }}

    /* Scrollbars — minimal */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {t.BG_CARD_RAISED};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
