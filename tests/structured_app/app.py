# import hydra_plugins.auto_schema.auto_schema_plugin  # noqa
# import hydra_plugins.auto_schema  # noqa
# import hydra_plugins  # noqa
from __future__ import annotations

import logging

import hydra
import rich.logging
from omegaconf import OmegaConf

from hydra_plugins.auto_schema import auto_schema_plugin
from tests.structured_app.conf import Config

# from conf import Config

logging.basicConfig(
    level=logging.DEBUG,
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

auto_schema_plugin.configure(
    auto_schema_plugin.AutoSchemaPluginConfig(
        # schemas_dir=Path(__file__).parent / "conf",
        regen_schemas=True,
        quiet=False,
        add_headers=True,
        verbose=True,
        stop_on_error=True,
    )
)


@hydra.main(
    version_base=None,
    config_path="conf",
    config_name="config",
)
def my_app(cfg: Config) -> None:
    print(cfg)
    print(OmegaConf.to_yaml(cfg, resolve=True))


if __name__ == "__main__":
    my_app()
