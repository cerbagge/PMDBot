# db_config/database.py - PostgreSQL 데이터베이스 설정

import os
from dotenv import load_dotenv

# .env 파일 로드 (여러 경로 시도)
for env_path in ['.env', '../.env']:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
else:
    load_dotenv()  # 기본 경로 시도

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
