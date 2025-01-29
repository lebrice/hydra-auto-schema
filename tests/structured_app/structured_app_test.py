""" TODO: Tests for getting the schema from structured configs. """

import shlex
import shutil
import subprocess
from pathlib import Path
import sys
import warnings

import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from hydra_plugins.auto_schema import auto_schema_plugin

structured_app_dir = Path(__file__).parent


@pytest.fixture
def new_repo_root(tmp_path: Path):
    new_repo_root = tmp_path / structured_app_dir.name
    shutil.copytree(structured_app_dir, new_repo_root)

    return new_repo_root


@pytest.fixture(params=[True, False], ids=["schemas_exist", "schemas_do_not_exist"])
def schemas_already_exist(request: pytest.FixtureRequest):
    return request.param


@pytest.fixture
def new_schemas_dir(new_repo_root: Path, schemas_already_exist: bool):
    schemas_dir = new_repo_root / "schemas"
    if not schemas_already_exist:
        shutil.rmtree(schemas_dir, ignore_errors=True)
    return schemas_dir


@pytest.fixture
def disable(request: pytest.FixtureRequest):
    return getattr(request, "param", False)


@pytest.fixture()
def set_config(
    tmp_path: Path,
    new_schemas_dir: Path,
    new_repo_root: Path,
    disable: bool,
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
            disable=disable,
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
    # monkeypatch.chdir(new_repo_root)
    result = subprocess.run(
        ["python", str(new_repo_root / "app.py"), *shlex.split(command_line_arguments)],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    print(result.stderr)
    return result


@pytest.mark.parametrize(command_line_arguments.__name__, [""], indirect=True)
def test_run_example(
    structured_app_result: subprocess.CompletedProcess,
    new_repo_root: Path,
    new_schemas_dir: Path,
    file_regression: FileRegressionFixture,
):
    assert structured_app_result.returncode == 0
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


@pytest.mark.parametrize(
    command_line_arguments.__name__, ["db.port=fail"], indirect=True
)
def test_run_example_with_error(
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


@pytest.fixture
def cli_args(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, new_repo_root: Path
):
    args = shlex.split(getattr(request, "param", ""))
    monkeypatch.chdir(new_repo_root)
    monkeypatch.setattr(sys, "argv", ["app.py"] + args)


@pytest.mark.parametrize(
    disable.__name__, [False, True], indirect=True, ids=["enabled", "disabled"]
)
@pytest.mark.parametrize(cli_args.__name__, ["", "db=postgresql"], indirect=True)
def test_disable_option(
    cli_args,
    new_repo_root: Path,
    set_config: None,
    disable: bool,
    new_schemas_dir: Path,
    schemas_already_exist: bool,
    file_regression: FileRegressionFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.syspath_prepend(str(new_repo_root.parent))
    monkeypatch.setenv("HYDRA_FULL_ERROR", "1")
    # https://www.geeksforgeeks.org/how-to-import-a-python-module-given-the-full-path/
    # module_spec = importlib.util.spec_from_file_location(
    #     "app", new_repo_root / "app.py"
    # )
    # app = importlib.util.module_from_spec(module_spec)
    # # executes the module in its own namespace
    # # when a module is imported or reloaded.
    # module_spec.loader.exec_module(app)
    from structured_app import app

    monkeypatch.setattr(
        auto_schema_plugin,
        "config",
        auto_schema_plugin.AutoSchemaPluginConfig(
            schemas_dir=new_schemas_dir,
            add_headers=True,
            regen_schemas=True,
            stop_on_error=True,
            quiet=False,
            disable=disable,
            verbose=True,
        ),
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", category=RuntimeWarning)
        app.register_configs()
        app.my_app()

    # The schemas should have been generated if not disabled.
    schemas_dir = new_schemas_dir
    assert schemas_dir.exists() is ((not disable) or schemas_already_exist)
    files = list(schemas_dir.glob("*.json"))

    assert bool(files) is ((not disable) or schemas_already_exist)
    for file in files:
        file_regression.check(
            (schemas_dir / file.name).read_text().rstrip(),
            extension=".json",
            fullpath=structured_app_dir / "schemas" / file.name,
        )
