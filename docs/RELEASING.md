# Release candidates and public acceptance

The repository contains release tooling, not proof of a public release. No Apple credentials, real provider sign-in, notarization result or clean-Mac acceptance is recorded by this change. Development builds remain ad-hoc signed and contain no updater. Do not distribute them as verified installers or bypass Gatekeeper.

## Version and build

`pyproject.toml` is the marketing version. Increase `macos/release.json`'s integer build for every distributed candidate; never reuse a build number. The bundle identifier and workspace directory remain stable. Record changes in `CHANGELOG.md`, tag the reviewed commit as `v<version>`, then dispatch **macOS release candidate** for that tag. The workflow uses an Apple Silicon runner and creates a **draft** GitHub release only.

Python dependencies still use bounded ranges. The build saves its exact installed inventory as `build-requirements.txt`; this is not a bit-for-bit reproducible toolchain. Review and pin a tested dependency set before claiming reproducible public binaries. Codex is pinned in the workflow. Sparkle is separately pinned by its archive URL and SHA256.

## Configure the protected GitHub environment

Create `macos-release` with deployment approval restricted to release maintainers. Configure these secrets through GitHub, never source files:

| Secret | Value |
|---|---|
| `MACOS_CERTIFICATE_BASE64` | Developer ID Application certificate and private key exported as PKCS12, base64 encoded |
| `MACOS_CERTIFICATE_PASSWORD` | Export password |
| `BUILD_KEYCHAIN_PASSWORD` | Random password for the disposable runner keychain |
| `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` | Apple account, team and app-specific password for notarytool |
| `SPARKLE_PRIVATE_KEY` | Exported Ed25519 private key for Sparkle's `--ed-key-file` option |

Configure these environment variables:

| Variable | Value |
|---|---|
| `MACOS_SIGN_IDENTITY` | Full `Developer ID Application: …` identity matching the certificate |
| `SPARKLE_ARCHIVE_URL` | Versioned official Sparkle 2.9.6 or newer stable `https://github.com/sparkle-project/Sparkle/releases/download/<version>/Sparkle-<version>.tar.xz` distribution URL |
| `SPARKLE_SHA256` | Independently checked, lowercase 64-character SHA256 of that archive |
| `SPARKLE_PUBLIC_KEY` | Matching base64 Ed25519 public key, 32 decoded bytes |
| `SPARKLE_FEED_URL` | Stable HTTPS feed URL, for example this repository's `releases/latest/download/appcast.xml` URL |

Generate the Sparkle signing key once using the tools in that verified distribution. Keep an offline recovery copy of the private key. Never generate a different update key for each build. Losing the key prevents normal updates from already installed versions. The feed can be public; the private key cannot. The app requires archive verification before extraction and signed feeds (Sparkle 2.9+). Publish the generated, signed appcast and HTML release notes without modifying their embedded signatures. The workflow puts credentials in a temporary keychain/files and removes them even after failure.

The workflow signs nested Mach-O files and bundles from the inside out with hardened runtime. Only browser executables receive the JIT entitlement. It smoke-tests the frozen service, local assets and bundled native executables in a temporary workspace without provider access. It notarizes and staples the app, verifies it with Gatekeeper, recreates the update ZIP, builds a compressed DMG containing the app and an Applications shortcut, then signs/notarizes/staples the DMG. Sparkle's tooling signs the update archive and generates the appcast. Any failed step prevents the draft release step. Validate nested browser code on the actual signed candidate; a successful development shell build does not establish that hardened runtime will work.

## Public acceptance, before publishing the draft

Use a clean macOS 14+ Apple Silicon machine, a fictional candidate and dedicated test provider access. Do not use contributor CVs, applications or their ordinary provider session.

1. Download the draft candidate through the same browser/download channel intended for users. Verify the checksum, Developer ID, app and DMG tickets, and Gatekeeper assessment. Install by dragging to Applications; launch with quarantine intact, no Terminal or security workaround.
2. Resume onboarding after quitting at each step, import text PDF/DOCX/TXT, correct imported facts and confirm the profile. Verify keyboard focus, small windows, VoiceOver, dark appearance and reduced motion on the native WKWebView.
3. Check real provider sign-in, model inference, limits, reconnect/disconnect and keyring behavior. Verify current provider distribution requirements. API subscriptions and billing are not interchangeable. Model discovery alone is not an inference entitlement check.
4. Search real permitted feeds and configured employer boards. Confirm original URLs, source dates and missing data. Test offline sources, cancellation, partial results and retry. An omitted listing or its age is not evidence of closure.
5. Prepare and edit a fictional application; check PDF export, factual CV content, unknown questions, consent and manual status transitions. Do not send test applications to real employers.
6. Install a second signed candidate with a greater build via the signed appcast. Test a valid update, invalid archive signature, offline feed, cancellation, unsaved edits and relaunch. Confirm profile, drafts, dossier files, history, Keychain session and selected workspace survive.
7. Record machine/OS, candidate commit/build, checksums, ticket results, provider modes tested and remaining issues in release notes. Publish only after every relevant check passes. Public GitHub Releases then becomes the feed's source of truth.
8. Change `site/release.json` to the accepted version and its exact versioned GitHub DMG URL with `verified: true`, update the availability FAQ, and redeploy the static site. Never point the CTA at an unverified `/latest` artifact.

Sparkle supplies native update prompts and a manual **Rechercher des mises à jour…** menu item in release builds. Automatic checks follow Sparkle's user choice; automatic installation is disabled. The generated feed currently contains the newest candidate, not delta patches or a complete archive of historical releases. A candidate is never made public automatically by this workflow.

## Upgrade recovery

The application bundle does not contain user data. Before a legacy SQLite schema is changed, the store checks integrity and writes a private SQLite backup to `data/backups/before-schema-<target-version>.sqlite3` using SQLite's online backup API. It preserves the first completed recovery point. A newer `user_version` is rejected before schema writes. This protects the database, not the generated files or Keychain; it is not a replacement for whole-workspace backups.

Before testing an upgrade, quit the app and use Finder to duplicate the entire selected workspace. The default is `~/Library/Application Support/Candidatures`, accessible through **Fichier → Afficher l’espace dans le Finder**. Keep the duplicate outside the application bundle. If an upgrade fails, quit before restoring. Duplicate the failed workspace too; restore the prior complete workspace and use its compatible app version. For database-only recovery, replace `data/agent.sqlite3` with a **copy** of the matching migration backup while the app is closed, keeping the original database and any SQLite journal files together in the failed copy. Never delete the only copy or replace files while a service is running. Generated attachments and database state must refer to the same workspace snapshot.

## Primary references

- [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Sparkle setup, archive signing and appcasts](https://sparkle-project.org/documentation/)
- [Official Codex app-server authentication guidance](https://learn.chatgpt.com/docs/app-server)
- [Registered Sign in with ChatGPT and app-server configuration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
