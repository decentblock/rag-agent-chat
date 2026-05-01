import os


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
EMEDDING_MODEL=os.getenv("EMEDDING_MODEL", "text-embedding-3-small")


SEARCH_K = int(os.getenv("SEARCH_K", "3"))

LOG_DIR = os.getenv("LOG_DIR", "/app/rag/logs")
PORT = int(os.getenv("PORT", "5000"))
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "/app/rag/chroma-db")
DEFAULT_COLLECTION_NAME=""

VERIFY_SSL = False
CHROMA_DB_FILE_PATH=r"C:/Users"