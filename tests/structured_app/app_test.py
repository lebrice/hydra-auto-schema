""" TODO: Tests for getting the schema from structured configs. """

import shlex
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


@pytest.fixture(params=[True, False])
def schemas_already_exist(request: pytest.FixtureRequest):
    return request.param


@pytest.fixture
def new_schemas_dir(new_repo_root: Path, schemas_already_exist: bool):
    schemas_dir = new_repo_root / "schemas"
    if not schemas_already_exist:
        shutil.rmtree(schemas_dir, ignore_errors=True)
    return schemas_dir


@pytest.fixture()
def set_config(
    tmp_path: Path,
    new_schemas_dir: Path,
    new_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        auto_schema_plugin,
        "config",
        auto_schema_plugin.AutoSchemaPluginConfig(
            schemas_dir=new_schemas_dir,
            add_headers=True,
            regen_schemas=True,
            stop_on_error=True,
            quiet=False,
            verbose=True,
        ),
    )


@pytest.fixture
def command_line_arguments(request: pytest.FixtureRequest):
    return getattr(request, "param", "")


@pytest.fixture
def structured_app_result(
    new_repo_root: Path,
    set_config: None,
    command_line_arguments: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(new_repo_root)
    result = subprocess.run(
        ["python", "app.py", *shlex.split(command_line_arguments)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    print(result.stdout)
    print(result.stderr)
    return result


@pytest.mark.parametrize(
    command_line_arguments.__name__, ["db.port=fail"], indirect=True
)
def test_run_example(
    structured_app_result: subprocess.CompletedProcess,
    new_repo_root: Path,
    new_schemas_dir: Path,
    file_regression: FileRegressionFixture,
):
    assert structured_app_result.returncode == 1
    assert (
        "Value 'fail' of type 'str' could not be converted to Integer"
        in structured_app_result.stderr
    )
    assert "full_key: db.port" in structured_app_result.stderr
    assert "reference_type=DBConfig" in structured_app_result.stderr
    assert "object_type=MySQLConfig" in structured_app_result.stderr
    # The schemas should have been generated.
    schemas_dir = new_schemas_dir
    assert schemas_dir.exists()
    files = list(schemas_dir.glob("*.json"))
    assert files
    for file in files:
        file_regression.check(
            (schemas_dir / file.name).read_text().rstrip(),
            extension=".json",
            fullpath=structured_app_dir / "schemas" / file.name,
        )


@pytest.mark.xfail(reason="TODO: implement the test.", strict=True)
@pytest.mark.parametrize(
    command_line_arguments.__name__, ["--config-name=with_overrides"], indirect=True
)
def test_run_example_with_overrides(
    structured_app_result: subprocess.CompletedProcess,
    new_schemas_dir: Path,
    file_regression: FileRegressionFixture,
):
    assert structured_app_result.returncode == 1
    assert False, structured_app_result.stdout
    # The schemas should have been generated.
    schemas_dir = new_schemas_dir
    assert schemas_dir.exists()
    files = list(schemas_dir.glob("*.json"))
    assert files
    for file in files:
        file_regression.check(
            (schemas_dir / file.name).read_text().rstrip(),
            extension=".json",
            fullpath=structured_app_dir / "schemas" / file.name,
        )
