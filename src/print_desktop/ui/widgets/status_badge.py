"""Coloured status pill for PrintJob.state."""

from PySide6.QtWidgets import QLabel

from print_desktop.theme import tokens as t


class StatusBadge(QLabel):
    def __init__(self, state: str = "sliced", parent=None):
        super().__init__(parent)
        self.setProperty("badge", True)
        self.set_state(state)

    def set_state(self, state: str) -> None:
        label = state.upper()
        color = t.status_color(state)
        self.setText(label)
        # Per-instance background; QSS handles border-radius + padding.
        self.setStyleSheet(
            f"background-color: {color}; color: {t.TEXT_PRIMARY};"
        )
