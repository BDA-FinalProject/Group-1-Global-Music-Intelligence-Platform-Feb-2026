import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # PostgreSQL
    PGHOST = os.getenv("PGHOST", "localhost")
    PGPORT = int(os.getenv("PGPORT", 5432))
    PGDATABASE = os.getenv("PGDATABASE", "gold")
    PGUSER = os.getenv("PGUSER", "postgres")
    PGPASSWORD = os.getenv("PGPASSWORD", "")

    # AWS
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    S3_GOLD_PREFIX = os.getenv("S3_GOLD_PREFIX")

    # Embeddings
    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL",
        "BAAI/bge-small-en-v1.5"
    )

    # Qdrant
    QDRANT_URL = os.getenv("QDRANT_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION = os.getenv(
        "QDRANT_COLLECTION",
        "spotify_gold_chunks"
    )


settings = Settings()