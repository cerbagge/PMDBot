# db_config/db_adapter.py - Database Adapter Layer (PostgreSQL / SQLite)

import os
from dotenv import load_dotenv

# .env 파일 로드
for env_path in ['.env', '../.env']:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
else:
    load_dotenv()

DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower().strip()

if DB_TYPE not in ("sqlite", "postgresql"):
    print(f"⚠️ DB_TYPE '{DB_TYPE}'은(는) 지원하지 않습니다. 'sqlite' 또는 'postgresql'만 사용 가능합니다. sqlite로 대체합니다.")
    DB_TYPE = "sqlite"


class DbAdapter:
    """데이터베이스 어댑터 기본 클래스"""

    def get_connection(self):
        raise NotImplementedError

    def get_dict_cursor(self, conn):
        raise NotImplementedError

    def adapt_ddl(self, sql: str) -> str:
        raise NotImplementedError

    def adapt_sql(self, sql: str) -> str:
        raise NotImplementedError

    def add_column_safe(self, cursor, table: str, column: str, col_type: str, default=None):
        raise NotImplementedError

    def get_db_label(self) -> str:
        raise NotImplementedError


class PostgresAdapter(DbAdapter):
    """PostgreSQL 어댑터"""

    def __init__(self, conn_params: dict):
        import psycopg2
        from psycopg2.extras import RealDictCursor
        self._psycopg2 = psycopg2
        self._RealDictCursor = RealDictCursor
        self._conn_params = conn_params

    def get_connection(self):
        return self._psycopg2.connect(**self._conn_params)

    def get_dict_cursor(self, conn):
        return conn.cursor(cursor_factory=self._RealDictCursor)

    def adapt_ddl(self, sql: str) -> str:
        return sql

    def adapt_sql(self, sql: str) -> str:
        sql = sql.replace("{ph}", "%s")
        sql = sql.replace("{like_op}", "ILIKE")
        return sql

    def add_column_safe(self, cursor, table: str, column: str, col_type: str, default=None):
        default_clause = f" DEFAULT {default}" if default is not None else ""
        cursor.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}{default_clause}')

    def get_db_label(self) -> str:
        return f"PostgreSQL {self._conn_params['host']}:{self._conn_params['port']}/{self._conn_params['dbname']}"


class SQLiteAdapter(DbAdapter):
    """SQLite 어댑터"""

    def __init__(self, db_path: str):
        import sqlite3
        self._sqlite3 = sqlite3
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)

    def get_connection(self):
        conn = self._sqlite3.connect(self._db_path)
        conn.row_factory = self._sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def get_dict_cursor(self, conn):
        return conn.cursor()

    def adapt_ddl(self, sql: str) -> str:
        sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        sql = sql.replace("BIGINT PRIMARY KEY", "INTEGER PRIMARY KEY")
        sql = sql.replace("BIGINT", "INTEGER")
        sql = sql.replace("DOUBLE PRECISION", "REAL")
        sql = sql.replace("BOOLEAN", "INTEGER")
        sql = sql.replace("DEFAULT NOW()", "DEFAULT CURRENT_TIMESTAMP")
        sql = sql.replace("DEFAULT FALSE", "DEFAULT 0")
        sql = sql.replace("DEFAULT TRUE", "DEFAULT 1")
        # TEXT, INTEGER, REAL, TIMESTAMP 등은 SQLite에서도 그대로 사용 가능
        return sql

    def adapt_sql(self, sql: str) -> str:
        sql = sql.replace("{ph}", "%s")
        sql = sql.replace("{like_op}", "ILIKE")
        sql = sql.replace("%s", "?")
        sql = sql.replace("NOW()", "datetime('now')")
        sql = sql.replace(" ILIKE ", " LIKE ")
        return sql

    def add_column_safe(self, cursor, table: str, column: str, col_type: str, default=None):
        try:
            col_type = col_type.replace("BIGINT", "INTEGER").replace("DOUBLE PRECISION", "REAL").replace("BOOLEAN", "INTEGER")
            default_clause = f" DEFAULT {default}" if default is not None else ""
            cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}')
        except Exception:
            pass  # 컬럼이 이미 존재

    def get_db_label(self) -> str:
        return f"SQLite {self._db_path}"


def create_adapter(log: bool = False) -> DbAdapter:
    """DB_TYPE에 따라 적절한 어댑터를 생성하는 팩토리 함수"""
    if DB_TYPE == "postgresql":
        from db_config.database import get_connection_params, get_log_connection_params
        conn_params = get_log_connection_params() if log else get_connection_params()
        return PostgresAdapter(conn_params)
    else:
        if log:
            db_path = os.getenv("SQLITE_LOG_PATH", "data/logs/bot_logs.db")
        else:
            db_path = os.getenv("SQLITE_DB_PATH", "data/bot.db")
        return SQLiteAdapter(db_path)
