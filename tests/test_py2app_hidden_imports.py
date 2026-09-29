"""The packaged .app must actually contain the modules httpx reaches only at
runtime — not just the ones py2app's static analysis can see.

This file exists because the first real install of the built bundle opened
cleanly and then failed *every* backend request with
`ModuleNotFoundError: No module named 'anyio._backends'`. httpx delegates its
async I/O to anyio, and anyio resolves its backend dynamically:

    importlib.import_module(f"anyio._backends._{asynclib_name}")

py2app's modulegraph is a static import graph — it never sees that string, so
`anyio/_backends/` was silently omitted from Contents/Resources/lib/pythonXY.zip
while `anyio/_core/` and the rest of the package went in. Nothing caught it: the
dev run (`uv run python -m print_desktop`) imports from the real site-packages
and stays green, the whole test suite stays green, the build reports "Done!",
codesign validates, and the GUI launches. The only symptom is a WARNING line in
~/Library/Logs/PrintDesktop/print-desktop.log.

So there are two checks here, at different strengths:

1. The static one always runs: the names must stay in setup.py's py2app
   `includes`. Cheap, and it fails the moment someone "tidies up" that list.
2. The bundle one runs whenever a real (non-alias) build exists. That is the
   check with teeth — it inspects the real zip the shipped app imports from, so
   it also catches a py2app upgrade that changes how `includes` are honoured,
   which check 1 cannot. CI runs it in the `release` job, which is the only job
   that produces the artifact users actually install; `build-macos` builds with
   `py2app -A` (alias mode links to live site-packages and cannot reproduce the
   bug), so there is nothing for it to inspect there.

`includes` is read by parsing setup.py's AST rather than executing it. An
earlier version exec'd the source and argued it was inert because setup.py
guards its py2app monkeypatch behind `if "py2app" in sys.argv` — but that guard
tests membership against *pytest's* argv, so `pytest -k py2app` made the exec
import py2app.build_app and monkeypatch it for the rest of the session. Reading
the tree sidesteps that, needs neither setuptools nor py2app importable, and
does not care where the `setup()` call sits in the file.
"""

import ast
import importlib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SETUP_PY = ROOT / "setup.py"
BUNDLE = ROOT / "dist" / "3D Print Desktop.app"
BUNDLE_LIB = BUNDLE / "Contents" / "Resources" / "lib"

# Imported by name at runtime, never by a literal `import` statement anywhere
# in the dependency tree, and therefore invisible to static analysis.
#
# Deliberately just the asyncio backend: anyio also ships _backends/_trio, but
# the app runs on qasync (asyncio) and trio isn't a dependency, so naming it
# here would only make py2app pull in a package that can never be reached.
# sniffio is likewise absent on purpose — anyio 4.13 made it optional
# (`if sniffio is None: ... assume asyncio`) and it is not installed, so listing
# it would be the stale-name failure `test_hidden_import_is_actually_importable`
# exists to catch.
HIDDEN_IMPORTS = ("anyio._backends._asyncio",)


def _py2app_includes() -> list[str]:
    """Pull OPTIONS["includes"] out of setup.py's AST.

    Only the one key is literal-eval'd: the surrounding OPTIONS dict holds a
    conditional expression for `iconfile`, so the dict as a whole is not a
    literal and `ast.literal_eval` would (correctly) refuse it.
    """
    tree = ast.parse(SETUP_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "OPTIONS" for t in node.targets):
            continue
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "includes":
                return ast.literal_eval(value)
    raise AssertionError("setup.py no longer defines OPTIONS['includes']")


def _bundle_zip() -> Path | None:
    """The zip py2app compiled the app's modules into.

    Not hardcoded to python311.zip: pyproject allows >=3.11,<3.13, and py2app
    names this from sys.version_info (python312.zip on a 3.12 build). Hardcoding
    it meant a real, freshly built bundle matched nothing and the test below
    skipped itself — a guard that silently disables itself on a supported
    interpreter is the exact failure mode this file exists to eliminate.
    """
    if not BUNDLE_LIB.is_dir():
        return None
    zips = sorted(BUNDLE_LIB.glob("python*.zip"))
    return zips[0] if zips else None


@pytest.mark.parametrize("module", HIDDEN_IMPORTS)
def test_hidden_import_is_declared_in_setup_py(module):
    assert module in _py2app_includes(), (
        f"{module} is missing from setup.py's py2app `includes`. It is resolved via "
        "importlib at runtime, so py2app will not bundle it on its own and every "
        "backend request in the packaged .app will fail with ModuleNotFoundError."
    )


@pytest.mark.parametrize("module", HIDDEN_IMPORTS)
def test_hidden_import_is_actually_importable(module):
    """Guards the reverse failure: a name that is stale or misspelled in
    `includes` bundles nothing and fails exactly like the original bug, while
    the declaration check above stays green."""
    importlib.import_module(module)


@pytest.mark.skipif(not BUNDLE.is_dir(), reason="no built .app (run `python setup.py py2app`)")
@pytest.mark.parametrize("module", HIDDEN_IMPORTS)
def test_hidden_import_is_present_in_the_built_bundle(module):
    """The check with teeth: inspect the zip the shipped app really imports
    from. `includes` being correct is not proof py2app honoured it.

    Skips only when no .app exists at all. If one exists but has no module zip,
    that fails loudly rather than skipping — an alias build (`py2app -A`) links
    to live site-packages instead of bundling, so a bundle-shaped directory with
    nothing inside it must not read as "checked".
    """
    bundle_zip = _bundle_zip()
    assert bundle_zip is not None, (
        f"{BUNDLE.name} exists but contains no python*.zip under Contents/Resources/lib. "
        "An alias build (`py2app -A`) cannot be checked for bundled modules — rebuild "
        "without -A to exercise this test."
    )
    with zipfile.ZipFile(bundle_zip) as zf:
        names = zf.namelist()
    prefix = module.replace(".", "/")
    assert any(n == f"{prefix}.pyc" or n.startswith(f"{prefix}/") for n in names), (
        f"{module} is absent from {bundle_zip.name} — the packaged app will raise "
        f"ModuleNotFoundError on the first backend request. Rebuild after checking "
        "setup.py's py2app `includes`."
    )
