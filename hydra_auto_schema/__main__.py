import argparse
import logging
import os
import sys
import time
from pathlib import Path

import rich.logging
from watchdog.observers import Observer

from hydra_auto_schema.auto_schema import add_schemas_to_all_hydra_configs, logger
from hydra_auto_schema.filewatcher import AutoSchemaEventHandler


def main(argv: list[str] | None = None):
    logging.basicConfig(
        level=logging.ERROR,
        # format="%(asctime)s - %(levelname)s - %(message)s",
        format="%(message)s",
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

    parser = argparse.ArgumentParser()
    parser.add_argument("repo_root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument(
        "--configs_dir",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "The directory containing hydra config files for which schemas should be generated. "
            "If unset, this will default to the first directory called 'configs' in the repo root."
        ),
    )
    parser.add_argument("--schemas-dir", type=Path, default=Path.cwd() / ".schemas")
    parser.add_argument("--regen-schemas", action=argparse.BooleanOptionalAction)
    parser.add_argument("--stop-on-error", action=argparse.BooleanOptionalAction)
    parser.add_argument("--watch", action=argparse.BooleanOptionalAction)
    parser.add_argument(
        "--add-headers",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Always add headers to the yaml config files, instead of the default "
            "behaviour which is to first try to add an entry in the vscode "
            "settings.json file."
        ),
    )
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "-q", "--quiet", dest="quiet", action=argparse.BooleanOptionalAction
    )
    verbosity_group.add_argument(
        "-v", "--verbose", dest="verbose", action="count", default=0
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configs_dir: Path | None = args.configs_dir
    schemas_dir: Path = args.schemas_dir
    repo_root: Path = args.repo_root
    regen_schemas: bool = args.regen_schemas
    stop_on_error: bool = args.stop_on_error
    quiet: bool = args.quiet
    verbose: int = args.verbose
    add_headers: bool = args.add_headers
    watch: bool = args.watch

    repo_root = repo_root.resolve()

    if configs_dir is None:
        configs_dir = next(
            (
                p
                for p in repo_root.rglob("conf*")
                if p.is_dir() and ".venv" not in p.parts
            ),
            None,
        )

    if configs_dir is None:
        raise ValueError(
            f"--configs-dir was not passed, and no hydra configs directory was found in "
            f"the passed repo root: {repo_root}!"
        )
    if not configs_dir.is_absolute():
        configs_dir = repo_root / configs_dir

    configs_dir = configs_dir.resolve()

    from hydra.core.config_store import ConfigStore
    from hydra.core.singleton import Singleton

    # assert False, (repo_root, configs_dir)
    _dir_before = os.getcwd()
    _sys_path_before = sys.path.copy()
    _singleton_state_before = Singleton.get_state()

    try:
        os.chdir(repo_root)
        repo_root = Path(".")
        sys.path.append(".")  # UGLY HACK!

        # Idea (might not be necessary): import all hydra-related modules in the repo root to
        # populate the ConfigStore.
        # package = repo_root.name.replace("-", "_")
        # for module in repo_root.glob("*.py"):
        #     module_name = module.stem
        #     if (
        #         "import hydra" in (module_text := module.read_text())
        #         or "from hydra" in module_text or "ConfigStore" in module_text
        #     ):
        #         logger.info(
        #             f"Importing module {module_name} from {package} to populate Hydra's ConfigStore."
        #         )
        #         importlib.import_module(module_name, package=package)
        config_store = ConfigStore.instance()
        # FIXME: It seems like changing this value is necessary? (otherwise we get an error later.)
        configs_dir = configs_dir.relative_to(os.getcwd())

    except ModuleNotFoundError:
        config_store = None
    finally:
        sys.path = _sys_path_before
        Singleton.set_state(_singleton_state_before)
        os.chdir(_dir_before)

    # try to find a ConfigStore?

    if quiet:
        logger.setLevel(logging.NOTSET)
    elif verbose:
        if verbose >= 3:
            logger.setLevel(logging.DEBUG)
        elif verbose == 2:
            logger.setLevel(logging.INFO)
        else:
            assert verbose == 1
            logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(logging.ERROR)
    logger.debug(
        f"{configs_dir=} {schemas_dir=} {repo_root=} {regen_schemas=} {stop_on_error=} {quiet=} {verbose=} {add_headers=} {watch=}"
    )

    if watch:
        observer = Observer()
        handler = AutoSchemaEventHandler(
            repo_root=repo_root,
            configs_dir=configs_dir,
            schemas_dir=schemas_dir,
            regen_schemas=regen_schemas,
            stop_on_error=stop_on_error,
            quiet=quiet,
            add_headers=add_headers,
            config_store=config_store,
        )
        observer.schedule(handler, str(configs_dir), recursive=True)
        observer.start()
        logger.info("Watching for changes in the config files.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
        return

    add_schemas_to_all_hydra_configs(
        repo_root=repo_root,
        configs_dir=configs_dir,
        schemas_dir=schemas_dir,
        regen_schemas=regen_schemas,
        stop_on_error=stop_on_error,
        quiet=quiet,
        add_headers=add_headers,
        config_store=config_store,
    )
    logger.info("Done updating the schemas for the Hydra config files.")


if __name__ == "__main__":
    main()
