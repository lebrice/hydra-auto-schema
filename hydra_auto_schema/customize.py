"""Global variables that can be used to customize how schemas are generated."""
import dataclasses
import enum
from typing import Any, Callable

from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

custom_hydra_zen_builds_args: dict[type | Callable, dict] = {
    # flax.linen.Module: {"zen_exclude": ["parent"]},
    # lightning.pytorch.callbacks.RichProgressBar: {"zen_exclude": ["theme"]},
}
"""Keyword arguments that should be passed to `hydra_zen.builds` for a given class or callable.

These arguments overwrite the default values.
"""

custom_enum_schemas: dict[type[enum.Enum], Callable] = {}
"""Dict of functions to be used by pydantic to generate schemas for enum classes.

TODO: This a bit too specific. We could probably use our `GenerateJsonSchema`
subclass to enable more general customizations, following this guide:
https://docs.pydantic.dev/2.9/concepts/json_schema/#customizing-the-json-schema-generation-process
"""

schema_conflict_handlers: dict[str, Callable[[Any, Any], Any]] = {}
"""Functions to be used by the `merge_dicts` function to resolve conflicts between schemas.

See the docstring of `merge_dicts` for more info.
"""

# Conditionally add some common fixes?
# TODO: Should we really import those here? This might make the import pretty slow, no? If not,
# when / how should we import things here?

try:
    from flax.linen import Module  # type: ignore

    custom_hydra_zen_builds_args[Module] = {"zen_exclude": ["parent"]}
except ImportError:
    pass

try:
    from lightning.pytorch.callbacks import RichProgressBar  # type: ignore

    custom_hydra_zen_builds_args[RichProgressBar] = {"zen_exclude": ["theme"]}
except ImportError:
    pass


try:
    from torchvision.models import WeightsEnum as _WeightsEnum  # type: ignore

    def _handle_torchvision_weights_enum(
        enum_type: type[_WeightsEnum], schema: core_schema.EnumSchema
    ) -> JsonSchemaValue:
        @dataclasses.dataclass
        class Dummy:
            value: str

        slightly_changed_schema = schema | {
            "members": [Dummy(v.name) for v in schema["members"]]
        }
        return slightly_changed_schema

    custom_enum_schemas[_WeightsEnum] = _handle_torchvision_weights_enum
except ImportError:
    pass
