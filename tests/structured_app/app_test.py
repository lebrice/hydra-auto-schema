""" TODO: Tests for getting the schema from structured configs. """

import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from hydra_plugins.auto_schema import auto_schema_plugin

structured_app_dir = Path(__file__).parent


@pytest.fixture
def new_repo_root(tmp_path: Path):
    new_repo_root = tmp_path / structured_app_dir.name
    shutil.copytree(structured_app_dir, new_repo_root)
    return new_repo_root


@pytest.fixture(scope="function", autouse=True)
def set_config(tmp_path: Path, new_repo_root: Path, monkeypatch: pytest.MonkeyPatch):
    test_config = auto_schema_plugin.AutoSchemaPluginConfig(
        schemas_dir=tmp_path / ".schemas"
    )
    monkeypatch.setattr(auto_schema_plugin, "config", test_config)


def test_structured_app(
    new_repo_root: Path,
    file_regression: FileRegressionFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(new_repo_root)
    result = subprocess.run(
        ["python", "app.py", "db.port=fail"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert (
        "Value 'fail' of type 'str' could not be converted to Integer" in result.stderr
    )
    assert "full_key: db.port" in result.stderr
    assert "reference_type=DBConfig" in result.stderr
    assert "object_type=MySQLConfig" in result.stderr
    # TODO:
    # schemas_dir = new_repo_root / ".schemas"
    # assert schemas_dir.exists()
