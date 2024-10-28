# hydra-auto-schema

Automagically create yaml schemas for your Hydra config files

## Installation

### uv (recommended)

```console
uv tool install git+https://www.github.com/lebrice/hydra-auto-schema
```

### pip

```console
pip install git+https://www.github.com/lebrice/hydra-auto-schema
```

### Usage

Generate the yaml schemas for all the configs in the `configs` folder:

```console
hydra-auto-schema configs
```

Watch for changes in the `configs` folder and update the schemas as needed:

```console
hydra-auto-schema configs --watch
```
