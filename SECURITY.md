# Security reporting — setup pending

FabParts is development software. No supported release range, response-time commitment or security maintenance policy has been established.

## Report privately

**A private reporting channel has not yet been configured.** No email address or working GitHub advisory endpoint is asserted here.

At the authorized creation of the GitHub repository, enable private vulnerability reporting and verify that the private “Report a vulnerability” route is available from the Security tab. Record the verified route here before inviting public reports. If that mechanism is unavailable, designate and verify another private contact. This setup step is performed on the actual repository; it does not require another general publication audit. GitHub's [private reporting documentation](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately) explains that the feature must be enabled separately from `SECURITY.md`.

Until then, do not post vulnerability details, exploit instructions, secrets or user data in a public issue. If you already have a private conversation with the maintainer, ask there for the reporting route. Otherwise, a public request for a private contact must contain no vulnerability details or sensitive attachments.

A private report should include the affected revision, platform, impact, reproduction steps using synthetic data and any relevant sanitized logs. Never attach a real catalogue, provider credential or full local backup unless a suitable private transfer and its necessity have been agreed.

## Development boundaries

Keep test data separate from personal and laboratory data. Review optional provider destinations and permissions before enabling them. The read-only Tauri prototype and the historical application have different capabilities; do not infer the historical application's write behavior from the prototype.

This publication audit is not a penetration test or a dependency vulnerability assessment.
