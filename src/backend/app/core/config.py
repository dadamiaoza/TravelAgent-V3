from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://travel:travel123@localhost:5434/travel_agent"
    llm_provider: str = "minimax"
    llm_model: str = "MiniMax-M2.7"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimaxi.com/v1"
    amap_api_key: str = ""
    weather_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
