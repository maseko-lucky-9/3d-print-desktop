# Troubleshooting

## "App is damaged and can't be opened" on first launch

macOS Gatekeeper quarantines downloaded `.app` bundles. Strip the quarantine attribute:

```bash
xattr -d com.apple.quarantine /Applications/PrintDesktop.app
```

If that fails on Apple Silicon + macOS 14.4+, the bundle needs ad-hoc codesigning:

```bash
codesign --force --deep --sign - /Applications/PrintDesktop.app
```

## TLS certificate error connecting to backend

The homelab backend uses a self-signed CA at `print-calc.homelab`. The app expects the CA cert bundled at `<App>.app/Contents/Resources/homelab-ca.pem`. If missing:

1. Get the cert from the homelab K8s secret: `kubectl get secret homelab-ca -n cert-manager -o jsonpath='{.data.ca\.crt}' | base64 -d > homelab-ca.pem`
2. Drop into the repo root before `python setup.py py2app`, or trust it system-wide via Keychain Access → System → drag in → Always Trust.

The CA expires March 2027. Plan a renewal job before then.

## Connection refused / timeout

Backend is LAN-only. Verify Tailscale is up:

```bash
tailscale status | grep print-calc
```

`print-calc.homelab` should resolve to a Tailscale `100.x.x.x` IP. If not, `tailscale up` and re-launch the app.

## Filament SKU dropdown is empty

Backend isn't reachable, or the inventory is empty. Check:

```bash
curl --cacert homelab-ca.pem https://print-calc.homelab/api/filaments/skus
```

If it returns `[]`, add a filament purchase via the web frontend (`print-calc.homelab` → Filament tab).

## Cost mismatch error from backend

The desktop computes cost locally, then the backend recomputes and rejects mismatches >1% (defence against client bugs). If you see this in the log, file an issue with the input values — your spool size, electricity rate, or margin probably don't round-trip cleanly through float math.

## Logs

`~/Library/Logs/PrintDesktop/print-desktop.log` (5 MB rotation × 5 files). View live:

```bash
tail -f ~/Library/Logs/PrintDesktop/print-desktop.log
```

Run with `--debug` for verbose output.

## Crash on launch

The crash reporter writes the traceback to the log file and shows a dialog. Send the log when reporting.
