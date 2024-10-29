import datetime
import json
import logging
import warnings
from pathlib import Path

import rich
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    PatternMatchingEventHandler,
)

from hydra_auto_schema.auto_schema import (
    _add_schema_header,
    _add_schemas_to_vscode_settings,
    _create_schema_for_config,
    _install_yaml_vscode_extension,
    _load_config,
    _read_json,
    add_schemas_to_all_hydra_configs,
    get_schema_file_path,
    logger,
)

from .utils import pretty_path


class AutoSchemaEventHandler(PatternMatchingEventHandler):
    debounce_interval: datetime.timedelta = datetime.timedelta(seconds=3)

    def __init__(
        self,
        repo_root: Path,
        configs_dir: Path,
        schemas_dir: Path,
        regen_schemas: bool,
        stop_on_error: bool,
        quiet: bool,
        add_headers: bool | None,
    ):
        self.configs_dir = configs_dir
        super().__init__(
            patterns=[
                f"{self.configs_dir}/**.yaml",
                f"{self.configs_dir}/**.yml",
                f"{self.configs_dir}/**/*.yaml",
                f"{self.configs_dir}/**/*.yml",
            ],
            ignore_patterns=None,
            ignore_directories=True,
            case_sensitive=True,
        )
        self.repo_root = repo_root
        self.schemas_dir = schemas_dir
        self.regen_schemas = regen_schemas
        self.stop_on_error = stop_on_error
        self.quiet = quiet
        self.add_headers = add_headers

        self._last_updated: dict[Path, datetime.datetime] = {}

        # On startup, we could make a schema for every config file, right?
        add_schemas_to_all_hydra_configs(
            repo_root=repo_root,
            configs_dir=configs_dir,
            schemas_dir=schemas_dir,
            regen_schemas=regen_schemas,
            stop_on_error=stop_on_error,
            quiet=quiet,
            add_headers=add_headers,
        )
        self.console = rich.console.Console()
        self.console.log(
            f"Watching for changes in config files in the {pretty_path(configs_dir)} directory."
        )

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        logger.debug(f"on_created event: {event.src_path}")
        if config_file := self._filter_config_file(event.src_path):
            logger.info(f"Config file was created: {config_file}")
            self.run(config_file)

    def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent) -> None:
        logger.debug(f"on_deleted event: {event.src_path}")

        # TODO: Remove the schema from the vscode settings.
        if config_file := self._filter_config_file(event.src_path):
            logger.info(f"Config file was deleted: {config_file}")
            self._remove_schema_file(config_file)

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        logger.debug(f"on_modified event: {event.src_path}")

        if config_file := self._filter_config_file(event.src_path):
            if self._debounce(config_file):
                return
            logger.info(f"Config file was modified: {config_file}")
            self.run(config_file)

    def on_moved(self, event: DirMovedEvent | FileMovedEvent) -> None:
        logger.debug(f"on_moved event: {event.src_path}")

        source_file = self._filter_config_file(event.src_path)
        dest_file = self._filter_config_file(event.dest_path)
        if source_file and dest_file:
            logger.info(f"Config file was moved from {source_file} --> {dest_file}")
            self._remove_schema_file(source_file)
            self.run(dest_file)

        if dest_file:
            self.run(dest_file)

    def _filter_config_file(self, p: str | bytes) -> Path | None:
        config_file = Path(str(p))
        if config_file.suffix not in [".yaml", ".yml"]:
            return None
        if not config_file.is_relative_to(self.configs_dir):
            return None
        return config_file

    def _debounce(self, config_file: Path) -> bool:
        """Debouncing to prevent a loop caused by us modifying the config file to add a header(?).

        TODO: Also seems to be necessary when `self.add_header` is False! Why?

        Returns:
            `True` if the file was modified recently (by us), `False` otherwise.
        """
        if config_file not in self._last_updated:
            self._last_updated[config_file] = datetime.datetime.now()
            return False

        if (
            datetime.datetime.now() - self._last_updated[config_file]
        ) < self.debounce_interval:
            logger.debug(
                f"Config file {config_file} was modified very recently; not regenerating the schema."
            )
            return True
        self._last_updated[config_file] = datetime.datetime.now()
        return False

    def run(self, config_file: Path) -> None:
        p = pretty_path(config_file)
        try:
            self._run(config_file)
        except Exception as exc:
            logger.warning(f"Error while processing config at {config_file}:\n{exc}")
            if self.stop_on_error:
                raise
            sees_warning = logger.getEffectiveLevel() <= logging.WARNING
            self.console.log(
                f"Unable to generate the schema for {p}."
                + ("" if sees_warning else " (use -v for more info).")
            )
        else:
            self.console.log(f"Schema updated for {p}.")

    def _run(self, config_file: Path) -> None:
        pretty_config_file_name = config_file.relative_to(self.configs_dir)
        schema_file = get_schema_file_path(config_file, self.schemas_dir)

        logger.debug(f"Creating a schema for {pretty_config_file_name}")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            config = _load_config(
                config_file, configs_dir=self.configs_dir, repo_root=self.repo_root
            )
        schema = _create_schema_for_config(
            config,
            config_file=config_file,
            configs_dir=self.configs_dir,
            repo_root=self.repo_root,
        )
        schema_file.parent.mkdir(exist_ok=True, parents=True)
        schema_file.write_text(json.dumps(schema, indent=2).rstrip() + "\n\n")
        # _set_is_incomplete_schema(schema_file, False)

        if not self.add_headers:
            try:
                _install_yaml_vscode_extension()
            except OSError:
                pass

            try:
                _add_schemas_to_vscode_settings(
                    {config_file: schema_file}, repo_root=self.repo_root
                )
            except Exception as exc:
                logger.error(
                    f"Unable to write schemas in the vscode settings file. "
                    f"Falling back to adding a header to config files. (exc={exc})"
                )
                if self.add_headers is not None:
                    # Unable to do it. Don't try to add headers, just return.
                    return
            else:
                # Success. Return.
                return

        logger.debug(
            "Adding a header to the config file to point to the schema to use."
        )
        _add_schema_header(config_file, schema_path=schema_file)

    def _remove_schema_file(self, config_file: Path) -> None:
        schema_file = get_schema_file_path(config_file, self.schemas_dir)
        if self.add_headers:
            # Could also remove the schema file for this config file.
            logger.debug(
                f"Removing schema file associated with config {config_file}: {schema_file}"
            )
            schema_file.unlink()
        else:
            vscode_settings_file = self.repo_root / ".vscode" / "settings.json"
            if not vscode_settings_file.exists():
                # Weird.
                return
            vscode_settings = _read_json(vscode_settings_file)
            yaml_schemas = vscode_settings.get("yaml.schemas", {})
            assert isinstance(yaml_schemas, dict)
            if not yaml_schemas:
                # Weird also!
                return
            if (
                schema_key := str(schema_file.relative_to(self.repo_root))
            ) not in yaml_schemas:
                # Weird also!
                return
            config_file_value = str(config_file)
            configs_with_schema: str | list[str] = yaml_schemas[schema_key]
            if isinstance(configs_with_schema, str):
                assert configs_with_schema == config_file_value
                # Weird!
                # Remove the schema from the dict.
                yaml_schemas.pop(schema_key)
            else:
                yaml_schemas[schema_key].remove(config_file_value)
            # NOTE: This doesn't work with comments.
            vscode_settings_file.write_text(json.dumps(vscode_settings, indent=4))
