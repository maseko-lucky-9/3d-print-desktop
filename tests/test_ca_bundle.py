"""The bundled homelab CA is the one the backend actually presents, and the
app can actually find it once packaged — not just in the source checkout.

This file exists because nothing asserted either of those things, and as a
result the wrong certificate shipped in the repo for over a month undetected.
`homelab-ca.pem` was captured on 2026-06-26 while nginx-ingress was serving
its self-signed FALLBACK certificate (`O=Acme Co, CN=Kubernetes Ingress
Controller Fake Certificate` — itself not even a CA: `CA:FALSE`), not the real
`CN=Homelab Local CA, O=Homelab` root issued by the `homelab-ca` cert-manager
ClusterIssuer. Every TLS request the desktop app made failed with "unable to
get local issuer certificate", and nothing in CI caught it because nothing
ever loaded or inspected the bundled file.

Two failure modes matter here, so this file checks both:

1. The file itself could be wrong (the original bug). `CA:TRUE` alone is not
   enough — a syntactically valid CA for the wrong organisation would pass a
   bare "is this a CA" check. `ssl.SSLContext.load_verify_locations` alone is
   even weaker: the fake fallback cert loads as a trust anchor without
   complaint, since it's a well-formed X.509 certificate, just not a CA and
   not the right identity. So this file asserts the *positive* identity
   (CN=Homelab Local CA, O=Homelab), not just "isn't the known-bad one".
2. Even a correct file is useless if `_bundled_ca_path()` can't find it once
   packaged. py2app is not PyInstaller — it never sets `sys._MEIPASS`; the
   documented mechanism is the `RESOURCEPATH` environment variable pointing
   at Contents/Resources (py2app.readthedocs.io/en/latest/environment.html).
   A version of this function that checked `sys._MEIPASS` would silently
   never find the bundled cert in the actual shipped .app — dev mode and this
   test file's direct file check would both stay green while production
   stayed broken. Hence the tests against `_bundled_ca_path()` itself below,
   not just against the file on disk.
"""

import shutil
import ssl
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from print_desktop import __main__ as main_module

CA_BUNDLE_PATH = Path(__file__).resolve().parent.parent / "homelab-ca.pem"

# Identifying markers of the nginx-ingress self-signed fallback cert that was
# accidentally bundled instead of the real homelab CA (2026-06-26 incident).
_FAKE_FALLBACK_MARKERS = ("Acme Co", "Kubernetes Ingress Controller Fake Certificate")

# The real CA's identity. Checked positively, not just "isn't the fake one" —
# any other CA:TRUE cert would pass a purely-negative check.
_EXPECTED_CN = "Homelab Local CA"
_EXPECTED_O = "O=Homelab"

_needs_openssl = pytest.mark.skipif(
    shutil.which("openssl") is None, reason="openssl CLI not available on this runner"
)


def _openssl_x509(*args: str) -> str:
    result = subprocess.run(
        ["openssl", "x509", "-in", str(CA_BUNDLE_PATH), "-noout", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"openssl x509 {' '.join(args)} failed (rc={result.returncode}): {result.stderr}"
    )
    return result.stdout


def _parse_cert_date(dates_output: str, field: str) -> datetime:
    prefix = f"{field}="
    (line,) = [ln for ln in dates_output.splitlines() if ln.startswith(prefix)]
    raw = line.removeprefix(prefix).removesuffix(" GMT")
    return datetime.strptime(raw, "%b %d %H:%M:%S %Y").replace(tzinfo=UTC)


def test_ca_bundle_file_exists():
    assert CA_BUNDLE_PATH.exists(), (
        f"{CA_BUNDLE_PATH} is missing — the app's TLS verification "
        "(src/print_desktop/__main__.py::_bundled_ca_path) has nothing to load "
        "and every backend request will fail."
    )


@_needs_openssl
def test_ca_bundle_is_a_real_ca_not_the_nginx_fallback_cert():
    """basicConstraints must say CA:TRUE.

    The 2026-06-26 fake cert was CA:FALSE — an end-entity fallback cert, not a
    CA — which is itself proof it was never meant to be trusted as an issuer.
    """
    ext = _openssl_x509("-ext", "basicConstraints")
    assert "CA:TRUE" in ext, f"bundled cert is not a CA (basicConstraints: {ext.strip()!r})"
    assert "CA:FALSE" not in ext


@_needs_openssl
def test_ca_bundle_is_not_the_acme_co_fallback_cert():
    subject = _openssl_x509("-subject")
    issuer = _openssl_x509("-issuer")
    for marker in _FAKE_FALLBACK_MARKERS:
        assert marker not in subject, f"bundled cert subject is the fake fallback cert: {subject!r}"
        assert marker not in issuer, f"bundled cert issuer is the fake fallback cert: {issuer!r}"


@_needs_openssl
def test_ca_bundle_identity_is_the_real_homelab_ca():
    """Positive check, not just "isn't the known-bad cert": a CA:TRUE cert
    for any *other* wrong identity would pass every check above it. Subject
    and issuer must both match, and must be equal — this CA is self-signed."""
    subject = _openssl_x509("-subject")
    issuer = _openssl_x509("-issuer")
    assert _EXPECTED_CN in subject and _EXPECTED_O in subject, (
        f"unexpected subject: {subject!r}"
    )
    assert _EXPECTED_CN in issuer and _EXPECTED_O in issuer, f"unexpected issuer: {issuer!r}"
    # openssl prefixes these differently ("subject=" vs "issuer="), so strip
    # the label before comparing identities rather than the raw lines.
    subject_dn = subject.removeprefix("subject=").strip()
    issuer_dn = issuer.removeprefix("issuer=").strip()
    assert subject_dn == issuer_dn, (
        f"expected a self-signed root; subject != issuer ({subject_dn!r} vs {issuer_dn!r})"
    )


@_needs_openssl
def test_ca_bundle_validity_window_is_current():
    """Both bounds, not just notAfter: a cert that isn't valid *yet* (e.g.
    from a clock-skewed regeneration) would pass an expiry-only check and
    load without complaint via ssl.load_verify_locations, then fail exactly
    the way this file exists to prevent."""
    dates = _openssl_x509("-dates")
    not_before = _parse_cert_date(dates, "notBefore")
    not_after = _parse_cert_date(dates, "notAfter")
    now = datetime.now(UTC)
    assert not_before <= now, (
        f"bundled CA cert is not valid yet (notBefore={not_before.isoformat()})"
    )
    assert now < not_after, (
        f"bundled CA cert expired {not_after.isoformat()} — replace homelab-ca.pem "
        "before the app loses the ability to verify the backend's TLS cert"
    )


def test_ca_bundle_loads_as_a_valid_trust_anchor():
    """The exact mechanism api_client.ApiClient uses: httpx's `verify=<path>`
    ultimately calls ssl.SSLContext.load_verify_locations(cafile=...). A file
    that isn't valid PEM, or contains no certificates, raises SSLError here —
    this would catch a corrupted or truncated bundle that the field-level
    checks above don't exercise."""
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(CA_BUNDLE_PATH))


def test_bundled_ca_path_resolves_via_resourcepath_when_frozen(tmp_path, monkeypatch):
    """py2app sets RESOURCEPATH to Contents/Resources at runtime — the
    directory `data_files` with an empty destination actually copies
    homelab-ca.pem into. This is the only reliable way to find it inside the
    packaged .app; py2app does NOT set sys._MEIPASS (that's PyInstaller-only,
    and a version of this function that checked it would silently never find
    the bundled cert in a real build while staying green here in dev)."""
    fake_resources = tmp_path / "Resources"
    fake_resources.mkdir()
    fake_ca = fake_resources / "homelab-ca.pem"
    fake_ca.write_text("stand-in for the real cert; only path resolution is under test")
    monkeypatch.setenv("RESOURCEPATH", str(fake_resources))

    resolved = main_module._bundled_ca_path()

    assert resolved == fake_ca


def test_bundled_ca_path_falls_back_to_source_tree_without_resourcepath(monkeypatch):
    """In dev (`uv run python -m print_desktop`), RESOURCEPATH is unset and
    the source-tree-relative fallback must still find the real repo-root
    file directly — this is the path every contributor's local run takes."""
    monkeypatch.delenv("RESOURCEPATH", raising=False)

    resolved = main_module._bundled_ca_path()

    assert resolved == CA_BUNDLE_PATH


def test_bundled_ca_path_returns_none_when_nowhere_to_be_found(tmp_path, monkeypatch):
    """RESOURCEPATH set but empty, and the source-tree candidate patched away
    — must return None rather than raising, so main() can fall through to
    plain `verify=True` instead of crashing on startup."""
    monkeypatch.setenv("RESOURCEPATH", str(tmp_path))  # empty dir, no homelab-ca.pem
    monkeypatch.setattr(main_module, "__file__", str(tmp_path / "nonexistent" / "__main__.py"))

    assert main_module._bundled_ca_path() is None
