# config/settings.py (Pydantic v1 compatible)
from pydantic import BaseSettings # Import from pydantic directly for v1
from typing import Optional 

class Settings(BaseSettings):
    # Core LLM settings
    GEMINI_MODEL_NAME: str = "qwen2:7b-instruct"  # Default; will be overridden by .env
    GEMINI_API_KEY: Optional[str] = None  

    # Ollama specific settings
    OLLAMA_API_BASE_URL: str = "http://localhost:11434"

    # Database settings
    DATABASE_URL: str = "federal_register.db" 

    # Federal Register API settings
    FEDERAL_REGISTER_API_BASE_URL: str = "https://www.federalregister.gov/api/v1/documents.json"
    EXECUTIVE_ORDER_DOCUMENT_TYPE: str = "PRESDOCU" # Value used for API query

    # Logging level
    LOG_LEVEL: str = "INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL

    class Config: # Pydantic v1 uses an inner Config class
        env_file = '.env'
        env_file_encoding = 'utf-8' # Good practice
        # For Pydantic v1, 'extra' fields are allowed by default if not specified.
        # If you needed to ignore/forbid, you'd use:
        # from pydantic import Extra
        # extra = Extra.ignore # or Extra.forbid
        # For now, omitting 'extra' is fine as Pydantic v1 is more lenient by default.

settings = Settings()

# Optional: Keep this logging if you find it useful for verifying settings load
import logging
logger = logging.getLogger(__name__) # Use __name__ for the logger
# This logging will only work if the global log level is set to DEBUG (e.g., in main.py)
# or if you explicitly set this logger's level.
if hasattr(settings, 'LOG_LEVEL') and settings.LOG_LEVEL.upper() == "DEBUG":
    logger.setLevel(logging.DEBUG) 
    logger.debug(f"DEBUG config.settings: Settings loaded. LOG_LEVEL='{settings.LOG_LEVEL}'")
    logger.debug(f"DEBUG config.settings: GEMINI_MODEL_NAME='{settings.GEMINI_MODEL_NAME}'")