"""Alembic environment using the connection provided by the composition root."""

from alembic import context

from kipartmanager.infrastructure.models import Base

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
