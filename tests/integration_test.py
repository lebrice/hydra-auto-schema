import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import hydra.core.plugins
import pytest
from hydra.plugins.search_path_plugin import SearchPathPlugin

from hydra_auto_schema.__main__ import main
from hydra_plugins.auto_schema import auto_schema_plugin
from hydra_plugins.auto_schema.auto_schema_plugin import (
    AutoSchemaPlugin,
    AutoSchemaPluginConfig,
)

from .app import app

config_dir = Path(__file__).parent / "configs"


def test_run_via_cli_without_errors():
    """Checks that the command completes without errors."""
    # Run programmatically instead of with a subprocess so we can get nice coverage stats.
    # assuming we're at the project root directory.
    main([f"{config_dir}", "--stop-on-error"])


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
            f"{config_dir}",
        ],
        text=True,
    )


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
            f"{config_dir}",
        ],
        text=True,
    )


@pytest.mark.xfail(
    reason="Turning off the plugin discovery for now while it's not ready."
)
def test_plugin_is_discoverable():
    plugins = hydra.core.plugins.Plugins.instance().discover(SearchPathPlugin)
    # Should only be discovered once though!
    assert AutoSchemaPlugin in plugins


@pytest.mark.xfail(reason="Plugin isn't called atm now while it's not ready.")
def test_plugin_is_called_when_hydra_app_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.chdir("tests")
    monkeypatch.setattr(sys, "argv", ["app.py"])
    monkeypatch.setitem(os.environ, "HYDRA_FULL_ERROR", "1")
    monkeypatch.setattr(AutoSchemaPlugin, "_ALREADY_DID", False)

    # Register manually while it's not automatically discovered?
    # register_auto_schema_plugin()

    test_config = AutoSchemaPluginConfig(
        schemas_dir=tmp_path,
        add_headers=True,
        quiet=False,
        regen_schemas=True,
        stop_on_error=True,
    )
    monkeypatch.setattr(auto_schema_plugin, "config", test_config)
    plugin = AutoSchemaPlugin()
    mock_plugin = Mock(spec_set=plugin, wraps=plugin)

    monkeypatch.setattr(
        auto_schema_plugin,
        AutoSchemaPlugin.__name__,
        Mock(spec_set=AutoSchemaPlugin, return_value=mock_plugin),
    )

    app()
    assert AutoSchemaPlugin._ALREADY_DID
    mock_plugin.manipulate_search_path.assert_called_once()
