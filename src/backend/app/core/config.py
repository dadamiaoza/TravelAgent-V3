from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://travel:travel123@localhost:5434/travel_agent"
    llm_provider: str = "minimax"
    llm_model: str = "MiniMax-M2.7"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimaxi.com/v1"
    amap_api_key: str = ""
    qweather_project_id: str = ""
    qweather_key_id: str = ""
    qweather_private_key: str = ""
    qweather_api_host: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
