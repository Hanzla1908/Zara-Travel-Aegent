import os
from dotenv import load_dotenv


def load_config() -> None:
    load_dotenv()


def get(key: str, default: str = "") -> str:
    return os.getenv(key, default)
