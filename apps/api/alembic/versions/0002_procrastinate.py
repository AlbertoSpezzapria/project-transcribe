"""schema della coda job (Procrastinate)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07

Applica lo schema di Procrastinate 3.10. Quando si aggiorna Procrastinate vanno
aggiunte nuove migrazioni con gli script SQL del pacchetto
(`procrastinate schema --migrations-path`).
"""
import os

from alembic import op
from procrastinate.schema import SchemaManager

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_USER", "redazione_app")


def upgrade() -> None:
    op.execute(SchemaManager.get_schema())
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP_ROLE}")
    # La riga sopra concede anche UPDATE/DELETE su audit_log: lo ripristiniamo in sola aggiunta.
    op.execute(f"REVOKE UPDATE, DELETE ON audit_log FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers, "
               "procrastinate_jobs, procrastinate_workers CASCADE")
