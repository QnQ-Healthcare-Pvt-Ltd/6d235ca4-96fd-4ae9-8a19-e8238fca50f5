from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rules Engine API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "API for managing forms"
    
    SUPABASE_URL: str
    SUPABASE_KEY: str

    OPENAI_API_KEY: Optional[str] = None  # Make it optional


    # Database settings
    DB_HOST: Optional[str] = None
    DB_PASSWORD: Optional[str] = None

    # Email settings are now optional since we use dynamic config
    EMAIL_HOST: Optional[str] = None
    EMAIL_USER: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_PORT: Optional[int] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True  # This ensures DB_HOST matches exactly with .env

settings = Settings()