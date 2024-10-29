# hydra-auto-schema

Automagically create yaml schemas for your Hydra config files!

> 📢 If you are thinking of using Hydra for a PyTorch or Jax-based ML project, take a look at the [Research Project Template](https://github.com/mila-iqia/ResearchTemplate/) where this plugin was originally created and is best integrated!

## Demo

<video width="100%" controls="">
  <source src="https://github.com/user-attachments/assets/08f52d47-ebba-456d-95ef-ac9525d8e983" type="video/mp4">
</video>

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
