---
name: milestone-checkpoint
description: Verify acceptance criteria and prepare the completion report when a KiPart Manager milestone reaches its checkpoint.
---

# Milestone checkpoint

Use only when finishing or reviewing a project milestone.

1. Read the acceptance criteria for the current milestone in `docs/MILESTONES.md`.
2. Compare the implementation with those criteria.
3. Inspect the relevant diff and repository state.
4. Run the complete currently configured test suite.
5. Run any milestone-specific manual or integration check that can be performed in the current environment.
6. Confirm no later-milestone feature was unnecessarily introduced.
7. Update relevant documentation if the implementation created an architectural decision that future milestones need to know.

Report:

- milestone;
- implementation completed;
- acceptance criteria status;
- automated test results;
- manual verification performed;
- important architectural decisions;
- known limitations;
- notable files added or changed.

If an acceptance criterion cannot be verified, say so explicitly.

Stop after the checkpoint report. Do not start the next milestone.
