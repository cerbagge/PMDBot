# db_config/database.py - 데이터베이스 설정 (SQLite/PostgreSQL 지원)

import os
import sqlite3
from dotenv import load_dotenv
from typing import Optional, Union
from enum import Enum

# .env 파일 로드 (여러 경로 시도)
for env_path in ['.env', '../.env']:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
else:
    load_dotenv()  # 기본 경로 시도


class DBType(Enum):
    """데이터베이스 타입"""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


def get_db_type() -> str:
    """현재 DB_TYPE 반환 (sqlite 또는 postgresql)"""
    return os.getenv("DB_TYPE", "sqlite").lower().strip()


def get_db_type_enum() -> DBType:
    """현재 설정된 데이터베이스 타입 반환 (Enum)"""
    db_type = get_db_type()
    if db_type in ("postgresql", "postgres", "pg"):
        return DBType.POSTGRESQL
    return DBType.SQLITE


def is_sqlite() -> bool:
    """SQLite 사용 여부"""
    return get_db_type_enum() == DBType.SQLITE


def is_postgresql() -> bool:
    """PostgreSQL 사용 여부"""
    return get_db_type_enum() == DBType.POSTGRESQL


# ===== SQLite 설정 =====

def get_sqlite_data_dir() -> str:
    """SQLite 데이터 디렉토리 경로"""
    return os.getenv("SQLITE_DATA_DIR", "data")


def get_sqlite_db_path() -> str:
    """SQLite 메인 DB 파일 경로"""
    data_dir = get_sqlite_data_dir()
    db_file = os.getenv("SQLITE_DB_FILE", "discord_minecraft.db")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, db_file)


def get_sqlite_log_db_path() -> str:
    """SQLite 로그 DB 파일 경로"""
    data_dir = get_sqlite_data_dir()
    log_dir = os.path.join(data_dir, "logs")
    db_file = os.getenv("SQLITE_LOG_DB_FILE", "bot_logs.db")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, db_file)


def get_sqlite_path() -> str:
    """SQLite 메인 DB 파일 경로 반환 (간단 경로)"""
    return os.getenv("SQLITE_DB_PATH", "data/bot.db")


def get_sqlite_log_path() -> str:
    """SQLite 로그 DB 파일 경로 반환 (간단 경로)"""
    return os.getenv("SQLITE_LOG_PATH", "data/logs/bot_logs.db")


# ===== PostgreSQL 설정 =====


def get_connection_params() -> dict:
    """PostgreSQL 연결 파라미터 반환"""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB", "discord_bot"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "")
    }


def get_log_connection_params() -> dict:
    """로그 DB PostgreSQL 연결 파라미터 반환"""
    postgres_db = os.getenv("POSTGRES_DB", "discord_bot")
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_LOG_DB") or postgres_db,
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "")
    }


def get_connection_string() -> str:
    """PostgreSQL 연결 문자열 반환"""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "discord_bot")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# ===== SQL 헬퍼 함수 =====

def get_placeholder() -> str:
    """SQL 플레이스홀더 반환 (SQLite: ?, PostgreSQL: %s)"""
    return "?" if is_sqlite() else "%s"


def get_auto_increment() -> str:
    """자동 증가 컬럼 타입 반환"""
    return "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite() else "SERIAL PRIMARY KEY"


def get_now_func() -> str:
    """현재 시간 함수 반환"""
    return "datetime('now', 'localtime')" if is_sqlite() else "NOW()"


def get_interval_sql(days: int) -> str:
    """날짜 간격 SQL 반환"""
    if is_sqlite():
        return f"datetime('now', '-{days} days')"
    return f"NOW() - INTERVAL '{days} days'"


def get_like_operator() -> str:
    """대소문자 무시 LIKE 연산자 반환 (SQLite는 기본 LIKE가 대소문자 무시)"""
    return "LIKE" if is_sqlite() else "ILIKE"


def adapt_sql(sql: str) -> str:
    """
    PostgreSQL SQL을 현재 DB 타입에 맞게 변환

    변환 사항:
    - %s -> ? (플레이스홀더)
    - SERIAL PRIMARY KEY -> INTEGER PRIMARY KEY AUTOINCREMENT
    - NOW() -> datetime('now', 'localtime')
    - ILIKE -> LIKE
    - INTERVAL '1 day' -> datetime 함수
    - BIGINT -> INTEGER
    - DEFAULT NOW() -> 제거 (SQLite에서는 트리거 또는 앱에서 처리)
    """
    if is_postgresql():
        return sql

    # SQLite용 변환
    result = sql

    # 플레이스홀더 변환
    result = result.replace("%s", "?")

    # 타입 변환
    result = result.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    result = result.replace("BIGINT", "INTEGER")

    # 함수 변환
    result = result.replace("NOW()", "datetime('now', 'localtime')")
    result = result.replace("ILIKE", "LIKE")

    # INTERVAL 변환 (단순 패턴)
    import re
    result = re.sub(
        r"NOW\(\)\s*-\s*INTERVAL\s*'(\d+)\s*days?'",
        r"datetime('now', '-\1 days')",
        result,
        flags=re.IGNORECASE
    )
    result = re.sub(
        r"NOW\(\)\s*-\s*INTERVAL\s*'(\d+)\s*day'",
        r"datetime('now', '-\1 days')",
        result,
        flags=re.IGNORECASE
    )

    return result


def get_db_info() -> str:
    """현재 데이터베이스 정보 문자열 반환"""
    if is_sqlite():
        return f"SQLite: {get_sqlite_db_path()}"
    else:
        params = get_connection_params()
        return f"PostgreSQL: {params['host']}:{params['port']}/{params['dbname']}"
