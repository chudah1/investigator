from pathlib import Path

from dotenv import load_dotenv


DEFAULT_ENV_PATH = Path(__file__).with_name(".env")


def load_environment(env_path: Path | None = None) -> bool:
    """Load local configuration without replacing exported environment values."""
    return load_dotenv(
        dotenv_path=env_path or DEFAULT_ENV_PATH,
        override=False,
    )
