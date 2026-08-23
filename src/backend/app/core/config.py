from pydantic import field_validator
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
    tavily_api_key: str = ""
    firecrawl_api_key: str = ""
    firecrawl_mcp_url: str = ""

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # Railway PostgreSQL 有时给 postgres://，SQLAlchemy/psycopg 更统一用 postgresql://
        if value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://"):]
        return value

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
