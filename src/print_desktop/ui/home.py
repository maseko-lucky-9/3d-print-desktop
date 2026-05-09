"""Home view — composes hero + features + manual form + projects grid.

Layout follows ReelSmith landing pattern (plan §7.5) translated for Option E:
- Hero (URL field + Calculate CTA)
- Feature icons row (3 live, no Coming-soon dead UI per §17 K1)
- Manual form + live cost panel
- Project tabs + grid
"""

import logging
from typing import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from print_desktop.models.print_request import FilamentSku, JobPayload, PrintJob
from print_desktop.storage.settings import Settings
from print_desktop.ui.widgets.feature_icons import FeatureIcons
from print_desktop.ui.widgets.manual_form import ManualForm
from print_desktop.ui.widgets.project_card import ProjectCard
from print_desktop.ui.widgets.project_tabs import ProjectTabs
from print_desktop.ui.widgets.url_hero import UrlHero

log = logging.getLogger(__name__)


class HomeView(QWidget):
    """Top-level home view. Connects via callbacks rather than coupling to
    the API client directly — MainWindow wires the async calls."""

    submit_job = Signal(object, bool)  # JobPayload, send_to_printer
    import_makerworld_url = Signal(str)
    feature_clicked = Signal(str)  # slug from FeatureIcons

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._jobs: list[PrintJob] = []
        self._build_ui(settings)

    def _build_ui(self, settings: Settings) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(32)

        # Hero
        self.hero = UrlHero(content)
        self.hero.url_submitted.connect(self.import_makerworld_url.emit)
        layout.addWidget(self.hero)

        # Feature icons
        self.features = FeatureIcons(content)
        self.features.action_requested.connect(self.feature_clicked.emit)
        layout.addWidget(self.features)

        # Manual form + cost panel
        self.form = ManualForm(settings, content)
        self.form.payload_ready.connect(lambda payload: self.submit_job.emit(payload, True))
        layout.addWidget(self.form)

        # Project tabs + grid
        self.tabs = ProjectTabs(content)
        self.tabs.tab_changed.connect(self._render_grid)
        layout.addWidget(self.tabs)

        grid_holder = QWidget(content)
        self._grid_layout = QGridLayout(grid_holder)
        self._grid_layout.setSpacing(16)
        layout.addWidget(grid_holder, stretch=1)

        scroll_layout = QVBoxLayout(self)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(content)
        scroll_layout.addWidget(scroll)

    # ── Public API (called by MainWindow) ──────────────────────────────────

    def set_skus(self, skus: list[FilamentSku]) -> None:
        self.form.set_skus(skus)

    def set_jobs(self, jobs: list[PrintJob]) -> None:
        self._jobs = jobs
        self.tabs.update_counts(jobs)
        self._render_grid(self.tabs.active_tab)

    # ── Internals ─────────────────────────────────────────────────────────

    def _render_grid(self, tab_slug: str) -> None:
        # Clear existing cards
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        items = ProjectTabs.jobs_for_tab(tab_slug, self._jobs)
        if not items:
            empty = QLabel("No projects yet. Fill the form above and hit Calculate cost.", self)
            empty.setProperty("muted", True)
            self._grid_layout.addWidget(empty, 0, 0)
            return

        # 3 columns
        for idx, job in enumerate(items):
            card = ProjectCard(job)
            row, col = divmod(idx, 3)
            self._grid_layout.addWidget(card, row, col)
