import shlex
import subprocess
from pathlib import Path

import hydra.core.plugins
import hydra.errors
import pytest
from hydra.plugins.search_path_plugin import SearchPathPlugin

from hydra_auto_schema.__main__ import main
from hydra_plugins.auto_schema.auto_schema_plugin import (
    AutoSchemaPlugin,
)

this_dir = Path(__file__).parent
test_configs_dir = this_dir / "configs"
structured_app_dir = this_dir / "structured_app"


@pytest.mark.xfail(
    raises=hydra.errors.MissingConfigException,
    reason="Doesn't work yet, need to get a populated Hydra ConfigStore outside the Hydra context.",
    strict=True,
)
@pytest.mark.parametrize(
    "args",
    [
        f"{this_dir} --stop-on-error --regen-schemas -vvv",
        # TODO: Perhaps we could try to import the repo_root as a python module, or add it to
        # path, or something similar, so that we can actually get a "hydrated" ConfigStore object?
        f"{structured_app_dir} --stop-on-error --regen-schemas -vvv",
    ],
)
def test_run_via_cli_without_errors(args: str):
    """Checks that the command completes without errors."""
    # Run programmatically instead of with a subprocess so we can get nice coverage stats.
    # assuming we're at the project root directory.
    main(shlex.split(args))


@pytest.mark.skip(reason="Shouldn't really be run as a uv tool anyway.")
def test_run_with_uvx():
    """Actually run the command on the repo, via the `[tool.rye.scripts]` entry in
    pyproject.toml."""
    # Run once so we can get nice coverage stats.
    subprocess.check_call(
        [
            "uvx",
            "--from=.",
            "--reinstall-package=hydra-auto-schema",
            "hydra-auto-schema",
            f"{test_configs_dir}",
        ],
        text=True,
    )


@pytest.mark.skip(reason="Shouldn't really be run as a uv tool anyway.")
def test_run_as_uv_tool():
    """Actually run the command on the repo, via the `[tool.rye.scripts]` entry in
    pyproject.toml."""
    # Run once so we can get nice coverage stats.
    subprocess.check_call(
        [
            "uv",
            "tool",
            "run",
            "--from=.",
            "--reinstall-package=hydra-auto-schema",
            "hydra-auto-schema",
            f"{test_configs_dir}",
        ],
        text=True,
    )


# @pytest.mark.xfail(
#     reason="Turning off the plugin discovery for now while it's not ready."
# )
def test_plugin_is_discoverable(monkeypatch: pytest.MonkeyPatch):
    # NOTE: This is super bad, it executes the plugin modules, and inserts them forcefully into
    # `sys.modules`, which overwrites our loaded modules!
    # class PreventOverwriteByHydraPlugins(dict):
    #     def __setitem__(self, key: str, value) -> None:
    #         if key.startswith("hydra_plugins.") and key in self:
    #             return
    #         super().__setitem__(key, value)

    # can't seem to be able to import `Loader` of importlib. :(
    # monkeypatch.setattr(importlib.Loader, "exec_module", lambda module: None)
    # monkeypatch.setattr(sys, "modules", PreventOverwriteByHydraPlugins(sys.modules))
    plugins = hydra.core.plugins.Plugins.instance().discover(SearchPathPlugin)
    # assert AutoSchemaPlugin in plugins
    assert AutoSchemaPlugin.__name__ in [p.__name__ for p in plugins]
