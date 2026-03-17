"""
SQLite → PostgreSQL 마이그레이션 스크립트

대상 SQLite DB:
  - data/bot.db           (메인 데이터)
  - data/discord_minecraft.db  (레거시 데이터)
  - data/logs/bot_logs.db (로그 데이터)

PostgreSQL에 이미 있는 행은 건너뜁니다 (ON CONFLICT DO NOTHING).
"""

import os
import sys
import sqlite3
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─── 설정 ────────────────────────────────────────────────────────────

SQLITE_MAIN = "data/bot.db"
SQLITE_LEGACY = "data/discord_minecraft.db"
SQLITE_LOGS = "data/logs/bot_logs.db"

PG_PARAMS = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "discord_bot"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

PG_LOG_PARAMS = PG_PARAMS.copy()
log_db = os.getenv("POSTGRES_LOG_DB")
if log_db:
    PG_LOG_PARAMS["dbname"] = log_db


# ─── 유틸 ────────────────────────────────────────────────────────────

def sqlite_conn(path):
    if not os.path.exists(path):
        print(f"  [SKIP] {path} 파일 없음")
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def pg_conn(params=None):
    return psycopg2.connect(**(params or PG_PARAMS))


def get_sqlite_tables(conn):
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
    return [r[0] for r in c.fetchall()]


def fetch_all_dicts(conn, table):
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table}")
    rows = c.fetchall()
    if not rows:
        return [], []
    cols = [desc[0] for desc in c.description]
    return cols, [dict(r) for r in rows]


# PostgreSQL BOOLEAN 컬럼 목록 캐시
_bool_cols_cache = {}

def get_bool_columns(pg_cur, table):
    """PostgreSQL 테이블에서 BOOLEAN 타입 컬럼 목록 반환"""
    if table not in _bool_cols_cache:
        pg_cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND data_type = 'boolean'",
            (table,)
        )
        _bool_cols_cache[table] = {r[0] for r in pg_cur.fetchall()}
    return _bool_cols_cache[table]


def convert_values(pg_cur, table, dst_cols, values):
    """SQLite 0/1 → PostgreSQL BOOLEAN 변환"""
    bool_cols = get_bool_columns(pg_cur, table)
    if not bool_cols:
        return values
    result = []
    for col, val in zip(dst_cols, values):
        if col in bool_cols and val is not None:
            result.append(bool(val))
        else:
            result.append(val)
    return result


# ─── PK 기반 테이블 마이그레이션 (ON CONFLICT DO NOTHING) ──────────

def migrate_pk_table(sq_conn, pg_cur, table, pk_col, col_mapping=None):
    """PK가 있는 테이블을 마이그레이션. col_mapping: {sqlite_col: pg_col} 또는 None"""
    cols, rows = fetch_all_dicts(sq_conn, table)
    if not rows:
        print(f"  [{table}] SQLite 데이터 없음 → 건너뜀")
        return 0

    # PostgreSQL 테이블의 실제 컬럼 확인
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
        (table,)
    )
    pg_cols = {r[0] for r in pg_cur.fetchall()}

    # SQLite 컬럼 중 PostgreSQL에도 존재하는 것만 사용
    valid_cols = [c for c in cols if c in pg_cols]
    if col_mapping:
        valid_cols_mapped = []
        for c in cols:
            mapped = col_mapping.get(c, c)
            if mapped in pg_cols:
                valid_cols_mapped.append((c, mapped))
        valid_cols_pairs = valid_cols_mapped
    else:
        valid_cols_pairs = [(c, c) for c in valid_cols]

    if not valid_cols_pairs:
        print(f"  [{table}] 매칭되는 컬럼 없음 → 건너뜀")
        return 0

    src_cols = [p[0] for p in valid_cols_pairs]
    dst_cols = [p[1] for p in valid_cols_pairs]
    placeholders = ", ".join(["%s"] * len(dst_cols))
    col_list = ", ".join(dst_cols)

    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT ({pk_col}) DO NOTHING"

    inserted = 0
    for row in rows:
        values = convert_values(pg_cur, table, dst_cols, [row.get(c) for c in src_cols])
        try:
            pg_cur.execute(sql, values)
            if pg_cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"    [WARN] {table} 삽입 실패: {e}")
            pg_cur.connection.rollback()

    print(f"  [{table}] {len(rows)}행 중 {inserted}행 새로 삽입")
    return inserted


# ─── SERIAL PK 테이블 마이그레이션 (중복 체크 후 삽입) ────────────

def ensure_users_exist(pg_cur, rows, discord_id_col="discord_id"):
    """FK 제약 조건 충족을 위해 users 테이블에 없는 discord_id를 자동 추가"""
    ids = {r.get(discord_id_col) for r in rows if r.get(discord_id_col)}
    if not ids:
        return
    for did in ids:
        pg_cur.execute(
            "INSERT INTO users (discord_id, first_seen, last_updated) "
            "VALUES (%s, NOW(), NOW()) ON CONFLICT (discord_id) DO NOTHING",
            (did,)
        )


def migrate_serial_table(sq_conn, pg_cur, table, dedup_cols):
    """SERIAL id 테이블 마이그레이션. dedup_cols로 중복 체크."""
    cols, rows = fetch_all_dicts(sq_conn, table)
    if not rows:
        print(f"  [{table}] SQLite 데이터 없음 → 건너뜀")
        return 0

    # PostgreSQL 테이블의 실제 컬럼 확인
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
        (table,)
    )
    pg_cols = {r[0] for r in pg_cur.fetchall()}

    # id 컬럼 제외 (SERIAL), PostgreSQL에 있는 컬럼만
    valid_cols = [c for c in cols if c in pg_cols and c != 'id']
    if not valid_cols:
        print(f"  [{table}] 매칭되는 컬럼 없음 → 건너뜀")
        return 0

    placeholders = ", ".join(["%s"] * len(valid_cols))
    col_list = ", ".join(valid_cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    # 중복 체크용: 기존 데이터 해시 세트
    valid_dedup = [c for c in dedup_cols if c in pg_cols]
    existing = set()
    if valid_dedup:
        dedup_select = ", ".join(valid_dedup)
        pg_cur.execute(f"SELECT {dedup_select} FROM {table}")
        for r in pg_cur.fetchall():
            existing.add(tuple(str(v) for v in r))

    inserted = 0
    skipped = 0
    for row in rows:
        # 중복 체크
        if valid_dedup:
            key = tuple(str(row.get(c)) for c in valid_dedup)
            if key in existing:
                skipped += 1
                continue

        values = convert_values(pg_cur, table, valid_cols, [row.get(c) for c in valid_cols])
        try:
            pg_cur.execute(sql, values)
            inserted += 1
            if valid_dedup:
                key = tuple(str(row.get(c)) for c in valid_dedup)
                existing.add(key)
        except Exception as e:
            print(f"    [WARN] {table} 삽입 실패: {e}")
            pg_cur.connection.rollback()

    print(f"  [{table}] {len(rows)}행 중 {inserted}행 새로 삽입 ({skipped}행 중복 건너뜀)")
    return inserted


# ─── 메인 마이그레이션 ───────────────────────────────────────────────

def migrate_db(sqlite_path, label):
    print(f"\n{'='*60}")
    print(f"  {label}: {sqlite_path}")
    print(f"{'='*60}")

    sq = sqlite_conn(sqlite_path)
    if sq is None:
        return

    tables = get_sqlite_tables(sq)
    print(f"  SQLite 테이블: {tables}")

    conn = pg_conn()
    conn.autocommit = False
    cur = conn.cursor()

    total_inserted = 0

    try:
        # ── PK 기반 테이블 ──
        if "users" in tables:
            total_inserted += migrate_pk_table(sq, cur, "users", "discord_id")

        if "callsigns" in tables:
            total_inserted += migrate_pk_table(sq, cur, "callsigns", "discord_id")

        if "callsign_cooldowns" in tables:
            total_inserted += migrate_pk_table(sq, cur, "callsign_cooldowns", "discord_id")

        if "all_players" in tables:
            total_inserted += migrate_pk_table(sq, cur, "all_players", "uuid")

        if "all_nations" in tables:
            total_inserted += migrate_pk_table(sq, cur, "all_nations", "uuid")

        if "all_towns" in tables:
            total_inserted += migrate_pk_table(sq, cur, "all_towns", "uuid")

        if "warning_config" in tables:
            total_inserted += migrate_pk_table(sq, cur, "warning_config", "guild_id")

        # ── FK 의존 테이블 전에 users 확보 ──
        fk_tables = ["minecraft_name_history", "nation_history", "callsign_history",
                      "callsigns", "callsign_cooldowns", "warnings"]
        for t in fk_tables:
            if t in tables:
                _, t_rows = fetch_all_dicts(sq, t)
                ensure_users_exist(cur, t_rows)
        conn.commit()

        # ── SERIAL PK 테이블 (중복 체크) ──
        if "minecraft_name_history" in tables:
            total_inserted += migrate_serial_table(
                sq, cur, "minecraft_name_history",
                ["discord_id", "minecraft_name", "changed_at"]
            )

        if "nation_history" in tables:
            total_inserted += migrate_serial_table(
                sq, cur, "nation_history",
                ["discord_id", "nation_name", "town_name", "changed_at"]
            )

        if "callsign_history" in tables:
            total_inserted += migrate_serial_table(
                sq, cur, "callsign_history",
                ["discord_id", "callsign", "set_at"]
            )

        if "warnings" in tables:
            total_inserted += migrate_serial_table(
                sq, cur, "warnings",
                ["guild_id", "discord_id", "warned_by", "created_at"]
            )

        if "travels" in tables:
            total_inserted += migrate_serial_table(
                sq, cur, "travels",
                ["travel_id"]
            )

        conn.commit()
        print(f"\n  ✓ {label} 완료: 총 {total_inserted}행 새로 삽입")

    except Exception as e:
        conn.rollback()
        print(f"\n  ✗ {label} 실패: {e}")
        raise
    finally:
        cur.close()
        conn.close()
        sq.close()


def migrate_logs():
    print(f"\n{'='*60}")
    print(f"  로그 DB: {SQLITE_LOGS}")
    print(f"{'='*60}")

    sq = sqlite_conn(SQLITE_LOGS)
    if sq is None:
        return

    conn = pg_conn(PG_LOG_PARAMS)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # logs 테이블에 source/action 컬럼 확보
        cur.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS source TEXT")
        cur.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS action TEXT")
        conn.commit()

        total = migrate_serial_table(
            sq, cur, "logs",
            ["time", "level", "category", "message", "user_id"]
        )
        conn.commit()
        print(f"\n  ✓ 로그 마이그레이션 완료: {total}행 새로 삽입")

    except Exception as e:
        conn.rollback()
        print(f"\n  ✗ 로그 마이그레이션 실패: {e}")
        raise
    finally:
        cur.close()
        conn.close()
        sq.close()


def main():
    print("=" * 60)
    print("  SQLite → PostgreSQL 마이그레이션")
    print(f"  대상 PG: {PG_PARAMS['host']}:{PG_PARAMS['port']}/{PG_PARAMS['dbname']}")
    print(f"  시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1) 메인 DB (bot.db)
    migrate_db(SQLITE_MAIN, "메인 DB (bot.db)")

    # 2) 레거시 DB (discord_minecraft.db)
    migrate_db(SQLITE_LEGACY, "레거시 DB (discord_minecraft.db)")

    # 3) 로그 DB
    migrate_logs()

    print(f"\n{'='*60}")
    print("  마이그레이션 완료!")
    print(f"  종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
