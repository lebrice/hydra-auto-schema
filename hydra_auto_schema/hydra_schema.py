from __future__ import annotations
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, Literal, TypedDict
from typing_extensions import NotRequired, Required


_SpecialEntries = TypedDict(
    "_SpecialEntries", {"$defs": dict[str, dict], "$schema": str}, total=False
)


class PropertySchema(_SpecialEntries, total=False):
    title: str
    type: str
    description: str
    default: Any
    examples: list[str]
    deprecated: bool
    readOnly: bool
    writeOnly: bool
    const: Any
    enum: list[Any]


class OneOf(TypedDict):
    oneOf: Sequence[
        PropertySchema | ArrayPropertySchema | ObjectSchema | StringPropertySchema
    ]


class ArrayPropertySchema(PropertySchema, total=False):
    type: Literal["array"]
    items: Required[PropertySchema | OneOf]
    minItems: int
    maxItems: int
    uniqueItems: bool


class StringPropertySchema(PropertySchema, total=False):
    type: Literal["string"]
    pattern: str


class _PropertyNames(TypedDict):
    pattern: str


class ObjectSchema(PropertySchema, total=False):
    type: Literal["object"]
    # annoying that we have to include the subclasses here!
    properties: MutableMapping[
        str, PropertySchema | ArrayPropertySchema | StringPropertySchema | ObjectSchema
    ]
    patternProperties: Mapping[str, PropertySchema | StringPropertySchema]
    propertyNames: _PropertyNames
    minProperties: int
    maxProperties: int


class Schema(TypedDict, total=False):
    # "$defs":
    title: str
    description: str
    type: str

    # annoying that we have to include the subclasses here!
    properties: Required[
        MutableMapping[
            str,
            PropertySchema | ArrayPropertySchema | StringPropertySchema | ObjectSchema,
        ]
    ]
    required: NotRequired[list[str]]

    additionalProperties: NotRequired[bool]

    dependentRequired: NotRequired[MutableMapping[str, list[str]]]
    """ https://json-schema.org/understanding-json-schema/reference/conditionals#dependentRequired """


HYDRA_CONFIG_SCHEMA = Schema(
    title="Default Schema for any Hydra config file.",
    description="Schema created by the `auto_schema.py` script.",
    properties={
        "defaults": ArrayPropertySchema(
            title="Hydra defaults",
            description="Hydra defaults for this config. See https://hydra.cc/docs/advanced/defaults_list/",
            type="array",
            items=OneOf(
                oneOf=[
                    ObjectSchema(
                        type="object",
                        propertyNames={"pattern": r"^(override\s*)?(/?\w*)+$"},
                        patternProperties={
                            # todo: support package directives with @?
                            # todo: Create a enum schema using the available options in the config group!
                            # override network: something  -> `something` value should be in the available options for network.
                            r"^(override\s*)?(/?\w*)*$": StringPropertySchema(
                                type="string", pattern=r"\w*(.yaml|.yml)?$"
                            ),
                        },
                        minProperties=1,
                        maxProperties=1,
                    ),
                    StringPropertySchema(type="string", pattern=r"^\w+(.yaml|.yml)?$"),
                    ObjectSchema(
                        type="object",
                        propertyNames=_PropertyNames(
                            pattern=r"^(override\s*)?(/?\w*)+$"
                        ),
                        patternProperties={
                            r"^(override\s*)?(/?\w*)*$": PropertySchema(type="null"),
                        },
                        minProperties=1,
                        maxProperties=1,
                    ),
                ],
            ),
            uniqueItems=True,
        ),
        "_target_": StringPropertySchema(
            type="string",
            title="Target",
            description="Target to instantiate.\nSee https://hydra.cc/docs/advanced/instantiate_objects/overview/",
        ),
        "_convert_": StringPropertySchema(
            type="string",
            enum=["none", "partial", "object", "all"],
            title="Convert",
            description="See https://hydra.cc/docs/advanced/instantiate_objects/overview/#parameter-conversion-strategies",
        ),
        "_partial_": PropertySchema(
            type="boolean",
            title="Partial",
            description=(
                "Whether this config calls the target function when instantiated, or creates "
                "a `functools.partial` that will call the target.\n"
                "See: https://hydra.cc/docs/advanced/instantiate_objects/overview"
            ),
        ),
        "_recursive_": PropertySchema(
            type="boolean",
            title="Recursive",
            description=(
                "Whether instantiating this config should recursively instantiate children configs.\n"
                "See: https://hydra.cc/docs/advanced/instantiate_objects/overview/#recursive-instantiation"
            ),
        ),
    },
    dependentRequired={
        "_convert_": ["_target_"],
        "_partial_": ["_target_"],
        "_args_": ["_target_"],
        "_recursive_": ["_target_"],
    },
)
