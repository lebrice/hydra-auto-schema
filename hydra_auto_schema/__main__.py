from hydra_auto_schema.auto_schema import add_schemas_to_all_hydra_configs, logger
from hydra_auto_schema.filewatcher import AutoSchemaEventHandler

import argparse
import logging
import sys
import time
from pathlib import Path
import rich.logging
from watchdog.observers import Observer


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
    parser.add_argument(
        "configs_dir",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "The directory containing hydra config files for which schemas should be generated. "
            "If unset, this will default to the first directory called 'configs' in the repo root."
        ),
    )
    parser.add_argument("--schemas-dir", type=Path, default=Path.cwd() / ".schemas")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
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

    if configs_dir is None:
        configs_dir = next(
            (p for p in repo_root.rglob("configs") if ".venv" not in p.parts), None
        )

    if configs_dir is None:
        raise ValueError(
            f"--configs-dir was not passed, and no hydra configs directory was found in "
            f"the passed repo root: {repo_root}!"
        )
    if not configs_dir.is_absolute():
        configs_dir = repo_root / configs_dir

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
    )
    logger.info("Done updating the schemas for the Hydra config files.")


if __name__ == "__main__":
    main()
