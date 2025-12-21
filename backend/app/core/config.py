"""Application configuration using Pydantic settings."""

from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Configuration
    app_name: str = "Explainable Agent API"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    # CORS Configuration
    cors_origins: List[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: List[str] = ["*"]
    cors_headers: List[str] = ["*"]

    # LLM Provider Selection
    llm_provider: str = "openai"  # options: openai, ollama, deepseek, groq
    # OpenAI Configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Ollama Configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    # DeepSeek Configuration
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # Groq Configuration
    groq_api_key: str = ""
    groq_model: str = "llama3-8b-8192"

    # LangSmith Configuration
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "default"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # Supabase Configuration
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    # Database Configuration
    database_path: str = "app/resource/northwind.db"
    
    # PostgreSQL Configuration
    postgres_host: str = "agent-postgres"
    postgres_port: int = 5432
    postgres_db: str = "agent_db"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    # MongoDB Configuration
    mongo_host: str = "mongodb"
    mongo_port: int = 27017
    mongo_username: str = "root"
    mongo_password: str = "explainable-agent-secret"
    mongo_database: str = "explainable_agent_db"
    mongo_auth_source: str = "admin"

    # Redis Configuration
    redis_url: str = "redis://redis:6379"
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_ttl: int = 3600  # DataFrame TTL in seconds (1 hour)

    # Logging Configuration
    logs_dir: str = "logs"
    log_level: str = "INFO"
    log_retention_days: int = 30

    # Security
    api_key: str = ""  # Optional API key for endpoints

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env


# Global settings instance
settings = Settings()


