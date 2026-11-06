# Security

Open Vitæ is an early preview designed to run locally on one person's computer. Do not expose its HTTP service to a network, public reverse proxy or shared server. It is not a multi-user hosted service.

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/Mathaamore/open-vitae/security/advisories/new) when available. If that feature is unavailable, open a minimal issue asking for a private reporting channel; do not publish exploit details or candidate data there.

Never attach provider keys, OAuth responses, CVs, application answers, database copies or unredacted logs. Use a fictional profile and redact tokens, names and contact details. There is no guaranteed response time or security bounty.

Credentials are handled by the OS keyring or the isolated Codex session. The application has no plaintext key fallback. Local files, browser downloads and generated documents still need the protection of your operating system account and backups.

The repository check scans indexed files for forbidden artifacts and common secret/contact patterns. It is a safeguard, not proof that a change contains no private information. Review the staged diff before every commit. If a real credential is published, revoke it immediately; deleting a file in a later commit does not remove it from Git history.
