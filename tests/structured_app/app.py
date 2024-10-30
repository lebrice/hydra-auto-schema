from dataclasses import dataclass

import hydra
from hydra.core.config_store import ConfigStore
from omegaconf import MISSING, OmegaConf


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

# from hydra_plugins.auto_schema import auto_schema_plugin

# auto_schema_plugin.register_auto_schema_plugin()


@hydra.main(version_base=None, config_path="conf", config_name="config")
def my_app(cfg: Config) -> None:
    print(OmegaConf.to_yaml(cfg, resolve=True))


if __name__ == "__main__":
    my_app()
