import dataclasses
from collections.abc import Callable
import enum
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


special_handlers: dict[type | Callable, dict] = {
    # flax.linen.Module: {"zen_exclude": ["parent"]},
    # lightning.pytorch.callbacks.RichProgressBar: {"zen_exclude": ["theme"]},
}
"""Keyword arguments that should be passed to `hydra_zen.builds` for a given class or callable.

These arguments overwrite the default values.
"""
custom_enum_schemas: dict[type[enum.Enum], Callable] = {}

try:
    from flax.linen import Module  # type: ignore

    special_handlers[Module] = {"zen_exclude": ["parent"]}
except ImportError:
    pass

try:
    from lightning.pytorch.callbacks import RichProgressBar  # type: ignore

    special_handlers[RichProgressBar] = {"zen_exclude": ["theme"]}
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
