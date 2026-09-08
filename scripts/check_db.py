import os

import psycopg

conninfo = (
    f"host={os.environ['POSTGRES_HOST']} "
    f"port={os.environ['POSTGRES_PORT']} "
    f"user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']} "
    f"dbname={os.environ['POSTGRES_DB']}"
)

with psycopg.connect(conninfo) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone()[0])

        cur.execute(
            "CREATE TABLE IF NOT EXISTS connection_check ("
            "  id serial PRIMARY KEY,"
            "  checked_at timestamptz NOT NULL DEFAULT now()"
            ")"
        )
        cur.execute("INSERT INTO connection_check DEFAULT VALUES")

        cur.execute("SELECT count(*) FROM connection_check")
        print("rows in connection_check:", cur.fetchone()[0])