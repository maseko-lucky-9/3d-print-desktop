"""The packaged .app must actually contain the modules httpx reaches only at
runtime — not just the ones py2app's static analysis can see.

This file exists because the first real install of the built bundle opened
cleanly and then failed *every* backend request with
`ModuleNotFoundError: No module named 'anyio._backends'`. httpx delegates its
async I/O to anyio, and anyio resolves its backend dynamically:

    importlib.import_module(f"anyio._backends._{asynclib_name}")

py2app's modulegraph is a static import graph — it never sees that string, so
`anyio/_backends/` was silently omitted from
Contents/Resources/lib/python311.zip while `anyio/_core/` and the rest of the
package went in. Nothing caught it: the dev run (`uv run python -m
print_desktop`) imports from the real site-packages and stays green, the whole
test suite stays green, the build reports "Done!", codesign validates, and the
GUI launches. The only symptom is a WARNING line in
~/Library/Logs/PrintDesktop/print-desktop.log.

So there are two checks here, at different strengths:

1. The static one always runs: the names must stay in setup.py's py2app
   `includes`. Cheap, and it fails the moment someone "tidies up" that list.
2. The bundle one runs only when dist/ has actually been built. That is the
   check with teeth — it inspects the real zip the shipped app imports from,
   so it also catches a py2app upgrade that changes how `includes` are
   honoured, which check 1 cannot.
"""

import importlib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "dist" / "3D Print Desktop.app"
BUNDLE_ZIP = BUNDLE / "Contents" / "Resources" / "lib" / "python311.zip"

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


def _py2app_options() -> dict:
    """Read setup.py's OPTIONS without executing setup() — importing the module
    would run the py2app build. The file guards its py2app monkeypatch behind
    `if "py2app" in sys.argv`, so a plain exec of the source is safe and keeps
    this test reading the *real* dict rather than a copy that can drift."""
    namespace: dict = {"__file__": str(ROOT / "setup.py"), "__name__": "setup_under_test"}
    source = (ROOT / "setup.py").read_text()
    # Drop the setup() call at the end; everything above it is declarative.
    source = source[: source.rindex("setup(")]
    exec(compile(source, str(ROOT / "setup.py"), "exec"), namespace)  # noqa: S102
    return namespace["OPTIONS"]


@pytest.mark.parametrize("module", HIDDEN_IMPORTS)
def test_hidden_import_is_declared_in_setup_py(module):
    includes = _py2app_options()["includes"]
    assert module in includes, (
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


@pytest.mark.skipif(
    not BUNDLE_ZIP.exists(),
    reason="no built bundle (run `uv run python setup.py py2app` first)",
)
@pytest.mark.parametrize("module", HIDDEN_IMPORTS)
def test_hidden_import_is_present_in_the_built_bundle(module):
    """The check with teeth: inspect the zip the shipped app really imports
    from. `includes` being correct is not proof py2app honoured it."""
    with zipfile.ZipFile(BUNDLE_ZIP) as zf:
        names = zf.namelist()
    prefix = module.replace(".", "/")
    assert any(n == f"{prefix}.pyc" or n.startswith(f"{prefix}/") for n in names), (
        f"{module} is absent from {BUNDLE_ZIP.name} — the packaged app will raise "
        f"ModuleNotFoundError on the first backend request. Rebuild after checking "
        "setup.py's py2app `includes`."
    )
