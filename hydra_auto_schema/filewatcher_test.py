import contextlib
import shutil
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from watchdog.events import (
    DirCreatedEvent,  # noqa
    DirDeletedEvent,  # noqa
    DirModifiedEvent,  # noqa
    DirMovedEvent,  # noqa
    FileCreatedEvent,  # noqa
    FileDeletedEvent,  # noqa
    FileModifiedEvent,  # noqa
    FileMovedEvent,  # noqa
)
from watchdog.observers import Observer

from hydra_auto_schema.auto_schema import get_schema_file_path
from hydra_auto_schema.filewatcher import AutoSchemaEventHandler

from .auto_schema_test import config_dir


@pytest.fixture
def repo_root(tmp_path: Path):
    repo_root = tmp_path / "repo_root"
    repo_root.mkdir()
    return repo_root


@pytest.fixture
def configs_dir(repo_root: Path):
    test_configs_dir = repo_root / "configs"
    shutil.copytree(config_dir, test_configs_dir)
    shutil.copy(config_dir.parent / "app.py", repo_root)
    return test_configs_dir


@pytest.fixture
def schemas_dir(tmp_path: Path):
    return tmp_path / ".schemas"


@pytest.fixture
def observer():
    """Taken from https://github.com/gorakhargosh/watchdog/blob/master/tests/test_fsevents.py#L39"""
    obs = Observer()
    obs.start()
    try:
        yield obs
    finally:
        obs.stop()
        with contextlib.suppress(RuntimeError):
            obs.join()


@pytest.fixture
def filewatcher(
    repo_root: Path,
    configs_dir: Path,
    schemas_dir: Path,
    observer,
):
    regen_schemas = True
    stop_on_error = True
    quiet = False
    add_headers = True

    # TODO: Do we mock out the calls to hydra stuff? (They are breaking.)

    real_handler = AutoSchemaEventHandler(
        repo_root=repo_root,
        configs_dir=configs_dir,
        schemas_dir=schemas_dir,
        regen_schemas=regen_schemas,
        stop_on_error=stop_on_error,
        quiet=quiet,
        add_headers=add_headers,
    )
    mock_handler = Mock(
        spec=real_handler,
        spec_set=real_handler,
        wraps=real_handler,
    )

    observer.schedule(mock_handler, str(configs_dir), recursive=True)
    yield mock_handler


def _get_all_schema_files(schemas_dir: Path) -> list[Path]:
    return list(schemas_dir.rglob("*.json"))


def test_on_created(
    filewatcher: AutoSchemaEventHandler, configs_dir: Path, schemas_dir: Path
):
    schemas_before = _get_all_schema_files(schemas_dir)

    new_file = configs_dir / "foobar.yaml"
    assert not new_file.exists()
    schema_file = get_schema_file_path(new_file, schemas_dir)
    assert not schema_file.exists()

    new_file.write_text("foo: bar")
    time.sleep(0.5)

    filewatcher.dispatch.assert_any_call(  # type: ignore
        FileCreatedEvent(
            src_path=str(new_file),
            is_synthetic=False,
        )
    )

    schemas_after = _get_all_schema_files(schemas_dir)
    assert set(schemas_after) == set(schemas_before) | {schema_file}


def test_on_modified(
    filewatcher: AutoSchemaEventHandler, configs_dir: Path, schemas_dir: Path
):
    existing_file = configs_dir / "config.yaml"
    assert existing_file.exists()
    schemas_before = _get_all_schema_files(schemas_dir)
    schema_file = get_schema_file_path(existing_file, schemas_dir)
    assert schema_file.exists()
    assert schema_file in schemas_before

    existing_file.write_text(existing_file.read_text() + "\n")
    time.sleep(0.5)

    filewatcher.dispatch.assert_any_call(  # type: ignore
        FileModifiedEvent(
            src_path=str(existing_file),
            is_synthetic=False,
        )
    )

    schemas_after = _get_all_schema_files(schemas_dir)
    assert set(schemas_after) == set(schemas_before)


def test_on_deleted(
    filewatcher: AutoSchemaEventHandler, configs_dir: Path, schemas_dir: Path
):
    existing_file = configs_dir / "config.yaml"
    assert existing_file.exists()
    schemas_before = _get_all_schema_files(schemas_dir)
    schema_file = get_schema_file_path(existing_file, schemas_dir)
    assert schema_file.exists()
    assert schema_file in schemas_before

    existing_file.unlink()
    time.sleep(0.5)

    filewatcher.dispatch.assert_any_call(  # type: ignore
        FileDeletedEvent(
            src_path=str(existing_file),
            is_synthetic=False,
        )
    )

    schemas_after = _get_all_schema_files(schemas_dir)
    assert set(schemas_after) == set(schemas_before) - {schema_file}


def test_on_moved(
    filewatcher: AutoSchemaEventHandler, configs_dir: Path, schemas_dir: Path
):
    old_file = configs_dir / "config.yaml"
    new_file = configs_dir / "config2.yaml"
    assert old_file.exists()
    assert not new_file.exists()

    schemas_before = _get_all_schema_files(schemas_dir)
    old_file_schema = get_schema_file_path(old_file, schemas_dir)
    new_file_schema = get_schema_file_path(new_file, schemas_dir)
    assert old_file_schema.exists()
    assert old_file_schema in schemas_before
    assert not new_file_schema.exists()
    assert new_file_schema not in schemas_before  # duh.

    old_file.rename(new_file)
    time.sleep(0.5)

    filewatcher.dispatch.assert_any_call(  # type: ignore
        FileMovedEvent(
            src_path=str(old_file),
            dest_path=str(new_file),
            is_synthetic=False,
        )
    )

    schemas_after = _get_all_schema_files(schemas_dir)
    assert set(schemas_after) == (set(schemas_before) - {old_file_schema}) | {
        new_file_schema
    }
