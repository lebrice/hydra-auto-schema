import importlib
import logging
import typing
from pathlib import Path
from typing import ClassVar
import warnings

import hydra.core.plugins
import hydra_zen
from hydra.core.config_search_path import ConfigSearchPath
from hydra.core.config_store import ConfigStore  # noqa
from hydra.plugins.search_path_plugin import SearchPathPlugin

from hydra_auto_schema.auto_schema import add_schemas_to_all_hydra_configs, logger

# TODO: Perhaps this should be a different kind of plugin, one that has access to the structured
# schemas within the hydra app, so it could be executed later when calling the `hydra.main`
# function?


def register_auto_schema_plugin():
    hydra.core.plugins.Plugins.instance().register(AutoSchemaPlugin)


@hydra_zen.hydrated_dataclass(
    add_schemas_to_all_hydra_configs,
    populate_full_signature=True,
    zen_partial=True,
    zen_meta={"verbose": False, "disable": False},
)
class AutoSchemaPluginConfig:
    """Config for the AutoSchemaPlugin."""

    schemas_dir: Path | None = None
    regen_schemas: bool = False
    stop_on_error: bool = False
    quiet: bool = True
    add_headers: bool | None = False
    if typing.TYPE_CHECKING:
        # These two fields are created by hydra-zen, but aren't passed to the function.
        verbose: bool = False
        disable: bool = False


config: AutoSchemaPluginConfig | None
"""Global config used by default by the AutoSchemaPlugin."""

# is called by hydra with the plugin module (even if we've already imported it!)
# HACK: Prevent a second exec of this module from changing this value.
# This happens in the `hydra.core.plugins.Plugins._scan_all_plugins` method, in `exec_module`
if "config" not in globals():
    config = None


def configure(new_config: AutoSchemaPluginConfig) -> None:
    global config
    logger.debug(f"Setting the configuration for the AutoSchemaPlugin: {new_config}")
    config = new_config


class AutoSchemaPlugin(SearchPathPlugin):
    provider: str
    path: str

    _ALREADY_DID: ClassVar[bool] = False

    def __init__(self) -> None:
        super().__init__()
        global config
        self.config = config if config is not None else AutoSchemaPluginConfig()
        self.fn = hydra_zen.instantiate(self.config)
        self.cs = ConfigStore.instance()

        logger.debug(
            f"The AutoSchemaPlugin is being instantiated with the following config: {self.config}"
        )
        if self.config.verbose:
            from hydra_auto_schema.auto_schema import logger as _logger

            _logger.setLevel(logging.INFO)

    def manipulate_search_path(self, search_path: ConfigSearchPath) -> None:
        # IDEA: Try to get the configs dir and the repo root from the search path, and call the
        # function on the config files in that directory.
        if self.config.disable:
            return
        if type(self)._ALREADY_DID:
            # TODO: figure out what's causing this.
            logger.debug(f"Avoiding weird multiple calls to the {AutoSchemaPlugin}!")
            return
        type(self)._ALREADY_DID = True
        try:
            self.run(search_path)
        except Exception as err:
            # raise err
            warnings.warn(
                # err
                RuntimeWarning(
                    f"An error occurred while adding schemas to the Hydra configs: {err}"
                )
            )

    def run(self, search_path: ConfigSearchPath) -> None:
        # WIP: Trying to infer the project root, configs dir from the Hydra context.
        # Currently hard-coded.

        search_path_entries = search_path.get_path()
        for search_path_entry in search_path_entries:
            # TODO: There are probably lots of assumptions that are specific to the
            # ResearchTemplate repo that would need to be removed / generalized before we can make
            # this a pip-installable hydra plugin..
            logger.debug(f"search_path_entry: {search_path_entry}")
            if search_path_entry.provider != "main":
                continue

            if search_path_entry.path.startswith("pkg://"):
                configs_pkg = search_path_entry.path.removeprefix("pkg://")
                project_package = configs_pkg.split(".")[0].replace("/", ".")
                logger.debug(f"Found project package: {project_package}")
                _project_module = importlib.import_module(project_package)

                if not (
                    _project_module.__file__
                    and Path(_project_module.__file__).name == "__init__.py"
                ):
                    # TODO: Loosen this assumption, which is specific to the Mila research project template.
                    raise RuntimeError(
                        "Unable to add schemas to Hydra configs: "
                        "Expected the project package to be a package with an __init__.py file!"
                    )
                repo_root = Path(_project_module.__file__).parent.parent
                configs_dir = repo_root / configs_pkg.removeprefix(
                    repo_root.name + "/"
                ).replace(".", "/")
            else:
                # TODO: Check for file:// prefixes?
                configs_dir = Path(search_path_entry.path)
                assert configs_dir.is_dir(), configs_dir
                repo_root = configs_dir.parent  # wild assumption, no?

            if not (repo_root.is_dir() and configs_dir.is_dir()):
                raise RuntimeError(
                    f"Unable to add schemas to Hydra configs: "
                    f"Expected to find the project root directory at {repo_root} "
                    f"and the configs directory at {configs_dir}!\n"
                    f"({repo_root.is_dir()=} and {configs_dir.is_dir()=})"
                )
            self.fn(
                repo_root=repo_root,
                configs_dir=configs_dir,
                config_store=self.cs,
            )
