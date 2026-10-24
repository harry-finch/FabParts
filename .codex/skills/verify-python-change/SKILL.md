---
name: verify-python-change
description: Verify Python source, dependency, packaging, or tooling changes using the project's configured quality checks.
---

# Python change verification

Use the repository configuration to determine the actual available commands. Do not assume tools that are not configured.

When Python code, project configuration, packaging, or dependencies have changed:

1. Identify the checks relevant to the change from `pyproject.toml` and repository configuration.
2. Run focused tests first when useful.
3. Run configured formatting/lint/type checks relevant to the modified code.
4. At a milestone checkpoint, run the complete existing test suite.
5. Fix failures introduced by the current change.
6. Do not hide or rewrite unrelated pre-existing failures.
7. Report commands executed and results concisely.

Do not introduce a new formatter, linter, type checker, or test framework merely to satisfy this skill.
