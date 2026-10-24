---
name: database-migration
description: Create or review SQLAlchemy and Alembic schema migrations when the persistent database schema changes.
---

# Database migration workflow

Use when a persistent SQLAlchemy model or database schema is being added or changed.

Requirements:

- Treat Alembic migrations as part of the feature.
- Never rely on manually editing an existing user database.
- Keep SQLite compatibility in mind.
- Give tables, foreign keys, indexes, and constraints intentional names where appropriate.
- Preserve UUID-based identity rules defined by the domain.
- Avoid encoding domain behavior exclusively in ORM models.
- Keep domain models and persistence models conceptually separated.

Verification should include, where applicable:

1. Create a fresh database from migrations.
2. Upgrade from the previous schema revision.
3. Confirm ORM mappings work.
4. Test key constraints.
5. Test downgrade when a safe downgrade is part of the migration strategy.

Do not add speculative columns for future milestones.
