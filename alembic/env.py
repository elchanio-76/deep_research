import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Load .env before resolving DATABASE_URL so local development works
# without manually exporting environment variables.
load_dotenv()

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Configure Python logging from the alembic.ini [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the database URL from the environment.
# An optional x_argument override (e.g. -x db_url=...) takes precedence,
# which allows integration tests to target a temporary test database without
# modifying the environment.
_x_args = context.get_x_argument(as_dictionary=True)
database_url: str | None = _x_args.get("db_url") or os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Please set it in your .env file or environment before running Alembic."
    )

# Inject the resolved URL into the Alembic config so that engine_from_config
# picks it up.  This keeps credentials out of alembic.ini.
config.set_main_option("sqlalchemy.url", database_url)

# No SQLAlchemy ORM models — migrations are written manually using op.* directives.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (--sql flag).

    Emits SQL to stdout/file without connecting to the database.
    Useful for generating migration scripts to review or apply manually.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (default).

    Creates a synchronous SQLAlchemy engine, connects to the database,
    and applies pending migrations.  NullPool is used so that the engine
    does not hold idle connections after the migration run completes.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
