"""Every PrintJob attribute the UI reads must actually be declared on the model.

This file exists because `ProjectCard._title_for` read `job.notes` while
`PrintJob` never declared a `notes` field. pydantic v2 defaults to
`extra="ignore"`, so the backend's `notes` value was parsed, silently dropped,
and then every attribute access raised
`AttributeError: 'PrintJob' object has no attribute 'notes'`.

That is worse than it sounds: ProjectCard is the home grid, so the exception
fired on the *first* card and aborted `HomeView._render_grid` for all of them.
The app opened to a permanently empty Projects view, with the traceback going
only to ~/Library/Logs/PrintDesktop/print-desktop.log via a
"Task exception was never retrieved" warning — no UI error state at all.

Nothing caught it because no test ever instantiated a card or called
`_title_for`, and the model was never checked against a real backend payload.
Hence three layers: a verbatim backend row (the only kind of fixture that can
catch drift — see tests/test_filament_sku_contract.py, which established this
convention for the same reason), a real `_render_grid` pass over that row, and
a cheap AST heuristic for undeclared field reads.
"""

import ast
from pathlib import Path

from pydantic import BaseModel
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from print_desktop.models.print_request import PrintJob
from print_desktop.ui.home import HomeView
from print_desktop.ui.widgets.project_card import ProjectCard

SRC = Path(__file__).resolve().parent.parent / "src" / "print_desktop"

# Verbatim from GET /api/jobs against the deployed backend. Copied from a real
# response, never written from the model: a fixture derived from PrintJob agrees
# with PrintJob by construction and cannot catch the backend renaming, dropping,
# or nulling a field the app requires. `ApiClient.list_jobs` runs
# `PrintJob.model_validate` over every row, so one drifted required field raises,
# `_refresh_async`'s broad `except Exception` swallows it into a self-clearing
# 6-second status-bar message, and the grid stays empty — the same silent shape
# as the bug this file is named for.
BACKEND_JOB = {
    "id": 2,
    "model_id": None,
    "filament_sku_id": 1,
    "printer_id": 1,
    "state": "sliced",
    "sliced_path": None,
    "slicer_grams": 100.0,
    "slicer_seconds": 7200,
    "bambu_task_id": None,
    "error_message": None,
    "created_at": "2026-08-11T14:20:13.631019+00:00",
    "started_at": None,
    "finished_at": None,
    "filament_size": None,
    "filament_price": 2.0,
    "electricity_rate": None,
    "power_watts": 200.0,
    "printer_hourly_cost": None,
    "profit_margin_pct": None,
    "filament_cost": 200.0,
    "electricity_cost": 1.14,
    "printer_usage_cost": 6.0,
    "total_cost": 282.85,
    "profit": 345.71,
    "selling_price": 628.56,
    "labour_minutes": 20.0,
    "labour_rate": 150.0,
    "failure_pct": 10.0,
    "consumables_cost": 0.0,
    "overhead_cost": 0.0,
    "vat_pct": 15.0,
    "price_incl_vat": 722.84,
    "direct_cost": 257.14,
    "pricing_mode": "margin_on_price",
    "quoted_at": "2026-08-11T14:20:13.630705+00:00",
    "labour_cost": 50.0,
    "failure_allowance": 25.71,
    "vat_amount": 94.28,
    "notes": "Phase 5 live verification (desktop ApiClient)",
}


def test_a_real_backend_jobs_row_parses():
    """The contract check: if the backend drops or renames a field PrintJob
    requires, this fails here instead of emptying the grid at runtime."""
    job = PrintJob.model_validate(BACKEND_JOB)

    assert job.id == 2
    assert job.state == "sliced"


def test_notes_survives_parsing_of_a_real_row():
    """The original bug in one line: pydantic's extra="ignore" means a missing
    field declaration is not an error, it is silent data loss."""
    job = PrintJob.model_validate(BACKEND_JOB)

    assert job.notes == "Phase 5 live verification (desktop ApiClient)"


def test_title_uses_the_first_line_of_notes():
    job = PrintJob.model_validate({**BACKEND_JOB, "notes": "Benchy v2\nsecond line ignored"})

    assert ProjectCard._title_for(job) == "Benchy v2"


def test_title_falls_back_to_job_id_when_notes_is_null():
    """`notes` is null for most rows in the live backend, so this is the common
    path — and the one that must not raise now that the field exists."""
    job = PrintJob.model_validate({**BACKEND_JOB, "notes": None})

    assert ProjectCard._title_for(job) == "Job #2"


def test_title_is_truncated_to_the_label_width():
    job = PrintJob.model_validate({**BACKEND_JOB, "notes": "x" * 100})

    assert ProjectCard._title_for(job) == "x" * 32


def test_card_title_renders_notes_as_literal_text_not_markup(qtbot):
    """QLabel defaults to Qt::AutoText, which parses anything markup-shaped as
    rich text. `notes` is backend-supplied and now actually reaches the label
    (before this fix pydantic discarded it), so a job whose notes open with a
    tag could spoof a status, hide its own title, or blank the card — and the
    32-char truncation counts markup characters, so a cut tag mangles it."""
    raw = "<b>DONE</b> shipped"
    job = PrintJob.model_validate({**BACKEND_JOB, "notes": raw})
    card = ProjectCard(job)
    qtbot.addWidget(card)

    labels = [lbl.text() for lbl in card.findChildren(QLabel)]
    titles = [t for t in labels if t == raw[:32]]
    assert titles, (
        "no label holds the notes text verbatim — markup was consumed by "
        f"rich-text parsing instead of shown literally (labels: {labels})"
    )
    title = next(lbl for lbl in card.findChildren(QLabel) if lbl.text() == raw[:32])
    assert title.textFormat() == Qt.PlainText


def test_render_grid_survives_a_full_page_of_real_rows(qtbot):
    """The property that made the original bug catastrophic: `_render_grid`
    builds cards in a bare loop, so one raising card takes out every other
    card on the page. Nothing asserted that until now."""
    # state must land in the default "printed" tab -- _render_grid filters via
    # ProjectTabs.jobs_for_tab, and the fixture row's "sliced" belongs to the
    # other tab, so reusing it verbatim renders nothing and asserts nothing.
    jobs = [
        PrintJob.model_validate({**BACKEND_JOB, "id": i, "state": "done"}) for i in range(1, 8)
    ]
    view = HomeView()
    qtbot.addWidget(view)

    view.set_jobs(jobs)

    cards = view.findChildren(ProjectCard)
    assert len(cards) == len(jobs), f"expected one card per job, rendered {len(cards)}"


def _undeclared_job_attribute_reads() -> list[str]:
    """Cheap heuristic — deliberately not a coverage guarantee.

    It only matches bare names spelled `job`/`j`, so it cannot see the same bug
    through `self._job.notes`, `jobs[0].notes`, or `getattr(job, "notes")`, and
    it gives no cover to the other models with identical extra="ignore"
    exposure. It catches the shape that actually shipped; treat a green result
    as "that shape is absent", not "no undeclared read exists".
    """
    declared = set(PrintJob.model_fields) | set(dir(BaseModel))
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
                continue
            if node.value.id not in ("job", "j"):
                continue
            # Writes (`job.notes = x`) are not the failure this guards.
            if not isinstance(node.ctx, ast.Load):
                continue
            if node.attr.startswith(("model_", "_")) or node.attr in declared:
                continue
            where = path.relative_to(SRC.parent.parent)
            offenders.append(f"{where}:{node.lineno} {node.value.id}.{node.attr}")
    return offenders


def test_no_ui_code_reads_a_printjob_field_in_the_shape_that_broke_the_grid():
    offenders = _undeclared_job_attribute_reads()

    assert not offenders, (
        "these read a `job.<attr>` that PrintJob does not declare — if the name is "
        "bound to a PrintJob, pydantic drops the backend's value silently and the "
        "access raises AttributeError at render time:\n  " + "\n  ".join(offenders)
    )
