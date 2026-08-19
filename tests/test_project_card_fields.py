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
Hence two checks: the specific one (`notes` round-trips and titles render), and
the general one (an AST sweep for *any* undeclared field read), so the next
field someone forgets to declare fails here instead of in a log file.
"""

import ast
from pathlib import Path

from print_desktop.models.print_request import PrintJob
from print_desktop.ui.widgets.project_card import ProjectCard

SRC = Path(__file__).resolve().parent.parent / "src" / "print_desktop"

# Minimal real backend shape: the required fields plus the one that regressed.
# Kept deliberately small — the point is the model/UI contract, not coverage of
# every column GET /api/jobs returns.
BASE_JOB = {"id": 4, "state": "done", "created_at": "2026-08-12T17:29:07.291210+00:00"}


def test_notes_round_trips_from_the_backend_payload():
    """The original bug in one line: pydantic's extra="ignore" means a missing
    field declaration is not an error, it is silent data loss."""
    job = PrintJob(**BASE_JOB, notes="Benchy v2\nsecond line")

    assert job.notes == "Benchy v2\nsecond line"


def test_title_uses_the_first_line_of_notes():
    job = PrintJob(**BASE_JOB, notes="Benchy v2\nsecond line ignored")

    assert ProjectCard._title_for(job) == "Benchy v2"


def test_title_falls_back_to_job_id_when_notes_is_null():
    """`notes` is null for most rows in the live backend, so this is the common
    path — and the one that must not raise now that the field exists."""
    job = PrintJob(**BASE_JOB, notes=None)

    assert ProjectCard._title_for(job) == "Job #4"


def test_title_is_truncated_to_the_label_width():
    job = PrintJob(**BASE_JOB, notes="x" * 100)

    assert ProjectCard._title_for(job) == "x" * 32


def _undeclared_job_attribute_reads() -> list[str]:
    """Static sweep for `job.<attr>` / `j.<attr>` reads that no PrintJob field
    backs. Convention-based (those two names always hold a PrintJob in this UI),
    which is why it is a sweep and not a type checker — but it is exactly the
    class of mistake that produced this file, and it costs nothing to run."""
    declared = set(PrintJob.model_fields)
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
                continue
            if node.value.id not in ("job", "j"):
                continue
            if node.attr.startswith(("model_", "_")) or node.attr in declared:
                continue
            where = path.relative_to(SRC.parent.parent)
            offenders.append(f"{where}:{node.lineno} {node.value.id}.{node.attr}")
    return offenders


def test_no_ui_code_reads_an_undeclared_printjob_field():
    offenders = _undeclared_job_attribute_reads()

    assert not offenders, (
        "these read a PrintJob attribute that the model does not declare — pydantic "
        "drops the backend's value silently and the access raises AttributeError at "
        "render time:\n  " + "\n  ".join(offenders)
    )
