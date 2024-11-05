import enum
import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from unittest.mock import Mock

import omegaconf
import pytest
from pytest_regressions.file_regression import FileRegressionFixture

from hydra_auto_schema.auto_schema import _create_schema_for_config

## Copied from torchvision.


@dataclass
class Weights:
    """This class is used to group important attributes associated with the pre-trained weights.

    Args:
        url (str): The location where we find the weights.
        transforms (Callable): A callable that constructs the preprocessing method (or validation preset transforms)
            needed to use the model. The reason we attach a constructor method rather than an already constructed
            object is because the specific object might have memory and thus we want to delay initialization until
            needed.
        meta (Dict[str, Any]): Stores meta-data related to the weights of the model and its configuration. These can be
            informative attributes (for example the number of parameters/flops, recipe link/methods used in training
            etc), configuration parameters (for example the `num_classes`) needed to construct the model or important
            meta-data (for example the `classes` of a classification model) needed to use the model.
    """

    url: str
    transforms: Callable
    meta: dict[str, Any]

    def __eq__(self, other: Any) -> bool:
        # We need this custom implementation for correct deep-copy and deserialization behavior.
        # TL;DR: After the definition of an enum, creating a new instance, i.e. by deep-copying or deserializing it,
        # involves an equality check against the defined members. Unfortunately, the `transforms` attribute is often
        # defined with `functools.partial` and `fn = partial(...); assert deepcopy(fn) != fn`. Without custom handling
        # for it, the check against the defined members would fail and effectively prevent the weights from being
        # deep-copied or deserialized.
        # See https://github.com/pytorch/vision/pull/7107 for details.
        if not isinstance(other, Weights):
            return NotImplemented

        if self.url != other.url:
            return False

        if self.meta != other.meta:
            return False

        if isinstance(self.transforms, functools.partial) and isinstance(
            other.transforms, functools.partial
        ):
            return (
                self.transforms.func == other.transforms.func
                and self.transforms.args == other.transforms.args
                and self.transforms.keywords == other.transforms.keywords
            )
        else:
            return self.transforms == other.transforms


# C
class WeightsEnum(enum.Enum):
    """This class is the parent class of all model weights. Each model building method receives an
    optional `weights` parameter with its associated pre-trained weights. It inherits from `Enum`
    and its values should be of type `Weights`.

    Args:
        value (Weights): The data class entry with the weight information.
    """

    @classmethod
    def verify(cls, obj: Any) -> Any:
        if obj is not None:
            if type(obj) is str:
                obj = cls[obj.replace(cls.__name__ + ".", "")]
            elif not isinstance(obj, cls):
                raise TypeError(
                    f"Invalid Weight class provided; expected {cls.__name__} but received {obj.__class__.__name__}."
                )
        return obj

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self._name_}"

    @property
    def url(self):
        return self.value.url

    @property
    def transforms(self):
        return self.value.transforms

    @property
    def meta(self):
        return self.value.meta


class InterpolationMode(enum.Enum):
    BILINEAR = enum.auto()


class ImageClassification:
    def __init__(
        self,
        *,
        crop_size: int,
        resize_size: int = 256,
        mean: tuple[float, ...] = (0.485, 0.456, 0.406),
        std: tuple[float, ...] = (0.229, 0.224, 0.225),
        interpolation: InterpolationMode = InterpolationMode.BILINEAR,
        antialias: bool | None = True,
    ) -> None:
        super().__init__()


_COMMON_META = {
    "min_size": (1, 1),
    "categories": [...],
}


class ResNet50_Weights(WeightsEnum):
    IMAGENET1K_V1 = Weights(
        url="https://download.pytorch.org/models/resnet50-0676ba61.pth",
        transforms=functools.partial(ImageClassification, crop_size=224),
        meta={
            **_COMMON_META,
            "num_params": 25557032,
            "recipe": "https://github.com/pytorch/vision/tree/main/references/classification#resnet",
            "_metrics": {
                "ImageNet-1K": {
                    "acc@1": 76.130,
                    "acc@5": 92.862,
                }
            },
            "_ops": 4.089,
            "_file_size": 97.781,
            "_docs": """These weights reproduce closely the results of the paper using a simple training recipe.""",
        },
    )
    IMAGENET1K_V2 = Weights(
        url="https://download.pytorch.org/models/resnet50-11ad3fa6.pth",
        transforms=functools.partial(
            ImageClassification, crop_size=224, resize_size=232
        ),
        meta={
            **_COMMON_META,
            "num_params": 25557032,
            "recipe": "https://github.com/pytorch/vision/issues/3995#issuecomment-1013906621",
            "_metrics": {
                "ImageNet-1K": {
                    "acc@1": 80.858,
                    "acc@5": 95.434,
                }
            },
            "_ops": 4.089,
            "_file_size": 97.79,
            "_docs": """
                These weights improve upon the results of the original paper by using TorchVision's `new training recipe
                <https://pytorch.org/blog/how-to-train-state-of-the-art-models-using-torchvision-latest-primitives/>`_.
            """,
        },
    )
    DEFAULT = IMAGENET1K_V2


def resnet50(
    *, weights: ResNet50_Weights | None = None, progress: bool = True, **kwargs: Any
) -> Any:
    return {"weights": weights, "progress": progress, **kwargs}


def test_use_custom_enum_handler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    file_regression: FileRegressionFixture,
):
    from hydra_auto_schema.customize import custom_enum_schemas

    def _handle_torchvision_weights_enum(enum_type: type[WeightsEnum], schema):
        @dataclass
        class Dummy:
            value: str

        slightly_changed_schema = schema | {
            "members": [Dummy(v.name) for v in schema["members"]]
        }
        return slightly_changed_schema

    mock = Mock(
        spec=_handle_torchvision_weights_enum, wraps=_handle_torchvision_weights_enum
    )

    monkeypatch.setitem(custom_enum_schemas, ResNet50_Weights, mock)

    config = {
        "_target_": f"{resnet50.__module__}.{resnet50.__name__}",
    }
    config_file = tmp_path / "config.yaml"
    omegaconf.OmegaConf.save(config, config_file)

    schema = _create_schema_for_config(
        config,
        config_file,
        configs_dir=tmp_path,
        repo_root=tmp_path,
        config_store=None,
    )
    mock.assert_called()
    file_regression.check(
        json.dumps(schema, indent=2),
        extension=".json",
    )
