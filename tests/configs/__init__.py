import dataclasses

from hydra.core.config_store import ConfigStore

cs = ConfigStore.instance()


@dataclasses.dataclass
class FooConfig:
    bar: str


# TODO: This still doesn't work!
cs.store(name="base_foo", node=FooConfig)
