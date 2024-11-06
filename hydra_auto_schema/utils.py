import copy
import inspect
from pathlib import Path
from typing import Callable, Mapping, MutableMapping, TypeVar, cast

# from hydra_auto_schema.customize import conflict_handlers

K = TypeVar("K")
K1 = TypeVar("K1")
K2 = TypeVar("K2")
V = TypeVar("V")
V1 = TypeVar("V1")
V2 = TypeVar("V2")

NestedMapping = MutableMapping[K, V | "NestedMapping[K, V]"]
NestedDict = dict[K, V | "NestedDict[K, V]"]


def get_target_string(some_callable: type | Callable) -> str:
    """Gets the string to use as _target_ in a Hydra config for the given callable.

    >>> get_target_string(int)
    'builtins.int'
    >>> get_target_string(Path)
    'pathlib.Path'
    >>> get_target_string(get_target_string)
    'hydra_auto_schema.utils.get_target_string'
    """
    if inspect.isclass(some_callable):
        return f"{some_callable.__module__}.{some_callable.__qualname__}"
    else:
        name = getattr(
            some_callable, "__qualname__", getattr(some_callable, "__name__")
        )
        return f"{some_callable.__module__}.{name}"


def pretty_path(path: Path) -> str:
    return (
        ("./" + str(path.relative_to(Path.cwd())))
        if path.is_relative_to(Path.cwd())
        else str(path)
    )


def merge_dicts(
    a: NestedMapping[K1, V1],
    b: NestedMapping[K2, V2],
    conflict_handler: Callable[[V1, V2], V1 | V2] | None = None,
    conflict_handlers: dict[str, Callable[[V1, V2], V1 | V2]] | None = None,
    _path: list[str] = [],
) -> NestedMapping[K1 | K2, V1 | V2]:
    """Merge two nested dictionaries.

    NOTE: performs a deep copy of `a` and of values in `b`.

    >>> x = dict(b=1, c=dict(d=2, e=3))
    >>> y = dict(d=3, c=dict(z=2, f=4))
    >>> merge_dicts(x, y)
    {'b': 1, 'c': {'d': 2, 'e': 3, 'z': 2, 'f': 4}, 'd': 3}
    >>> x
    {'b': 1, 'c': {'d': 2, 'e': 3}}
    >>> y
    {'d': 3, 'c': {'z': 2, 'f': 4}}

    If keys are in both dicts and no conflict handler is passed, an error is raised:
    >>> merge_dicts({'a': {'b': 1, 'c': 5}}, {'a': {'b': 2}})
    Traceback (most recent call last):
    ...
    Exception: Conflict at a.b


    in nested dicts conflict, the `conflict_handler` is called with the conflicting values.

    >>> merge_dicts({'a': {'b': 1, 'c': 5}}, {'a': {'b': 2}}, conflict_handler=lambda a, b: a + b)
    {'a': {'b': 3, 'c': 5}}

    Conflict handlers can be passed for specific keys.
    The dict of handlers can map either from the full path or from a key to the handler to use:

    >>> merge_dicts(
    ...     {'a': {'b': 1, 'c': 1, 'd': 12}},
    ...     {'a': {'b': 2, 'c': 2}},
    ...     conflict_handlers={
    ...         'a.b': lambda a, b: a + b,  # this will be used for 'a.b'
    ...         'c': lambda a, b: a - b,    # this will be used for 'c' in any subdict.
    ...     }
    ... )
    {'a': {'b': 3, 'c': -1, 'd': 12}}
    """
    conflict_handlers = conflict_handlers or {}
    out: NestedMapping[K1 | K2, V1 | V2] = copy.deepcopy(a)  # type: ignore
    for key in b:
        b_val: V2 | NestedMapping[K2, V2] = b[key]

        if key not in a:
            out[key] = copy.deepcopy(b_val)  # type: ignore
            continue

        # Type checker doesn't get that `key in a` := `isinstance(key, V1)` yet.
        a_key: K1 = key  # type: ignore
        a_val = a[a_key]

        if isinstance(a_val, Mapping) and isinstance(b_val, Mapping):
            # Type checker doesn't narrow `a_val` or `b_val` to `NestedMapping` yet.
            a_val = cast(NestedMapping[K1, V1], a_val)
            b_val = cast(NestedMapping[K2, V2], b_val)
            out[key] = merge_dicts(
                a_val,
                b_val,
                conflict_handlers={
                    # k: v
                    k.removeprefix(f"{key}."): v
                    for k, v in (conflict_handlers or {}).items()
                },
                conflict_handler=conflict_handler,
                _path=_path + [str(key)],
            )
        elif a_val != b_val:
            # Type checker doesn't narrow `a_val` to `V1` or `b_val` to `V2` yet.
            a_val = cast(V1, a_val)
            b_val = cast(V2, b_val)
            if specific_conflict_handler := conflict_handlers.get(str(key)):
                out[key] = specific_conflict_handler(a_val, b_val)
            elif conflict_handler:
                out[key] = conflict_handler(a_val, b_val)
            else:
                raise Exception("Conflict at " + ".".join(_path + [str(key)]))
    return out
