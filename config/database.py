import psycopg2
from psycopg2.extras import RealDictCursor

from config.settings import settings


def get_connection():
    """
    Returns PostgreSQL connection.
    """

    return psycopg2.connect(
        host=settings.PGHOST,
        port=settings.PGPORT,
        dbname=settings.PGDATABASE,
        user=settings.PGUSER,
        password=settings.PGPASSWORD,
        cursor_factory=RealDictCursor
    )


def test_connection():
    """
    Test PostgreSQL connectivity.
    """

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("SELECT version();")

    version = cur.fetchone()

    print("Connected Successfully")
    print(version)

    cur.close()
    conn.close()