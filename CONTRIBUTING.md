# Contributing to FabParts

FabParts is in early development. Original project code is licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE). Public hosting is still being prepared. Contributions must be offered under this license by someone entitled to do so; imported third-party material must retain its compatible license and notices. No CLA or mandatory DCO is required.

## Set up and check

Use the [development instructions](README.md#development) and the locked Python, npm and Cargo dependencies. Use disposable data under `local-data/` or outside the checkout. Never use a personal or laboratory database for tests.

Run the checks listed in the README. At a milestone checkpoint, run the complete existing test suite. Frontend changes require tests and Svelte/TypeScript checks; Rust changes require the relevant Cargo tests. Native UI changes also need visual inspection at normal, narrow and wide sizes, in both themes where applicable.

Record the commands, results, environment and any pre-existing failures. Do not claim a native check from a build or a screenshot of the separate UX prototype.

## Issues and pull requests

Once a public repository exists, use its issue tracker for reproducible bugs and focused proposals. Include the expected and observed behavior, version/commit, OS and a minimal example made from synthetic data. Remove credentials, private paths and catalogue contents from attachments.

Use the private reporting process described in [SECURITY.md](SECURITY.md) for vulnerabilities. Do not disclose security details in a public issue while a private contact is being arranged.

For a change:

1. Start from an up-to-date `main` after repository consolidation.
2. Create one focused branch. Codex work uses `codex/<short-description>` by default; owner-approved milestone names such as `tech/02-real-asset-previews` are also supported.
3. Implement the agreed scope, tests and documentation together.
4. Open a PR explaining the problem, changed behavior, verification and limitations.
5. Record an identifiable milestone commit and checkpoint, then request Product Owner/maintainer review.
6. Merge the approved change to `main`, then push only the approved branch. Do not force-push or skip the checkpoint.

Do not start a later milestone as part of an unrelated fix. No remote or next-milestone branch is created by these instructions.

## Architecture and data

Follow [AGENTS.md](AGENTS.md) and [ARCHITECTURE.md](docs/ARCHITECTURE.md).

- SQLite and the managed Asset Store are authoritative; KiCad outputs are generated artifacts.
- Keep UI, application, domain, ports and infrastructure boundaries intact.
- Preserve offline core behavior; providers are optional adapters.
- Do not silently replace user assets, rewrite published versions or modify official KiCad libraries.
- Search existing resources before generation; preserve provenance and validate before publication.
- No real credentials, user databases, laboratory catalogues or provider downloads in fixtures.

## UI and documentation

Use [fab-design-system](.agents/skills/fab-design-system/SKILL.md) for shared identity and [professional-workshop-ui](.agents/skills/professional-workshop-ui/SKILL.md) for desktop workflows. Existing PySide6 screens also follow [pyside-ui-ux](.codex/skills/pyside-ui-ux/SKILL.md). Reuse existing components and [UI conventions](docs/UI_GUIDELINES.md); do not introduce a parallel palette or redesign.

Update user/developer documentation for changed behavior. Architectural decisions belong in the ADRs; preserve historical checkpoint conclusions and append new evidence explicitly. Use portable paths and clearly label simulations, future behavior and unverified platforms.

The Product Owner confirms designing `fab-design-system` with Claude assistance and `professional-workshop-ui` with ChatGPT assistance, and authorizes publication of both packs under GPL-3.0-or-later with FabApps projects. Third-party resources keep their terms.

## Provenance and licensing

Identify borrowed code and assets, their exact source/version and applicable notices. Do not assume that an online symbol, footprint, 3D model or datasheet can be redistributed. Keep third-party notices and report uncertain provenance before adding material.

Disclose substantial AI assistance and review the resulting code and citations. Assistance does not establish ownership or eliminate obligations attached to copied material. Confirm that your employer, institution or other rights holders permit the contribution when relevant. No CLA, DCO requirement or automatic relicensing policy has been adopted; those remain owner decisions.

When redistributing GPL-covered modifications, preserve copyright and license notices, identify changes, and provide the corresponding source as required by the GPL. The project license does not authorize you to relicense third-party assets. Do not add invented copyright holders; retain existing attributions and disclose uncertain ownership.
