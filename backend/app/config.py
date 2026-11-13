from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./lm.db"
    jwt_secret: str
    jwt_expire_minutes: int = 60
    max_upload_mb: int = 10

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()