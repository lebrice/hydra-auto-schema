class Foo:
    def __init__(self, bar: str):
        """Description of the `Foo` class.

        Args:
            bar: Description of the `bar` argument.
        """
        self.bar = bar


class Bar(Foo):
    """Docstring of the Bar class.

    Args:
        baz: description of the `baz` argument from the cls docstring instead of the init docstring.
    """

    def __init__(self, bar: str, baz: int):
        # no docstring here.
        super().__init__(bar=bar)
        self.baz = baz
