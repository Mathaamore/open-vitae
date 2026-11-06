# Open Vitæ for Mac

AppKit and WKWebView application for macOS 14+ on Apple Silicon. Python, the local service, Codex and the form-reading browser are bundled. The service listens on 127.0.0.1 on a free port and stops with the app. Users do not need a terminal.

Move Open Vitae.app into Applications and open it. Local builds are ad hoc signed. Public distribution requires Developer ID signing and notarization; keep Gatekeeper enabled. See [release acceptance](../docs/RELEASING.md) for the public distribution requirements.

A new workspace lives in `~/Library/Application Support/Candidatures`. Existing selected workspaces are preserved; **File → Open Workspace…** changes it. Data stays outside the application bundle. Profiles, saved jobs, documents and portable AI work without a connected provider. ChatGPT uses Codex's official login flow; Claude and Gemini use API keys, independently of consumer subscriptions. Credentials stay in the macOS keychain. Provider charges are separate. Applications are reviewed and submitted manually.

## Build

Requires Python 3.11+, Swift/Xcode Command Line Tools and the official native Codex CLI. For npm installations, `CODEX_BINARY` must point to the macOS binary under `vendor/aarch64-apple-darwin/codex/codex`, rather than its JavaScript launcher. From the repository root:

```sh
python3 -m venv --system-site-packages /tmp/candidatures-mac-build
/tmp/candidatures-mac-build/bin/python -m pip install -e '.[test]' 'pyinstaller>=6,<7'
PLAYWRIGHT_BROWSERS_PATH=/tmp/candidatures-browsers /tmp/candidatures-mac-build/bin/python -m playwright install chromium --only-shell
/tmp/candidatures-mac-build/bin/python macos/build.py
```

The bundle excludes personal workspaces and includes licenses in `Contents/Resources/licenses`. English strings are in `en.lproj/Localizable.strings`. The bundle identifier, keychain references, preferences and Application Support folder keep their existing names to preserve user data.

Tests use temporary workspaces and fictional providers. See the root README for test commands and limits. Real account generation, notarization, updates and checks on a clean Mac require separate release acceptance; passing fixture tests does not establish those results.

Version comes from `pyproject.toml`; build number from `macos/release.json`. `build.py --release` requires Developer ID, verified Sparkle, an Ed25519 public key and HTTPS feed. `distribute.py` notarizes, staples tickets and creates the DMG. The manual workflow creates a draft GitHub release.

File imports use the native WebKit upload panel, restricted to the local workspace page. Canceling the panel leaves the current profile unchanged. Test the CV picker in the Mac app as well as in browser QA; a successful browser import does not test WKWebView’s native panel. Keep only the installed copy in Applications registered for everyday use; build and QA copies can appear as separate apps in Launch Services.
