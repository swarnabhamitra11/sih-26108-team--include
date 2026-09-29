import os
import sys
import argparse
import psycopg2
from pathlib import Path


def load_env(env_path: Path):
    # Simple .env loader (ignores comments, empty lines)
    env = {}
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, val = line.split('=', 1)
            env[key.strip()] = val.strip()
    return env


def render_sql(template_path: Path, dim: str) -> str:
    sql = template_path.read_text()
    return sql.replace('%%EMBEDDING_DIM%%', dim)


def execute_sql(conn, sql: str):
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception as e:
        print(f"SQL Error during execution: {e}")
        conn.rollback()
        sys.exit(1)


def reset_schema(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE;")
            cur.execute("CREATE SCHEMA public;")
        conn.commit()
    except Exception as e:
        print(f"SQL Error during schema reset: {e}")
        conn.rollback()
        sys.exit(1)


def verify_tables_and_extensions(conn):
    expected_tables = {
        'product_group', 'family', 'standards', 'certification_rules',
        'benchmark_rows', 'benchmark_expected', 'queries', 'reviews',
        'standard_editions', 'standard_amendments', 'standard_relations'
    }
    # Verify tables
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        rows = cur.fetchall()
    actual = {row[0] for row in rows}
    missing = expected_tables - actual
    if missing:
        print(f"Missing tables: {', '.join(sorted(missing))}")
        sys.exit(1)
    else:
        print("All expected tables are present.")
    # Verify extensions
    with conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension;")
        ext_rows = cur.fetchall()
    extensions = {row[0] for row in ext_rows}
    print("Installed extensions:")
    for ext in sorted(extensions):
        print(f" - {ext}")
    if 'vector' not in extensions:
        print("Missing required extension: vector")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Initialize or reset the Postgres schema for Standards Navigator')
    parser.add_argument('--reset', action='store_true', help='Drop existing schema before creating')
    args = parser.parse_args()

    # Load .env from project root explicitly, regardless of cwd
    env_path = Path(__file__).resolve().parents[1] / '.env'
    if not env_path.is_file():
        print('Error: .env file not found at expected path')
        sys.exit(1)
    env = load_env(env_path)

    defaults = {
        'POSTGRES_USER': 'user',
        'POSTGRES_PASSWORD': 'password',
        'POSTGRES_DB': 'standards',
        'POSTGRES_HOST': 'localhost',
        'POSTGRES_PORT': '5433',
        'EMBEDDING_DIM': '384',
    }
    for key, val in defaults.items():
        if key not in env or not env[key]:
            env[key] = val

    print(f"Loaded POSTGRES_USER={env['POSTGRES_USER']}, POSTGRES_DB={env['POSTGRES_DB']}, POSTGRES_HOST={env['POSTGRES_HOST']}, POSTGRES_PORT={env['POSTGRES_PORT']}")
    conn_str = (
        f"host={env['POSTGRES_HOST']} "
        f"port={env['POSTGRES_PORT']} "
        f"dbname={env['POSTGRES_DB']} "
        f"user={env['POSTGRES_USER']} "
        f"password={env['POSTGRES_PASSWORD']}"
    )
    try:
        conn = psycopg2.connect(conn_str)
    except Exception as e:
        print(f"Connection error: {e}")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.standards');")
            already_initialized = cur.fetchone()[0] is not None

        if args.reset:
            print('Resetting schema...')
            reset_schema(conn)
            already_initialized = False

        if not already_initialized:
            schema_path = Path(__file__).resolve().parents[1] / 'schema.sql'
            sql = render_sql(schema_path, env['EMBEDDING_DIM'])
            print('Applying schema...')
            execute_sql(conn, sql)
            print('Schema applied successfully.')
        else:
            print('Schema already exists, skipping schema creation.')

        verify_tables_and_extensions(conn)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
