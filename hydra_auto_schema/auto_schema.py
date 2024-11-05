"""Scripts that creates Schemas for hydra config files.

This is very helpful when using Hydra! It shows the user what options are available, along with their
description and default values, and displays errors if you have config files with invalid values.

## todos
- [ ] Support '???' as a value for any property.
- [ ] Modify the schema to support omegaconf directives like ${oc.env:VAR_NAME} and our custom directives like ${instance_attr} and so on.
- [ ] todo: Make a hydra plugin that creates the schemas for configs when hydra is loading stuff.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import inspect
import json
import os.path
import subprocess
import sys
import typing
import warnings
from collections.abc import Callable, MutableMapping
from logging import getLogger as get_logger
from pathlib import Path
from typing import Any, TypeVar

import docstring_parser as dp
import hydra.conf
import hydra.errors
import hydra.plugins
import hydra.utils
import hydra_zen
import omegaconf
import pydantic
import pydantic.schema
import tqdm
from hydra._internal.config_loader_impl import ConfigLoaderImpl
from hydra._internal.config_search_path_impl import ConfigSearchPathImpl
from hydra.core.config_search_path import ConfigSearchPath
from hydra.core.config_store import ConfigNode, ConfigStore
from hydra.core.plugins import Plugins
from hydra.plugins.search_path_plugin import SearchPathPlugin
from hydra.types import RunMode
from omegaconf import DictConfig, OmegaConf
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import core_schema
from tqdm.rich import tqdm_rich

from hydra_auto_schema.customize import custom_enum_schemas, special_handlers
from hydra_auto_schema.hydra_schema import (
    HYDRA_CONFIG_SCHEMA,
    ObjectSchema,
    PropertySchema,
    Schema,
)
from hydra_auto_schema.utils import pretty_path

logger = get_logger(__name__)

config = None

K = TypeVar("K")
V = TypeVar("V")
PossiblyNestedDict = dict[K, V | "PossiblyNestedDict[K, V]"]


def _yaml_files_in(configs_dir: Path) -> list[Path]:
    # Ignores .venv subfiles if the `configs_dir` isn't itself in a ".venv" directory.
    if ".venv" in configs_dir.parts:
        return list(configs_dir.rglob("*.yaml")) + list(configs_dir.rglob("*.yml"))
    return list(
        p for p in configs_dir.rglob("*.yaml") if ".venv" not in p.parts
    ) + list(p for p in configs_dir.rglob("*.yml") if ".venv" not in p.parts)


def add_schemas_to_all_hydra_configs(
    repo_root: Path,
    configs_dir: Path,
    schemas_dir: Path | None = None,
    regen_schemas: bool = False,
    stop_on_error: bool = False,
    quiet: bool = False,
    add_headers: bool | None = False,
    config_store: ConfigStore | None = None,
):
    """Adds schemas to all the passed Hydra config files.

    Parameters:
        repo_root: The root directory of the repository.
        configs_dir: The directory containing the Hydra config files.
        schemas_dir: The directory to store the generated schema files. Defaults to ".schemas" in the repo_root.
        regen_schemas: If True, regenerate schemas even if they already exist. Defaults to False.
        stop_on_error: If True, raise an exception on error. Defaults to False.
        quiet: If True, suppress progress bar output. Defaults to False.
        add_headers: Determines how to associate schema files with config files.

            - If None, try adding to VSCode settings first, then fallback to adding headers.
            - If False, only use VSCode settings.
            - If True, only add headers.
    """
    config_store = config_store or ConfigStore.instance()
    config_files = _yaml_files_in(configs_dir)
    if not config_files:
        if stop_on_error:
            raise RuntimeError("No config files were found!")
        else:
            warnings.warn(RuntimeWarning("No config files were found! Skipping."))
        # return

    if schemas_dir is None:
        schemas_dir = repo_root / ".schemas"

    if schemas_dir.is_relative_to(repo_root):
        _add_schemas_dir_to_gitignore(schemas_dir, repo_root=repo_root)

    config_file_to_schema_file: dict[Path, Path] = {}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=tqdm.TqdmExperimentalWarning)
        pbar = tqdm_rich(
            config_files,
            desc="Creating schemas for Hydra config files...",
            total=len(config_files),
            leave=False,
            disable=quiet,
        )

    for config_file in pbar:
        pretty_config_file_name = config_file.relative_to(configs_dir)
        schema_file = get_schema_file_path(config_file, schemas_dir)

        # Check the modification time. If the config file was modified after the schema file,
        # regen the schema file.

        if schema_file.exists():
            schema_file_modified_time = datetime.datetime.fromtimestamp(
                schema_file.stat().st_mtime
            )
            config_file_modified_time = datetime.datetime.fromtimestamp(
                config_file.stat().st_mtime
            )
            # Add a delay to account for the time it takes to modify the the config file at the end
            # to remove a header.
            if (
                config_file_modified_time - schema_file_modified_time
            ) > datetime.timedelta(seconds=10):
                logger.info(
                    f"Config file {pretty_config_file_name} was modified, regenerating the schema."
                )
            elif regen_schemas:
                pass  # regenerate it.
            elif sys.platform == "linux" and _is_incomplete_schema(schema_file):
                logger.info(
                    f"Unable to properly create the schema for {pretty_config_file_name} last time. Trying again."
                )
            else:
                logger.debug(
                    f"Schema file {pretty_path(schema_file)} was already successfully created. Skipping."
                )
                continue

        pbar.set_postfix_str(f"Creating schema for {pretty_config_file_name}")

        # We'll modify the config store so that we treat structured configs as if they
        # had a _target_ corresponding to the structured class.
        # This helps us create the schemas.
        # We later reset this to not affect the config loading in the Hydra application.
        from hydra.core.singleton import Singleton  # noqa

        state_backup = Singleton.get_state()

        try:
            logger.debug(f"Creating a schema for {pretty_config_file_name}")

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                # TODO: Can we somehow get that the ConfigStore entries should
                # be used as targets?
                #     Singleton._instances.pop(ConfigStore)
                # else:
                # Maybe using the _convert_ param of Hydra?
                config = load_config(
                    config_file,
                    configs_dir=configs_dir,
                    repo_root=repo_root,
                    config_store=config_store,
                )
            schema = _create_schema_for_config(
                config,
                config_file=config_file,
                configs_dir=configs_dir,
                repo_root=repo_root,
                config_store=config_store,
            )
            schema_file.parent.mkdir(exist_ok=True, parents=True)
            schema_file.write_text(json.dumps(schema, indent=2).rstrip() + "\n\n")
            if sys.platform == "linux":
                _set_is_incomplete_schema(schema_file, False)
        except (
            pydantic.errors.PydanticSchemaGenerationError,
            hydra.errors.MissingConfigException,
            hydra.errors.ConfigCompositionException,
            omegaconf.errors.InterpolationResolutionError,
            Exception,  # todo: remove this to harden the code.
        ) as exc:
            logger.warning(
                RuntimeWarning(
                    f"Unable to create a schema for config {pretty_config_file_name}: {exc}"
                )
            )
            if stop_on_error:
                raise

            schema = copy.deepcopy(HYDRA_CONFIG_SCHEMA)
            schema["additionalProperties"] = True
            schema["title"] = f"Partial schema for {pretty_config_file_name}"
            schema[
                "description"
            ] = f"(errors occurred while trying to create the schema from the signature:\n{exc}"
            schemas_dir.mkdir(exist_ok=True, parents=True)
            schema_file.write_text(json.dumps(schema, indent=2) + "\n")
            if sys.platform == "linux":
                _set_is_incomplete_schema(schema_file, True)
        finally:
            # Reset the config store / search path / etc to what they were before.
            Singleton.set_state(state_backup)

        config_file_to_schema_file[config_file] = schema_file

    # Option 1: Add a vscode setting that associates the schema file with the yaml files. (less intrusive perhaps).
    # Option 2: Add a header to the yaml files that points to the schema file.

    # If add_headers is None, try option 1, then fallback to option 2.
    # If add_headers is False, only use option 1
    # If add_headers is True, only use option 2

    if not add_headers:
        try:
            _install_yaml_vscode_extension()
        except OSError:
            pass

        try:
            _add_schemas_to_vscode_settings(
                config_file_to_schema_file, repo_root=repo_root
            )
        except Exception as exc:
            logger.error(
                f"Unable to write schemas in the vscode settings file. "
                f"Falling back to adding a header to config files. (exc={exc})"
            )
            if add_headers is not None:
                # Unable to do it. Don't try to add headers, just return.
                return
        else:
            # Success. Return.
            return

    logger.debug("Adding headers to config files to point to the schemas to use.")
    for config_file, schema_file in config_file_to_schema_file.items():
        _add_schema_header(config_file, schema_path=schema_file)


def _get_gitignore_path(repo_root: Path) -> Path:
    for parent in repo_root.parents:
        if (gitignore_file := (parent / ".gitignore")).exists():
            return gitignore_file
    return repo_root / ".gitignore"


def _add_schemas_dir_to_gitignore(schemas_dir: Path, repo_root: Path):
    gitignore_file = _get_gitignore_path(repo_root)
    if not schemas_dir.is_relative_to(gitignore_file.parent):
        # The schemas dir is not under the same directory as the gitignore file, so we can't add it.
        return

    _rel = schemas_dir.relative_to(gitignore_file.parent)
    if not gitignore_file.exists():
        gitignore_file.write_text(f"{_rel}\n")
        return
    if not any(
        line.startswith(str(_rel)) for line in gitignore_file.read_text().splitlines()
    ):
        logger.info(
            f"Adding entry in .gitignore for the schemas directory ({schemas_dir})"
        )
        with gitignore_file.open("a") as f:
            f.write(f"{_rel}\n")


_incomplete_schema_xattr = "user.schema_error"


def _is_incomplete_schema(schema_file: Path) -> bool:
    try:
        return os.getxattr(schema_file, _incomplete_schema_xattr) == bytes(1)
    except OSError:
        return False


def _set_is_incomplete_schema(schema_file: Path, val: bool):
    os.setxattr(schema_file, _incomplete_schema_xattr, bytes(val))


def _relative_to_cwd(p: str | Path):
    return Path(p).relative_to(Path.cwd())


def _install_yaml_vscode_extension():
    logger.debug(
        "Running `code --install-extension redhat.vscode-yaml` to install the yaml extension for vscode."
    )
    output = subprocess.check_output(
        ("code", "--install-extension", "redhat.vscode-yaml"), text=True
    )
    logger.debug(output)


def _read_json(file: Path) -> dict:
    file_contents = file.read_text()
    if not file_contents:
        return {}
    # Remove any trailing commas from the content:
    file_contents = (
        # Remove any trailing "," that would make it invalid JSON.
        "".join(file_contents.split()).replace(",}", "}").replace(",]", "]")
    )
    return json.loads(file_contents)


def _add_schemas_to_vscode_settings(
    config_file_to_schema_file: dict[Path, Path],
    repo_root: Path,
) -> None:
    # Make the vscode settings file if necessary:
    vscode_dir = repo_root / ".vscode"
    vscode_dir.mkdir(exist_ok=True, parents=False)
    vscode_settings_file = vscode_dir / "settings.json"
    vscode_settings_file.touch(exist_ok=True)

    # TODO: Use Jsonc to load the file and preserve comments?
    logger.debug(f"Reading the VsCode settings file at {vscode_settings_file}.")
    vscode_settings: dict[str, Any] = _read_json(vscode_settings_file)

    # logger.debug(f"Vscode settings: {vscode_settings}")
    # Avoid the popup and do users a favour by disabling telemetry.
    vscode_settings.setdefault("redhat.telemetry.enabled", False)

    # TODO: Should probably overwrite the schemas entry if we're passed the --regen-schemas flag,
    # since otherwise we might accumulate schemas for configs that aren't there anymore.
    yaml_schemas_setting: dict[str, str | list[str]] = vscode_settings.setdefault(
        "yaml.schemas", {}
    )

    # Write all the schemas
    for config_file, schema_file in config_file_to_schema_file.items():
        assert schema_file.exists()

        _root = vscode_settings_file.parent.parent
        schema_key = str(schema_file.relative_to(_root))
        path_to_add = str(config_file.absolute())

        if schema_key not in yaml_schemas_setting:
            yaml_schemas_setting[schema_key] = path_to_add
        elif isinstance(
            files_associated_with_schema := yaml_schemas_setting[schema_key], str
        ):
            files = sorted(set([files_associated_with_schema, path_to_add]))
            yaml_schemas_setting[schema_key] = files[0] if len(files) == 1 else files
        else:
            files = sorted(set(files_associated_with_schema + [path_to_add]))
            yaml_schemas_setting[schema_key] = files[0] if len(files) == 1 else files

    vscode_settings_file.write_text(json.dumps(vscode_settings, indent=2))
    logger.debug(
        f"Updated the yaml schemas in the vscode settings file at {vscode_settings_file}."
    )

    # If this worked, then remove any schema directives from the config files.
    for config_file, schema_file in config_file_to_schema_file.items():
        assert schema_file.exists()
        config_lines = config_file.read_text().splitlines()
        lines_to_remove: list[int] = []
        for i, line in enumerate(config_lines):
            if line.strip().startswith("# yaml-language-server: $schema="):
                lines_to_remove.append(i)
        for line_to_remove in reversed(lines_to_remove):
            config_lines.pop(line_to_remove)
        config_file.write_text(
            "\n".join(config_lines).rstrip() + ("\n" if config_lines else "")
        )


def get_schema_file_path(config_file: Path, schemas_dir: Path):
    config_group = config_file.parent
    schema_file = schemas_dir / f"{config_group.name}_{config_file.stem}_schema.json"
    return schema_file


def _all_subentries_with_target(config: dict) -> dict[tuple[str, ...], dict]:
    """Iterator that yields all the nested config entries that have a _target_."""
    entries = {}
    if "_target_" in config:
        entries[()] = config

    for key, value in config.items():
        if isinstance(value, dict):
            for subkey, subvalue in _all_subentries_with_target(value).items():
                entries[(key, *subkey)] = subvalue
    return entries


def _create_schema_for_config(
    config: dict | DictConfig,
    config_file: Path,
    configs_dir: Path,
    repo_root: Path,
    config_store: ConfigStore | None,
) -> Schema | ObjectSchema:
    """IDEA: Create a schema for the given config.

    - If you encounter a key, add it to the schema.
    - If you encounter a value with a _target_, use a dedicated function to get the schema for that target, and merge it into the current schema.
    - Only the top-level config (`config`) can have a `defaults: list[str]` key.
        - Should ideally load the defaults and merge this schema on top of them.
    """

    # Start from the base schema for any Hydra configs.
    schema = copy.deepcopy(HYDRA_CONFIG_SCHEMA)

    pretty_path = config_file.relative_to(configs_dir) if configs_dir else config_file
    schema["title"] = f"Auto-generated schema for {pretty_path}"

    # NOTE: Config files can also not have a target.
    # This sets additionalProperties to `false` if there is a structured config in the defaults
    # list, since `schema` will have been given a `_target_` above.
    schema["additionalProperties"] = "_target_" not in config and (
        "const" not in schema["properties"].get("_target_", {})
    )
    _config_dict = (
        OmegaConf.to_container(config, resolve=False)
        if isinstance(config, DictConfig)
        else config
    )
    assert isinstance(_config_dict, dict)
    for keys, value in _all_subentries_with_target(_config_dict).items():
        is_top_level: bool = not keys

        # logger.debug(f"Handling key {'.'.join(keys)} in config at path {config_file}")

        nested_value_schema = _get_schema_from_target(value)

        if "$defs" in nested_value_schema:
            # note: can't have a $defs key in the schema.
            schema.setdefault("$defs", {}).update(  # type: ignore
                nested_value_schema.pop("$defs")
            )
            assert "properties" in nested_value_schema

        if is_top_level:
            schema = _merge_dicts(
                schema, nested_value_schema, conflict_handler=_overwrite
            )
            continue

        parent_keys, last_key = keys[:-1], keys[-1]
        where_to_set: Schema | ObjectSchema = schema
        for key in parent_keys:
            where_to_set = where_to_set.setdefault("properties", {}).setdefault(
                key, {"type": "object"}
            )  # type: ignore
            if "_target_" not in where_to_set:
                where_to_set["additionalProperties"] = True

        # logger.debug(f"Using schema from nested value at keys {keys}: {nested_value_schema}")

        if "properties" not in where_to_set:
            where_to_set["properties"] = {last_key: nested_value_schema}  # type: ignore
        elif last_key not in where_to_set["properties"]:
            assert isinstance(last_key, str)
            where_to_set["properties"][last_key] = nested_value_schema  # type: ignore
        else:
            where_to_set["properties"] = _merge_dicts(  # type: ignore
                where_to_set["properties"],
                {last_key: nested_value_schema},  # type: ignore
                conflict_handler=_overwrite,
            )

    return schema


def _update_schema_from_defaults(
    config_file: Path,
    schema: Schema,
    defaults: list[str | dict[str, str]],
    configs_dir: Path,
    repo_root: Path,
    config_store: ConfigStore | None,
):
    defaults_list = defaults
    config_store = config_store or ConfigStore.instance()

    for default in defaults_list:
        if default == "_self_":  # todo: does this actually make sense?
            continue
        # Note: The defaults can also have the .yaml or .yml extension, _load_config drops the
        # extension.
        default_config, default_config_file = load_default_config(
            config_file=config_file,
            configs_dir=configs_dir,
            default=default,
            repo_root=repo_root,
        )

        if "_target_" not in default_config:
            object_type = default_config._metadata.object_type
            logger.debug(f"{default=} {object_type=}")
            # TODO: if `object_type` is `dict`, this *may* be because the default config is:
            # {some_key: {some_value: thing_from_default}}
            if object_type is not dict:
                # todo: Figure out other examples where the object type is `dict` than the one above:
                # For now here we assume that the target is the same as the current one. Don't add one.
                # TODO: Need to check what the default is for object_type when `default_config` is not
                # a structured config.
                with omegaconf.open_dict(default_config):
                    default_config["_target_"] = (
                        object_type.__module__ + "." + object_type.__qualname__
                    )

        schema_of_default = _create_schema_for_config(
            config=default_config,
            # TODO: Something wrong about the `default_config_file` here. If the default
            # is something like {"a": {"b": some_config}} and default_config_file is "{config_dir/a/b/some_config}",
            # We shouldn't just recurse infinitely though!
            config_file=(
                default_config_file if isinstance(default, str) else config_file
            ),
            configs_dir=configs_dir,
            repo_root=repo_root,
            config_store=config_store,
        )
        # SUPER VERBOSE:
        # logger.debug(f"Schema from default {default}: {schema_of_default}")
        # logger.debug(
        #     f"Properties of {default=}: {list(schema_of_default['properties'].keys())}"
        # )  # type: ignore

        schema = _merge_dicts(  # type: ignore
            schema_of_default,  # type: ignore
            schema,  # type: ignore
            conflict_handler=_overwrite,
            # conflict_handlers={
            #     "_target_": _overwrite,  # use the new target.
            #     "_target_.const": _overwrite,  # use the new target.
            #     "default": _overwrite,  # use the new default?
            #     "title": _overwrite,
            #     "description": _overwrite,
            # },
        )
        # todo: deal with this one here.
        if schema.get("additionalProperties") is False:
            schema.pop("additionalProperties")
    return schema


def load_default_config(
    config_file: Path,
    configs_dir: Path,
    default: str | dict[str, str],
    repo_root: Path,
) -> tuple[DictConfig, Path]:
    """Loads the config pointed to by the given "defaults" entry in this config file.

    https://hydra.cc/docs/advanced/defaults_list/
    """
    assert "@" not in default  # TODO!

    if isinstance(default, str):
        assert not default.startswith("/")  # TODO!
        other_config_path = config_file.parent / default
    else:
        # TODO: It's more complicated that that! We need to also apply the default at the entry.
        # BUG: "override /db: something" should put the schema for `something` at key `db`!
        assert len(default) == 1
        key, val = next(iter(default.items()))
        key = key.removeprefix("override ")
        key = key.removeprefix("optional ")
        key = key.strip()
        assert key
        where_to_set = key.removeprefix("/").split("/")
        if key.startswith("/"):
            other_config_path = configs_dir / key.removeprefix("/") / val
        else:
            other_config_path = config_file.parent / key / val

        logger.debug(
            f"Loading config of default {default} with 'path': {pretty_path(other_config_path)}"
        )

        if not other_config_path.suffix:
            # If the other config file has the name without the extension, try both .yml and .yaml.
            for suffix in (".yml", ".yaml"):
                if other_config_path.with_suffix(suffix).exists():
                    other_config_path = other_config_path.with_suffix(suffix)
                    break
        default_config = load_config(
            other_config_path,
            configs_dir=configs_dir,
            repo_root=repo_root,
            config_store=ConfigStore.instance(),
        )
        assert where_to_set
        # if not where_to_set:
        #     return default_config, other_config_path

        default_config_result = {}
        result = default_config_result
        for i, parent in enumerate(where_to_set):
            if i == len(where_to_set) - 1:
                result[parent] = default_config
            else:
                result[parent] = {}
            result = result[parent]
        default_config = OmegaConf.create(default_config_result)
        logger.info(f"{default=}, {where_to_set=}, {default_config=}")
        # logger.info(f"{default_config=}, {where_to_set=}")
        return default_config, other_config_path

    logger.debug(
        f"Loading config of default {default} with 'path': {pretty_path(other_config_path)}"
    )

    if not other_config_path.suffix:
        # If the other config file has the name without the extension, try both .yml and .yaml.
        for suffix in (".yml", ".yaml"):
            if other_config_path.with_suffix(suffix).exists():
                other_config_path = other_config_path.with_suffix(suffix)
                break
    default_config = load_config(
        other_config_path,
        configs_dir=configs_dir,
        repo_root=repo_root,
        config_store=ConfigStore.instance(),
    )
    return (
        default_config,
        other_config_path,
    )


def _overwrite(val_a: Any, val_b: Any) -> Any:
    return val_b


def _keep_previous(val_a: Any, val_b: Any) -> Any:
    return val_a


conflict_handlers: dict[str, Callable[[Any, Any], Any]] = {}

_K = TypeVar("_K")
_V = TypeVar("_V")
_NestedDict = MutableMapping[_K, _V | "_NestedDict[_K, _V]"]

_D1 = TypeVar("_D1", bound=_NestedDict)
_D2 = TypeVar("_D2", bound=_NestedDict)


def _merge_dicts(
    a: _D1,
    b: _D2,
    path: list[str] = [],
    conflict_handlers: dict[str, Callable[[Any, Any], Any]] = conflict_handlers,
    conflict_handler: Callable[[Any, Any], Any] | None = None,
) -> _D1 | _D2:
    """Merge two nested dictionaries.

    >>> x = dict(b=1, c=dict(d=2, e=3))
    >>> y = dict(d=3, c=dict(z=2, f=4))
    >>> _merge_dicts(x, y)
    {'b': 1, 'c': {'d': 2, 'e': 3, 'z': 2, 'f': 4}, 'd': 3}
    >>> x
    {'b': 1, 'c': {'d': 2, 'e': 3}}
    >>> y
    {'d': 3, 'c': {'z': 2, 'f': 4}}
    """
    out = copy.deepcopy(a)
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                out[key] = _merge_dicts(
                    a[key],
                    b[key],
                    path + [str(key)],
                    conflict_handlers={
                        k.removeprefix(f"{key}."): v
                        for k, v in conflict_handlers.items()
                    },
                    conflict_handler=conflict_handler,
                )
            elif a[key] != b[key]:
                if specific_conflict_handler := conflict_handlers.get(key):
                    out[key] = specific_conflict_handler(a[key], b[key])  # type: ignore
                elif conflict_handler:
                    out[key] = conflict_handler(a[key], b[key])  # type: ignore

                # if any(key.split(".")[-1] == handler_name for  for prefix in ["_", "description", "title"]):
                #     out[key] = b[key]
                else:
                    raise Exception("Conflict at " + ".".join(path + [str(key)]))
        else:
            out[key] = copy.deepcopy(b[key])  # type: ignore
    return out


def _has_package_global_line(config_file: Path) -> int | None:
    """Returns whether the config file contains a `@package _global_` directive of hydra.

    See: https://hydra.cc/docs/advanced/overriding_packages/#overriding-the-package-via-the-package-directive
    """
    for line in config_file.read_text().splitlines():
        line = line.strip()
        if not line.startswith("#"):
            continue
        if line.removeprefix("#").strip().startswith("@package _global_"):
            return True
    return False


# def _config_is_in_config_store(config_path: Path, config_store: ConfigStore) -> bool:
#     return config_store._open(str(config_path)) is not None


def _try_load_from_config_store(
    config_path: Path, configs_dir: Path, config_store: ConfigStore
) -> DictConfig | None:
    config_path = config_path.relative_to(configs_dir)

    def _config_is_in_config_store(config_path: Path) -> bool:
        return config_store._open(str(config_path)) is not None

    if _config_is_in_config_store(with_yml := config_path.with_suffix(".yml")):
        return config_store.load(str(with_yml)).node

    if _config_is_in_config_store(with_yaml := config_path.with_suffix(".yaml")):
        return config_store.load(str(with_yaml)).node

    return None


# NOTE: Tried to use `functools.cache` to prevent this from loading the plugins again, doesn't work
# import hydra._internal.utils
# hydra._internal.utils.create_config_search_path = functools.cache(
#     hydra._internal.utils.create_config_search_path
# )


# @functools.cache
def _create_config_search_path(search_path_dir: str | None) -> ConfigSearchPath:
    search_path = ConfigSearchPathImpl()
    search_path.append("hydra", "pkg://hydra.conf")

    if search_path_dir is not None:
        search_path.append("main", search_path_dir)

    search_path_plugins = Plugins.instance().discover(SearchPathPlugin)
    for spp in search_path_plugins:
        # CHANGED this, to avoid the weird re-instantiation of our plugin type.
        from hydra_plugins.auto_schema import auto_schema_plugin

        if spp is auto_schema_plugin.AutoSchemaPlugin:
            continue
        # TODO: This will still call all the other plugins once per call to this function!
        plugin = spp()
        assert isinstance(plugin, SearchPathPlugin)
        plugin.manipulate_search_path(search_path)

    search_path.append("schema", "structured://")

    return search_path


def load_config(
    config_path: Path,
    configs_dir: Path,
    repo_root: Path,
    config_store: ConfigStore,
) -> DictConfig:
    """Super overly-complicated function that tries to load a Hydra configuration file.

    This is in large part because Hydra's internal code is *very* complicated.
    """

    def _set_node_target(entry: ConfigNode | PossiblyNestedDict[str, ConfigNode]):
        if isinstance(entry, dict):
            for _key, value in entry.items():
                _set_node_target(value)
            return
        if "_target_" in entry.node:
            return

        target = entry.node._metadata.object_type
        if target is dict:
            assert entry.name == "_dummy_empty_config_.yaml"
            return

        logger.debug(
            f"Setting target for structured config node {entry.name} to {target}"
        )
        with omegaconf.open_dict(entry.node):
            target = f"{target.__module__}.{target.__qualname__}"
            entry.node["_target_"] = target

    for _key, entry in config_store.repo.items():
        _set_node_target(entry)

    if config := _try_load_from_config_store(
        config_path, configs_dir=configs_dir, config_store=config_store
    ):
        return config

    *config_groups, config_name = (
        config_path.relative_to(configs_dir).with_suffix("").parts
    )
    logger.debug(
        f"config_path: ./{pretty_path(config_path)}, {config_groups=}, {config_name=}, configs_dir: {configs_dir}"
    )
    config_group = "/".join(config_groups)

    from hydra.core.utils import setup_globals

    # todo: When would this normally be called?
    setup_globals()

    # FIXME!
    if configs_dir.is_relative_to(repo_root) and (configs_dir / "__init__.py").exists():
        config_module = str(configs_dir.relative_to(repo_root)).replace("/", ".")
        search_path = _create_config_search_path(f"pkg://{config_module}")
        logger.debug(f"Search path for a config module: {search_path}")
    else:
        search_path = _create_config_search_path(str(configs_dir))
        logger.debug(f"Search path for a config dir: {search_path}")

    config_loader = ConfigLoaderImpl(config_search_path=search_path)
    from hydra._internal.core_plugins.structured_config_source import (
        StructuredConfigSource,  # noqa
    )

    logger.debug(f"loading config {config_path}")

    # assert isinstance(
    #     schema_source := config_loader.repository.get_schema_source(),
    #     StructuredConfigSource,
    # )
    # assert False, schema_source.load_config(str(config_path))

    if _has_package_global_line(config_path):
        # Tricky: Here we load the global config but with the given config as an override.
        top_config = config_loader.load_configuration(
            "config",  # todo: Fix this!!
            overrides=[f"{config_group}={config_name}"],
            # todo: setting this here because it appears to be what's used in Hydra in a normal
            # run, even though RunMode.RUN would make more sense intuitively.
            run_mode=RunMode.MULTIRUN,
        )
        return top_config

    # Load the global config and get the node for the desired config.
    with warnings.catch_warnings():
        config_to_load = f"{config_group}/{config_name}"
        # if config_path.name == "config.yaml":
        #     # Make sure not to load the (base) Hydra config file that is also called `config.yaml`!
        #     config_to_load = str(config_path)
        warnings.simplefilter("ignore", category=UserWarning)
        top_config = config_loader.load_configuration(
            config_to_load,
            overrides=[],
            run_mode=RunMode.MULTIRUN,
            validate_sweep_overrides=False,
        )
    # Retrieve the sub-entry in the config and return it.
    config = top_config
    for config_group in config_groups:
        config = config[config_group]
    return config


def _add_schema_header(config_file: Path, schema_path: Path) -> None:
    """Add a comment in the yaml config file to tell yaml language server where to look for the
    schema.

    Importantly in the context of Hydra, this comment line should be added **after** any `#
    @package: <xyz>` directives of Hydra, otherwise Hydra doesn't use those directives properly
    anymore.
    """
    lines = config_file.read_text().splitlines(keepends=False)

    if config_file.parent is schema_path.parent:
        # TODO: Unsure when this branch would be used, and if it would differ.
        relative_path_to_schema = "./" + schema_path.name
    else:
        relative_path_to_schema = os.path.relpath(schema_path, start=config_file.parent)

    # Remove any existing schema lines.
    lines = [
        line
        for line in lines
        if not line.strip().startswith("# yaml-language-server: $schema=")
    ]

    # NOTE: This line can be placed anywhere in the file, not necessarily needs to be at the top,
    # and the yaml vscode extension will pick it up.
    new_line = f"# yaml-language-server: $schema={relative_path_to_schema}"

    package_global_line: int | None = None

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        # BUG: IF the schema line comes before a @package: global comment, then the @package: _global_
        # comment is ignored by Hydra.
        # Locate the last package line (a bit unnecessary, since there should only be one).
        if line.startswith("#") and line.removeprefix("#").strip().startswith(
            "@package"
        ):
            package_global_line = i

    if package_global_line is None:
        # There's no package directive in the file.
        new_lines = [new_line, *lines]
    else:
        new_lines = lines.copy()
        # Insert the schema line after the package directive line.
        new_lines.insert(package_global_line + 1, new_line)

    result = "\n".join(new_lines).strip() + "\n"
    if config_file.read_text() != result:
        config_file.write_text(result)


def _get_dataclass_from_target(target: Any, config: dict | DictConfig) -> type:
    if inspect.isclass(target) and target in special_handlers:
        special_kwargs = special_handlers[target]
        kwargs = _merge_dicts(
            dict(
                populate_full_signature=True,
                hydra_recursive=False,
                hydra_convert="all",
                zen_dataclass={"cls_name": target.__qualname__},
            ),
            special_kwargs,
        )
        # Generate the dataclass dynamically with hydra-zen.
        return hydra_zen.builds(target, **kwargs)
    if dataclasses.is_dataclass(target):
        # The target is a dataclass, so the schema is just the schema of the dataclass.
        assert inspect.isclass(target)
        return target
    # The target is a type or callable.
    assert callable(target)
    return hydra_zen.builds(
        target,
        populate_full_signature=True,
        hydra_defaults=config.get("defaults", None),
        hydra_recursive=False,
        hydra_convert="all",
        zen_dataclass={"cls_name": target.__qualname__.replace(".", "_")},
        # zen_wrappers=pydantic_parser,  # unsure if this is how it works?
    )


def _get_schema_from_target(config: dict | DictConfig) -> ObjectSchema | Schema:
    assert isinstance(config, dict | DictConfig)
    # logger.debug(f"Config: {config}")
    target = hydra.utils.get_object(config["_target_"])

    object_type = _get_dataclass_from_target(target=target, config=config)

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)

            json_schema = pydantic.TypeAdapter(object_type).json_schema(
                mode="serialization",
                schema_generator=_MyGenerateJsonSchema,
                by_alias=False,
            )
            json_schema = typing.cast(Schema, json_schema)
        assert "properties" in json_schema
    except pydantic.PydanticSchemaGenerationError as e:
        raise NotImplementedError(f"Unable to get the schema with pydantic: {e}")

    assert "properties" in json_schema

    # Add a description
    json_schema["description"] = (
        f"Based on the signature of {target}.\n" + json_schema.get("description", "")
    )

    docs_to_search: list[dp.Docstring] = []

    if inspect.isclass(target):
        for target_or_base_class in inspect.getmro(target):
            if class_docstring := inspect.getdoc(target_or_base_class):
                docs_to_search.append(dp.parse(class_docstring))
            if init_docstring := inspect.getdoc(target_or_base_class.__init__):
                docs_to_search.append(dp.parse(init_docstring))
    else:
        assert inspect.isfunction(target) or inspect.ismethod(target), target
        docstring = inspect.getdoc(target)
        if docstring:
            docs_to_search = [dp.parse(docstring)]

    param_descriptions: dict[str, str] = {}
    for doc in docs_to_search:
        for param in doc.params:
            if param.description and param.arg_name not in param_descriptions:
                param_descriptions[param.arg_name] = param.description

    # Update the pydantic schema with descriptions:
    for property_name, property_dict in json_schema["properties"].items():
        if description := param_descriptions.get(property_name):
            property_dict["description"] = description
        else:
            property_dict[
                "description"
            ] = f"The {property_name} parameter of the {target.__qualname__}."

    if config.get("_partial_"):
        json_schema["required"] = []
    # Add some info on the target.
    if "_target_" not in json_schema["properties"]:
        json_schema["properties"]["_target_"] = {}
    else:
        assert isinstance(json_schema["properties"]["_target_"], dict)
    json_schema["properties"]["_target_"].update(
        PropertySchema(  # type: ignore
            type="string",
            title="Target",
            const=config["_target_"],
            # pattern=r"", # todo: Use a pattern to match python module import strings.
            description=(
                f"Target to instantiate, in this case: `{target}`\n"
                # f"* Source: <file://{relative_to_cwd(inspect.getfile(target))}>\n"
                # f"* Config file: <file://{config_file}>\n"
                f"See the Hydra docs for '_target_': https://hydra.cc/docs/advanced/instantiate_objects/overview/\n"
            ),
        )
    )

    # if the target takes **kwargs, then we don't restrict additional properties.
    json_schema["additionalProperties"] = (
        inspect.getfullargspec(target).varkw is not None
    )

    return json_schema


def _target_has_var_kwargs(config: DictConfig) -> bool:
    target = hydra_zen.get_target(config)  # type: ignore
    return inspect.getfullargspec(target).varkw is None


class _MyGenerateJsonSchema(GenerateJsonSchema):
    # def handle_invalid_for_json_schema(
    #     self, schema: core_schema.CoreSchema, error_info: str
    # ) -> JsonSchemaValue:
    #     raise PydanticOmit

    def enum_schema(self, schema: core_schema.EnumSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches an Enum value.

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        enum_type = schema["cls"]
        logger.debug(f"Enum of type {enum_type}")
        if custom_handler := custom_enum_schemas.get(enum_type):
            schema = custom_handler(enum_type, schema)
        return super().enum_schema(schema)
