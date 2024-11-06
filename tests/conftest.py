import pytest
from hydra.core.singleton import Singleton


@pytest.fixture(autouse=True)
def reset_singletons_between_tests():
    state = Singleton.get_state()

    yield

    Singleton.set_state(state)
