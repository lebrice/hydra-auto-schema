import hydra


@hydra.main(config_path="configs", config_name="config.yaml", version_base="1.2")
def app(config):
    print(config)
    return 1.23


if __name__ == "__main__":
    app()
