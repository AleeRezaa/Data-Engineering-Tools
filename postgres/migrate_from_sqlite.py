"""
This code is written to migrate superset internal data from a SQLite database to PostgreSQL.
It connects to both databases, retrieves the list of tables, and for each table, it identifies the common columns between SQLite and PostgreSQL.
It then reads the data from SQLite, converts it to match PostgreSQL types, and inserts it into the corresponding PostgreSQL table.
The script also handles transactions, resets sequences for auto-incrementing IDs, and provides a summary of the migration results.
"""

import sqlite3
import uuid

import psycopg2
import psycopg2.extras

SQLITE_PATH = "/data/superset.db"
PG_DSN = "host=localhost port=5432 dbname=superset user=**** password=****"
ONLY_TABLES = False
# ONLY_TABLES = {"dashboards", "dbs", "key_value", "table_columns", "sql_metrics", "saved_query", "tables", "slices"}
SKIP_TABLES = {"alembic_version"}


def get_pg_connection():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    return conn


def get_pg_tables(pg_conn):
    cur = pg_conn.cursor()
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """
    )
    return [row[0] for row in cur.fetchall()]


def get_pg_columns_with_types(pg_conn, table):
    """Get column names AND data types for a table in PG"""
    cur = pg_conn.cursor()
    cur.execute(
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """,
        (table,),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def get_sqlite_columns(sq_conn, table):
    cur = sq_conn.execute(f"PRAGMA table_info('{table}')")
    return [row[1] for row in cur.fetchall()]


def convert_row(row, col_types):
    """Convert a SQLite row to match PG types"""
    converted = []
    for val, (col_name, pg_type) in zip(row, col_types):
        if val is None:
            converted.append(None)
        elif pg_type == "boolean":
            converted.append(bool(val))
        elif pg_type == "uuid":
            # SQLite stores UUID as 16-byte blob → convert to UUID string
            if isinstance(val, bytes) and len(val) == 16:
                converted.append(str(uuid.UUID(bytes=val)))
            elif isinstance(val, str):
                # Already a string UUID (some versions of superset do this)
                converted.append(val)
            else:
                converted.append(str(uuid.UUID(bytes=val)))
        elif isinstance(val, bytes):
            converted.append(psycopg2.Binary(val))
        else:
            converted.append(val)
    return tuple(converted)


def migrate():
    sq_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = get_pg_connection()
    pg_cur = pg_conn.cursor()

    pg_cur.execute("SET session_replication_role = 'replica';")

    pg_tables = get_pg_tables(pg_conn)

    success = []
    skipped = []
    failed = []

    for table in pg_tables:
        if table in SKIP_TABLES:
            skipped.append(table)
            continue
        if ONLY_TABLES and table not in ONLY_TABLES:
            continue

        pg_col_info = get_pg_columns_with_types(pg_conn, table)
        pg_cols = [c[0] for c in pg_col_info]
        sq_cols = get_sqlite_columns(sq_conn, table)

        if not sq_cols:
            skipped.append(table)
            continue

        # Only columns in BOTH, keep PG order and types
        common_col_info = [(name, dtype) for name, dtype in pg_col_info if name in sq_cols]
        common_cols = [c[0] for c in common_col_info]

        if not common_cols:
            skipped.append(table)
            continue

        col_list = ", ".join(f'"{c}"' for c in common_cols)
        placeholders = ", ".join(["%s"] * len(common_cols))

        try:
            # Reconnect if needed
            if pg_conn.closed:
                pg_conn = get_pg_connection()
                pg_cur = pg_conn.cursor()
                pg_cur.execute("SET session_replication_role = 'replica';")

            pg_cur.execute(f'DELETE FROM "{table}";')  # TRUNCATE TABLE "{table}" CASCADE;

            rows = sq_conn.execute(f'SELECT {col_list} FROM "{table}"').fetchall()

            if rows:
                converted_rows = [convert_row(row, common_col_info) for row in rows]

                insert_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'

                # Insert in small batches to avoid OOM/connection drops
                BATCH = 100
                for i in range(0, len(converted_rows), BATCH):
                    batch = converted_rows[i : i + BATCH]
                    psycopg2.extras.execute_batch(pg_cur, insert_sql, batch, page_size=50)

            pg_conn.commit()
            success.append(f"{table} ({len(rows)} rows)")
            print(f"✓ {table}: {len(rows)} rows")

        except Exception as e:
            try:
                pg_conn.rollback()
            except:
                # Connection is dead, reconnect
                pg_conn = get_pg_connection()
                pg_cur = pg_conn.cursor()
            pg_cur.execute("SET session_replication_role = 'replica';")
            failed.append(f"{table}: {e}")
            print(f"✗ {table}: {e}")

    # Reset sequences
    print("\n— Resetting sequences...")
    if pg_conn.closed:
        pg_conn = get_pg_connection()
        pg_cur = pg_conn.cursor()

    pg_cur.execute(
        """
        SELECT table_name, column_name, pg_get_serial_sequence(table_name, column_name)
        FROM information_schema.columns
        WHERE table_schema = 'public' AND column_default LIKE 'nextval%%'
    """
    )
    for table_name, col_name, seq in pg_cur.fetchall():
        if seq:
            try:
                pg_cur.execute(f'SELECT COALESCE(MAX("{col_name}"), 0) FROM "{table_name}"')
                max_val = pg_cur.fetchone()[0]
                pg_cur.execute(f"SELECT setval('{seq}', {max_val + 1}, false)")
            except:
                pg_conn.rollback()

    pg_cur.execute("SET session_replication_role = 'origin';")
    pg_conn.commit()

    print(f"\n{'='*50}")
    print(f"Success: {len(success)} tables")
    print(f"Skipped: {len(skipped)} tables")
    print(f"Failed:  {len(failed)} tables")
    for f in failed:
        print(f"  - {f}")

    sq_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    migrate()
