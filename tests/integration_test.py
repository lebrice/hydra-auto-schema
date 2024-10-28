from pathlib import Path
from hydra_auto_schema.__main__ import main
import subprocess

config_dir = Path(__file__).parent / "configs"


def test_run_via_cli_without_errors():
    """Checks that the command completes without errors."""
    # Run programmatically instead of with a subproc4ess so we can get nice coverage stats.
    main(
        [f"{config_dir}", "--stop-on-error"]
    )  # assuming we're at the project root directory.


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
