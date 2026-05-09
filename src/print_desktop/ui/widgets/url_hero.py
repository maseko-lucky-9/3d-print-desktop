"""URL hero widget: rotating placeholder + Calculate CTA + MakerWorld URL field.

Translated from ReelSmith's `routes/index.tsx:84-130` hero section
(see plan §7.5 element-mapping table) — 3D-printing variant.
"""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import qtawesome as qta

PLACEHOLDERS = [
    "Drop a MakerWorld link…",
    "Drop a Thingiverse link… (coming soon)",
    "Drop a Printables link… (coming soon)",
    "Or fill the form below ↓",
]


class UrlHero(QWidget):
    """Hero with URL field, rotating placeholder, and primary CTA.

    Emits:
      url_submitted(str): user pressed Calculate / Enter with a URL in the field.
      calculate_requested(): user pressed the primary Calculate CTA without a URL
                              (use form values from the manual-entry form below).
    """

    url_submitted = Signal(str)
    calculate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._placeholder_idx = 0
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._cycle_placeholder)
        self._timer.start(3000)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText(PLACEHOLDERS[0])
        self.url_input.setMinimumHeight(48)
        self.url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.url_input.returnPressed.connect(self._on_submit)
        # Link-icon prefix
        link_icon: QIcon = qta.icon("fa5s.link", color="#A1A1AA")
        self.url_input.addAction(link_icon, QLineEdit.LeadingPosition)
        layout.addWidget(self.url_input)

        cta = QPushButton("Calculate cost", self)
        cta.setProperty("primary", True)
        cta.setMinimumHeight(44)
        cta.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cta.clicked.connect(self._on_submit)
        layout.addWidget(cta)
        # Re-polish so the [primary="true"] QSS rule applies after dynamic property set
        cta.style().unpolish(cta)
        cta.style().polish(cta)

    def _cycle_placeholder(self) -> None:
        if self.url_input.hasFocus():
            return
        self._placeholder_idx = (self._placeholder_idx + 1) % len(PLACEHOLDERS)
        self.url_input.setPlaceholderText(PLACEHOLDERS[self._placeholder_idx])

    def _on_submit(self) -> None:
        url = self.url_input.text().strip()
        if url:
            self.url_submitted.emit(url)
        else:
            self.calculate_requested.emit()
