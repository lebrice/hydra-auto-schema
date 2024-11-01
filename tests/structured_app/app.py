# import hydra_plugins.auto_schema.auto_schema_plugin  # noqa
# import hydra_plugins.auto_schema  # noqa
# import hydra_plugins  # noqa
import logging
from dataclasses import dataclass
from pathlib import Path

import hydra
import rich.logging
from hydra.core.config_store import ConfigStore
from omegaconf import MISSING, OmegaConf

from hydra_plugins.auto_schema import auto_schema_plugin

logging.basicConfig(
    level=logging.INFO,
    format=" %(message)s",
    datefmt="[%X]",
    force=True,
    handlers=[
        rich.logging.RichHandler(
            markup=True,
            rich_tracebacks=True,
            tracebacks_width=100,
            tracebacks_show_locals=False,
        )
    ],
)


@dataclass
class DBConfig:
    driver: str = MISSING
    host: str = "localhost"
    port: int = MISSING


@dataclass
class MySQLConfig(DBConfig):
    driver: str = "mysql"
    port: int = 3306
    user: str = MISSING
    password: str = MISSING


@dataclass
class PostGreSQLConfig(DBConfig):
    driver: str = "postgresql"
    user: str = MISSING
    port: int = 5432
    password: str = MISSING
    timeout: int = 10


@dataclass
class Config:
    db: DBConfig = MISSING
    debug: bool = False


cs = ConfigStore.instance()
cs.store(name="base_config", node=Config)
cs.store(group="db", name="base_mysql", node=MySQLConfig)
cs.store(group="db", name="base_postgresql", node=PostGreSQLConfig)


auto_schema_plugin.configure(
    auto_schema_plugin.AutoSchemaPluginConfig(
        schemas_dir=Path(__file__).parent / "schemas",
        regen_schemas=True,
        quiet=False,
        add_headers=True,
        verbose=True,
        stop_on_error=True,
    )
)


@hydra.main(version_base=None, config_path="conf", config_name="config")
def my_app(cfg: Config) -> None:
    print(cfg)
    print(OmegaConf.to_yaml(cfg, resolve=True))


if __name__ == "__main__":
    my_app()
