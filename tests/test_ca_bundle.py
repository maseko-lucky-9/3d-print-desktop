"""The bundled homelab CA is the one the backend actually presents.

This file exists because nothing asserted it, and as a result the wrong
certificate shipped in the repo for over a month undetected. `homelab-ca.pem`
was captured on 2026-06-26 while nginx-ingress was serving its self-signed
FALLBACK certificate (`O=Acme Co, CN=Kubernetes Ingress Controller Fake
Certificate` — itself not even a CA: `CA:FALSE`), not the real
`CN=Homelab Local CA, O=Homelab` root issued by the `homelab-ca` cert-manager
ClusterIssuer. Every TLS request the desktop app made failed with "unable to
get local issuer certificate", and nothing in CI caught it because nothing
ever loaded or inspected the bundled file.

`ssl.SSLContext.load_verify_locations` alone would NOT have caught this: the
fake fallback cert is a syntactically well-formed X.509 certificate and loads
just fine as a trust anchor. What actually distinguishes a correct bundle from
the wrong-but-valid one that shipped is its *identity* — it must be a real CA
(`CA:TRUE`) and it must not be the nginx-ingress fallback. Hence the explicit
subject/issuer and basicConstraints checks below, not just a load-without-
raising smoke test.
"""

import shutil
import ssl
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

CA_BUNDLE_PATH = Path(__file__).resolve().parent.parent / "homelab-ca.pem"

# Identifying markers of the nginx-ingress self-signed fallback cert that was
# accidentally bundled instead of the real homelab CA (2026-06-26 incident).
_FAKE_FALLBACK_MARKERS = ("Acme Co", "Kubernetes Ingress Controller Fake Certificate")

pytestmark = pytest.mark.skipif(
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


def _parse_not_after(dates_output: str) -> datetime:
    (line,) = [ln for ln in dates_output.splitlines() if ln.startswith("notAfter=")]
    raw = line.removeprefix("notAfter=").removesuffix(" GMT")
    return datetime.strptime(raw, "%b %d %H:%M:%S %Y").replace(tzinfo=UTC)


def test_ca_bundle_file_exists():
    assert CA_BUNDLE_PATH.exists(), (
        f"{CA_BUNDLE_PATH} is missing — the app's TLS verification "
        "(src/print_desktop/__main__.py::_bundled_ca_path) has nothing to load "
        "and every backend request will fail."
    )


def test_ca_bundle_is_a_real_ca_not_the_nginx_fallback_cert():
    """basicConstraints must say CA:TRUE.

    The 2026-06-26 fake cert was CA:FALSE — an end-entity fallback cert, not a
    CA — which is itself proof it was never meant to be trusted as an issuer.
    """
    ext = _openssl_x509("-ext", "basicConstraints")
    assert "CA:TRUE" in ext, f"bundled cert is not a CA (basicConstraints: {ext.strip()!r})"
    assert "CA:FALSE" not in ext


def test_ca_bundle_is_not_the_acme_co_fallback_cert():
    subject = _openssl_x509("-subject")
    issuer = _openssl_x509("-issuer")
    for marker in _FAKE_FALLBACK_MARKERS:
        assert marker not in subject, f"bundled cert subject is the fake fallback cert: {subject!r}"
        assert marker not in issuer, f"bundled cert issuer is the fake fallback cert: {issuer!r}"


def test_ca_bundle_is_not_expired():
    dates = _openssl_x509("-dates")
    not_after = _parse_not_after(dates)
    assert not_after > datetime.now(UTC), (
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
