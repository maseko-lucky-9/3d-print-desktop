"""ProjectCard widget — one card per PrintJob, used in the home grid."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

import qtawesome as qta

from print_desktop.models.print_request import PrintJob
from print_desktop.theme import tokens as t


class ProjectCard(QFrame):
    def __init__(self, job: PrintJob, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setFixedHeight(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Top row: title + status badge
        head = QHBoxLayout()
        title = QLabel(self._title_for(job), self)
        title.setProperty("heading", True)
        title.setWordWrap(False)
        title.setMaximumWidth(180)
        head.addWidget(title, stretch=1)
        badge = QLabel(job.state.upper(), self)
        badge.setProperty("badge", True)
        badge.setStyleSheet(
            f"background-color: {t.status_color(job.state)}; color: {t.TEXT_PRIMARY};"
        )
        head.addWidget(badge)
        layout.addLayout(head)

        # Middle: thumbnail placeholder (real bytes filled in by MainWindow if available)
        thumb = QLabel(self)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setMinimumHeight(80)
        thumb.setText("")
        thumb.setPixmap(qta.icon("fa5s.cube", color=t.TEXT_DIM).pixmap(48, 48))
        layout.addWidget(thumb, stretch=1)

        # Bottom: cost + grams + hours
        cost_str = f"R {job.total_cost:.2f}" if job.total_cost is not None else "R —"
        grams_str = f"{job.slicer_grams:.1f} g" if job.slicer_grams is not None else "— g"
        hours_str = self._fmt_hours(job.slicer_seconds)
        meta = QLabel(f"{cost_str}  ·  {grams_str}  ·  {hours_str}", self)
        meta.setProperty("dim", True)
        meta.setAlignment(Qt.AlignLeft)
        layout.addWidget(meta)

    @staticmethod
    def _title_for(job: PrintJob) -> str:
        if job.notes:
            return job.notes.split("\n", 1)[0][:32]
        return f"Job #{job.id}"

    @staticmethod
    def _fmt_hours(seconds: int | None) -> str:
        if not seconds:
            return "— h"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if h else f"{m}m"
