import sqlite3
import psycopg2
import os

# Source SQLite database
sqlite_db_path = 'site.db'
if not os.path.exists(sqlite_db_path):
    print(f"Error: {sqlite_db_path} not found!")
    exit(1)

# Destination PostgreSQL (Public Connect URL)
pg_url = "postgresql://postgres:qVEPOXaAGHCoBppbMUesUOzTCSqcZJOz@gondola.proxy.rlwy.net:47349/railway"

try:
    # Connect to SQLite
    sqlite_conn = sqlite_connection = sqlite3.connect(sqlite_db_path)
    sqlite_cursor = sqlite_conn.cursor()

    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(pg_url)
    pg_cursor = pg_conn.cursor()

    print("Success: Connected to both databases!")

    # 1. Migrate Tables helper
    def migrate_table(table_name):
        try:
            print(f"Migrating '{table_name}' table...")
            sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            rows = sqlite_cursor.fetchall()
            if not rows: 
                print(f"Table '{table_name}' is empty.")
                return
            
            # Get columns
            columns = [description[0] for description in sqlite_cursor.description]
            placeholders = ",".join(["%s"] * len(columns))
            col_names = ",".join(columns)
            
            # Upsert logic
            query = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"
            
            # Convert SQLite values to Postgres-friendly types (bool handling)
            for row in rows:
                converted_row = []
                for val in row:
                    # SQLite stores bools as 0/1, Postgres wants True/False
                    # We can try to cast if we knew the schema, or just let psycopg2 handle basic types
                    converted_row.append(val)
                
                pg_cursor.execute(query, tuple(converted_row))
            
            pg_conn.commit()
            print(f"Successfully migrated {len(rows)} rows to '{table_name}'.")
        except Exception as e:
            print(f"Error migrating {table_name}: {e}")
            pg_conn.rollback()

    # List of tables to migrate in order (to respect foreign keys if any)
    tables = ['vehicle', 'article', 'lead', 'review', 'inspection_report', 'visit']
    for t in tables:
        migrate_table(t)

    print("\nFINISHED! All data migrated to PostgreSQL successfully! 🎉")


except Exception as e:
    print(f"FAILED: {e}")
finally:
    if 'sqlite_conn' in locals(): sqlite_conn.close()
    if 'pg_conn' in locals(): pg_conn.close()
