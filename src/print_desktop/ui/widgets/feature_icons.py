"""Circular feature-icon row — three live icons only.

Per plan §17 K1: dropped the "Coming soon" feature icons that ReelSmith uses
for marketing — this is a personal tool, no aspirational signaling needed.
The three live icons map to actual user actions.
"""

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from print_desktop.theme import tokens as t

FEATURES = [
    ("MakerWorld", "fa5s.cloud-download-alt", "makerworld"),
    ("Print history", "fa5s.history", "history"),
    ("Send to printer", "fa5s.print", "send_to_printer"),
]


class FeatureIcons(QWidget):
    """Emits action_requested(str) with the slug of the activated feature."""

    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setSpacing(24)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        for label, icon_name, slug in FEATURES:
            cell = QVBoxLayout()
            cell.setSpacing(6)

            btn = QPushButton(self)
            btn.setProperty("feature", True)
            btn.setIcon(qta.icon(icon_name, color=t.TEXT_PRIMARY))
            btn.setIconSize(btn.size())
            btn.setCursor(self.cursor())
            btn.clicked.connect(lambda _checked=False, s=slug: self.action_requested.emit(s))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

            text = QLabel(label, self)
            text.setProperty("dim", True)
            text.setMaximumWidth(80)
            text.setWordWrap(True)
            text.setAlignment(Qt.AlignCenter)

            cell.addWidget(btn, alignment=Qt.AlignCenter)
            cell.addWidget(text, alignment=Qt.AlignCenter)
            holder = QWidget(self)
            holder.setLayout(cell)
            layout.addWidget(holder)
        layout.addStretch(1)
