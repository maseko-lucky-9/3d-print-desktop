"""py2app build script.

Usage:
    uv run python setup.py py2app

Post-build:
    codesign --force --deep --sign - dist/PrintDesktop.app
    open dist/PrintDesktop.app
"""

from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "src" / "print_desktop" / "__main__.py"

DATA_FILES = []
ca_path = ROOT / "homelab-ca.pem"
if ca_path.exists():
    DATA_FILES.append(("", [str(ca_path)]))

OPTIONS = {
    "argv_emulation": False,
    "packages": ["print_desktop"],
    "includes": ["qasync", "qtawesome"],
    "iconfile": str(ROOT / "resources" / "icon.icns") if (ROOT / "resources" / "icon.icns").exists() else None,
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
