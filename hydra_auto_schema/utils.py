from pathlib import Path


def pretty_path(path: Path) -> str:
    return (
        ("./" + str(path.relative_to(Path.cwd())))
        if path.is_relative_to(Path.cwd())
        else str(path)
    )
