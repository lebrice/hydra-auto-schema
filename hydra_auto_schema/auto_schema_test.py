import json
import os
from pathlib import Path

import pytest
import yaml
from hydra.core.config_store import ConfigStore
from pytest_regressions.file_regression import FileRegressionFixture

from .auto_schema import (
    _add_schema_header,
    _create_schema_for_config,
    add_schemas_to_all_hydra_configs,
)

REPO_ROOTDIR = Path.cwd()
IN_GITHUB_CI = "GITHUB_ACTIONS" in os.environ
config_dir = Path(__file__).parent.parent / "tests" / "configs"


@pytest.fixture
def original_datadir():
    return config_dir


class Foo:
    def __init__(self, bar: str):
        """Description of the `Foo` class.

        Args:
            bar: Description of the `bar` argument.
        """
        self.bar = bar


class Bar(Foo):
    """Docstring of the Bar class.

    Args:
        baz: description of the `baz` argument from the cls docstring instead of the init docstring.
    """

    def __init__(self, bar: str, baz: int):
        # no docstring here.
        super().__init__(bar=bar)
        self.baz = baz


test_files = list(config_dir.rglob("*.yaml"))


@pytest.mark.parametrize(
    "config_file",
    [
        pytest.param(
            p,
            marks=pytest.mark.xfail(
                IN_GITHUB_CI,
                reason="TODO: Does not work on the Github CI for some reason!",
            ),
        )
        if "structured" in p.name
        else p
        for p in test_files
    ],
    ids=[f.name for f in test_files],
)
def test_make_schema(config_file: Path, file_regression: FileRegressionFixture):
    """Test that creates a schema for a config file and saves it next to it.

    (in the test folder).
    """
    schema_file = config_file.with_suffix(".json")

    config = yaml.load(config_file.read_text(), yaml.FullLoader)
    if config is None:
        config = {}
    schema = _create_schema_for_config(
        config=config,
        config_file=config_file,
        configs_dir=config_dir,
        repo_root=REPO_ROOTDIR,
        config_store=ConfigStore.instance(),
    )
    _add_schema_header(config_file, schema_path=schema_file)

    file_regression.check(
        json.dumps(schema, indent=2) + "\n", fullpath=schema_file, extension=".json"
    )


def test_warns_when_no_config_files_found(tmp_path: Path):
    with pytest.warns(RuntimeWarning, match="No config files were found"):
        add_schemas_to_all_hydra_configs(
            repo_root=tmp_path, configs_dir=tmp_path, schemas_dir=tmp_path
        )


def test_raises_when_no_config_files_found_and_stop_on_error(tmp_path: Path):
    with pytest.raises(RuntimeError, match="No config files were found"):
        add_schemas_to_all_hydra_configs(
            repo_root=tmp_path,
            configs_dir=tmp_path,
            schemas_dir=tmp_path,
            stop_on_error=True,
        )
