"""py2app build script.

Usage:
    uv run python setup.py py2app

Post-build:
    codesign --force --deep --sign - "dist/3D Print Desktop.app"
    open "dist/3D Print Desktop.app"
"""

import sys
from pathlib import Path

from setuptools import setup

# Only patch py2app when actually building the bundle; keep this script importable
# during plain wheel builds (uv sync) where py2app isn't installed.
if "py2app" in sys.argv:
    import py2app.build_app as _p2a_build

    _orig_finalize = _p2a_build.py2app.finalize_options

    def _patched_finalize(self):
        # py2app rejects any non-empty install_requires; pyproject.toml's
        # `dependencies` get auto-merged in, so we strip it before its check.
        self.distribution.install_requires = []
        return _orig_finalize(self)

    _p2a_build.py2app.finalize_options = _patched_finalize

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "src" / "print_desktop" / "__main__.py"

DATA_FILES = []
ca_path = ROOT / "homelab-ca.pem"
if ca_path.exists():
    DATA_FILES.append(("", ["homelab-ca.pem"]))

OPTIONS = {
    "argv_emulation": False,
    "packages": ["print_desktop"],
    "includes": ["qasync", "qtawesome"],
    "iconfile": (
        str(ROOT / "resources" / "icon.icns")
        if (ROOT / "resources" / "icon.icns").exists()
        else None
    ),
    "plist": {
        "CFBundleName": "3D Print Desktop",
        "CFBundleDisplayName": "3D Print Desktop",
        "CFBundleIdentifier": "com.prudentia.printdesktop",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSAppNapDisabled": True,
        "NSHumanReadableCopyright": "© 2026 Thulani Maseko",
        "LSApplicationCategoryType": "public.app-category.utilities",
    },
}

setup(
    name="3D Print Desktop",
    app=[str(ENTRY)],
    data_files=DATA_FILES,
    options={"py2app": {k: v for k, v in OPTIONS.items() if v is not None}},
    setup_requires=["py2app"],
)
