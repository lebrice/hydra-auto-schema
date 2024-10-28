import importlib
from pathlib import Path
from typing import ClassVar

import hydra.core.plugins
import hydra_zen
from hydra.core.config_search_path import ConfigSearchPath
from hydra.plugins.search_path_plugin import SearchPathPlugin

from hydra_auto_schema.auto_schema import add_schemas_to_all_hydra_configs, logger


def register_auto_schema_plugin():
    hydra.core.plugins.Plugins.instance().register(AutoSchemaPlugin)


@hydra_zen.hydrated_dataclass(
    add_schemas_to_all_hydra_configs, populate_full_signature=True, zen_partial=True
)
class AutoSchemaPluginConfig:
    """Config for the AutoSchemaPlugin."""

    schemas_dir: Path | None = None
    regen_schemas: bool = False
    stop_on_error: bool = False
    quiet: bool = True
    add_headers: bool | None = False


config: AutoSchemaPluginConfig | None = None
"""Global config used by default by the AutoSchemaPlugin."""


class AutoSchemaPlugin(SearchPathPlugin):
    provider: str
    path: str
    _ALREADY_DID: ClassVar[bool] = False

    def __init__(self) -> None:
        super().__init__()
        self.config = config or AutoSchemaPluginConfig()
        self.fn = hydra_zen.instantiate(self.config)

    def manipulate_search_path(self, search_path: ConfigSearchPath) -> None:
        # IDEA: Try to get the configs dir and the repo root from the search path, and call the
        # function on the config files in that directory.

        if type(self)._ALREADY_DID:
            # TODO: figure out what's causing this.
            logger.debug(f"Avoiding weird recursion in the {AutoSchemaPlugin}.")
            return
        type(self)._ALREADY_DID = True

        search_path_entries = search_path.get_path()

        # WIP: Trying to infer the project root, configs dir from the Hydra context.
        # Currently hard-coded.

        for search_path_entry in search_path_entries:
            # TODO: There are probably lots of assumptions that are specific to the
            # ResearchTemplate repo that would need to be removed / generalized before we can make
            # this a pip-installable hydra plugin..
            if search_path_entry.provider != "main":
                continue

            if search_path_entry.path.startswith("pkg://"):
                configs_pkg = search_path_entry.path.removeprefix("pkg://")
                project_package = configs_pkg.split(".")[0]
                project_package = project_package.replace("/", ".")
                logger.debug(f"Found project package: {project_package}")
                _project_module = importlib.import_module(project_package)
                # FIXME: THIS IS SPECIFIC TO THE RESEARCH TEMPLATE!
                assert (
                    _project_module.__file__
                    and Path(_project_module.__file__).name == "__init__.py"
                )
                repo_root = Path(_project_module.__file__).parent.parent

                configs_dir = repo_root / configs_pkg.replace(".", "/")
                if not (repo_root.is_dir() and configs_dir.is_dir()):
                    logger.warning(
                        f"Unable to add schemas to Hydra configs: "
                        f"Expected to find the project root directory at {repo_root} "
                        f"and the configs directory at {configs_dir}!"
                    )
                    continue
                self.fn(
                    repo_root=repo_root,
                    configs_dir=configs_dir,
                )
