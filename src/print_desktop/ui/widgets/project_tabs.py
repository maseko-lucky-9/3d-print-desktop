"""Project tabs strip — 'All projects (Printed)' + 'Projects (Calculated)'.

Per user spec: rename of ReelSmith's 'All projects'/'Saved' tabs.
- All projects (Printed): jobs in printing/done/failed/cancelled (i.e., ever sent).
- Projects (Calculated): jobs in 'sliced' (cost-attributed but not yet sent).

Counters update as the job list changes.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from print_desktop.models.print_request import PrintJob

PRINTED_STATES = {"printing", "done", "failed", "cancelled", "queued"}
CALCULATED_STATES = {"sliced"}


class ProjectTabs(QWidget):
    """Emits tab_changed(str) with 'printed' or 'calculated' when user clicks."""

    tab_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._printed_btn = self._make_tab("All projects (Printed)", "printed", active=True)
        self._calculated_btn = self._make_tab("Projects (Calculated)", "calculated")
        layout.addWidget(self._printed_btn)
        layout.addWidget(self._calculated_btn)
        layout.addStretch(1)

        self._active = "printed"

    def _make_tab(self, label: str, slug: str, active: bool = False) -> QPushButton:
        b = QPushButton(label, self)
        b.setProperty("tab", True)
        b.setProperty("active", active)
        b.setFlat(True)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        b.setCursor(self.cursor())
        b.clicked.connect(lambda _checked=False, s=slug: self._on_click(s))
        b.style().unpolish(b)
        b.style().polish(b)
        return b

    def _on_click(self, slug: str) -> None:
        if slug == self._active:
            return
        self._active = slug
        for btn, s in [(self._printed_btn, "printed"), (self._calculated_btn, "calculated")]:
            btn.setProperty("active", s == slug)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.tab_changed.emit(slug)

    def update_counts(self, jobs: list[PrintJob]) -> None:
        printed = sum(1 for j in jobs if j.state in PRINTED_STATES)
        calculated = sum(1 for j in jobs if j.state in CALCULATED_STATES)
        self._printed_btn.setText(f"All projects (Printed) ({printed})")
        self._calculated_btn.setText(f"Projects (Calculated) ({calculated})")

    @property
    def active_tab(self) -> str:
        return self._active

    @staticmethod
    def jobs_for_tab(slug: str, jobs: list[PrintJob]) -> list[PrintJob]:
        states = PRINTED_STATES if slug == "printed" else CALCULATED_STATES
        return [j for j in jobs if j.state in states]
