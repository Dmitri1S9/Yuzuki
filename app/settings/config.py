from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(Path(__file__).resolve().parent.parent.parent, ".env"),
        env_file_encoding="utf-8",
        extra='allow',
    )
    # api key to openai
    api_key: str

    # db
    db_name: str
    db_password: str
    db_user: str

    # for localhost
    db_host: str
    db_port: str
    # for docker launch
    # DB_HOST: str
    # DB_PORT: str

    debug: bool

    # for docker
    # REDIS_URL=redis://redis:6379/0
    # for localhost
    redis_url_celery: str
    redis_url_cache: str

    api_key_x: str
    api_key_gemini: str


if __name__ == "__main__":
    ...
