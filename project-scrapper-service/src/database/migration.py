from pathlib import Path
from alembic.config import Config
from alembic import command
import structlog

from src.config import Settings

logger = structlog.get_logger()


def run_migrations(config: Settings) -> None:
    """Программный запуск миграций Alembic."""
    project_root = Path(__file__).parent.parent.parent
    alembic_cfg_path = project_root / "alembic.ini"

    alembic_cfg = Config(str(alembic_cfg_path))
    alembic_cfg.set_main_option("sqlalchemy.url", config.database_url_sync)

    command.upgrade(alembic_cfg, "head")

    logger.info("Database migrations applied successfully!")
