from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Finance"
    secret_key: str = "change-me"
    database_url: str = "sqlite:///./data/finance.db"
    timezone: str = "Asia/Shanghai"

    admin_username: str = "admin"
    admin_password: str = "admin123"

    telegram_bot_token: str = ""
    telegram_finance_chat_id: str = ""
    telegram_manager_chat_id: str = ""


settings = Settings()
