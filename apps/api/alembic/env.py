from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    # Le tabelle di Procrastinate sono gestite dal suo schema, non dai nostri modelli.
    if type_ == "table" and name.startswith("procrastinate_"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().migrations_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().migrations_database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
