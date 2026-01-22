# migrate_to_postgres.py - SQLite에서 PostgreSQL로 데이터 마이그레이션
# 사용법: python migrate_to_postgres.py
# -*- coding: utf-8 -*-

import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import os
from datetime import datetime
from db_config.database import get_connection_params, get_log_connection_params

# SQLite 데이터베이스 경로
SQLITE_MAIN_DB = "data/discord_minecraft.db"
SQLITE_LOG_DB = "data/logs/bot_logs.db"


def migrate_main_database():
    """메인 데이터베이스 마이그레이션 (discord_minecraft.db)"""
    print("\n" + "="*60)
    print("메인 데이터베이스 마이그레이션 시작")
    print("="*60)

    if not os.path.exists(SQLITE_MAIN_DB):
        print(f"[SKIP] SQLite 파일이 존재하지 않음: {SQLITE_MAIN_DB}")
        return

    # SQLite 연결
    sqlite_conn = sqlite3.connect(SQLITE_MAIN_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # PostgreSQL 연결
    pg_conn = psycopg2.connect(**get_connection_params())
    pg_cursor = pg_conn.cursor()

    try:
        # 1. users 테이블 마이그레이션
        print("\n[1/7] users 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT * FROM users")
        users = sqlite_cursor.fetchall()

        if users:
            pg_cursor.execute("DELETE FROM callsign_cooldowns")
            pg_cursor.execute("DELETE FROM callsign_history")
            pg_cursor.execute("DELETE FROM callsigns")
            pg_cursor.execute("DELETE FROM nation_history")
            pg_cursor.execute("DELETE FROM minecraft_name_history")
            pg_cursor.execute("DELETE FROM users")

            for user in users:
                pg_cursor.execute('''
                    INSERT INTO users (discord_id, minecraft_uuid, current_minecraft_name, first_seen, last_updated)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (discord_id) DO UPDATE SET
                        minecraft_uuid = EXCLUDED.minecraft_uuid,
                        current_minecraft_name = EXCLUDED.current_minecraft_name,
                        first_seen = EXCLUDED.first_seen,
                        last_updated = EXCLUDED.last_updated
                ''', (user['discord_id'], user['minecraft_uuid'], user['current_minecraft_name'],
                      user['first_seen'], user['last_updated']))
            print(f"   -> {len(users)}개 사용자 마이그레이션 완료")
        else:
            print("   -> 마이그레이션할 사용자 없음")

        # 2. minecraft_name_history 테이블 마이그레이션
        print("\n[2/7] minecraft_name_history 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT * FROM minecraft_name_history")
        history = sqlite_cursor.fetchall()

        if history:
            for record in history:
                pg_cursor.execute('''
                    INSERT INTO minecraft_name_history (discord_id, minecraft_uuid, minecraft_name, changed_at)
                    VALUES (%s, %s, %s, %s)
                ''', (record['discord_id'], record['minecraft_uuid'], record['minecraft_name'], record['changed_at']))
            print(f"   -> {len(history)}개 히스토리 마이그레이션 완료")
        else:
            print("   -> 마이그레이션할 히스토리 없음")

        # 3. nation_history 테이블 마이그레이션
        print("\n[3/7] nation_history 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT * FROM nation_history")
        nation_history = sqlite_cursor.fetchall()

        # 존재하는 user discord_id 목록 가져오기
        pg_cursor.execute("SELECT discord_id FROM users")
        existing_users = set(row[0] for row in pg_cursor.fetchall())

        if nation_history:
            migrated = 0
            skipped = 0
            for record in nation_history:
                # users 테이블에 없는 discord_id는 스킵
                if record['discord_id'] not in existing_users:
                    skipped += 1
                    continue
                nation_ranks = record['nation_ranks'] if 'nation_ranks' in record.keys() else None
                town_ranks = record['town_ranks'] if 'town_ranks' in record.keys() else None
                pg_cursor.execute('''
                    INSERT INTO nation_history (discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks, changed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (record['discord_id'], record['nation_name'], record['nation_uuid'],
                      record['town_name'], record['town_uuid'], nation_ranks, town_ranks, record['changed_at']))
                migrated += 1
            print(f"   -> {migrated}개 국가 히스토리 마이그레이션 완료 (스킵: {skipped}개)")
        else:
            print("   -> 마이그레이션할 국가 히스토리 없음")

        # 4. callsigns 테이블 마이그레이션
        print("\n[4/7] callsigns 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='callsigns'")
        if sqlite_cursor.fetchone():
            sqlite_cursor.execute("SELECT * FROM callsigns")
            callsigns = sqlite_cursor.fetchall()

            if callsigns:
                migrated = 0
                skipped = 0
                for record in callsigns:
                    if record['discord_id'] not in existing_users:
                        skipped += 1
                        continue
                    pg_cursor.execute('''
                        INSERT INTO callsigns (discord_id, callsign, set_at, admin_override)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (discord_id) DO UPDATE SET
                            callsign = EXCLUDED.callsign,
                            set_at = EXCLUDED.set_at,
                            admin_override = EXCLUDED.admin_override
                    ''', (record['discord_id'], record['callsign'], record['set_at'], record['admin_override']))
                    migrated += 1
                print(f"   -> {migrated}개 콜사인 마이그레이션 완료 (스킵: {skipped}개)")
            else:
                print("   -> 마이그레이션할 콜사인 없음")
        else:
            print("   -> callsigns 테이블 없음")

        # 5. callsign_history 테이블 마이그레이션
        print("\n[5/7] callsign_history 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='callsign_history'")
        if sqlite_cursor.fetchone():
            sqlite_cursor.execute("SELECT * FROM callsign_history")
            callsign_history = sqlite_cursor.fetchall()

            if callsign_history:
                migrated = 0
                skipped = 0
                for record in callsign_history:
                    if record['discord_id'] not in existing_users:
                        skipped += 1
                        continue
                    pg_cursor.execute('''
                        INSERT INTO callsign_history (discord_id, callsign, set_at, admin_override)
                        VALUES (%s, %s, %s, %s)
                    ''', (record['discord_id'], record['callsign'], record['set_at'], record['admin_override']))
                    migrated += 1
                print(f"   -> {migrated}개 콜사인 히스토리 마이그레이션 완료 (스킵: {skipped}개)")
            else:
                print("   -> 마이그레이션할 콜사인 히스토리 없음")
        else:
            print("   -> callsign_history 테이블 없음")

        # 6. callsign_cooldowns 테이블 마이그레이션
        print("\n[6/7] callsign_cooldowns 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='callsign_cooldowns'")
        if sqlite_cursor.fetchone():
            sqlite_cursor.execute("SELECT * FROM callsign_cooldowns")
            cooldowns = sqlite_cursor.fetchall()

            if cooldowns:
                migrated = 0
                skipped = 0
                for record in cooldowns:
                    if record['discord_id'] not in existing_users:
                        skipped += 1
                        continue
                    pg_cursor.execute('''
                        INSERT INTO callsign_cooldowns (discord_id, cooldown_end, set_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (discord_id) DO UPDATE SET
                            cooldown_end = EXCLUDED.cooldown_end,
                            set_at = EXCLUDED.set_at
                    ''', (record['discord_id'], record['cooldown_end'], record['set_at']))
                print(f"   -> {len(cooldowns)}개 쿨타임 마이그레이션 완료")
            else:
                print("   -> 마이그레이션할 쿨타임 없음")
        else:
            print("   -> callsign_cooldowns 테이블 없음")

        # 7. all_players 테이블 마이그레이션
        print("\n[7/7] all_players 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='all_players'")
        if sqlite_cursor.fetchone():
            sqlite_cursor.execute("SELECT * FROM all_players")
            all_players = sqlite_cursor.fetchall()

            if all_players:
                pg_cursor.execute("DELETE FROM all_players")
                for player in all_players:
                    pg_cursor.execute('''
                        INSERT INTO all_players (uuid, name, nation, town, nation_ranks, town_ranks, last_updated)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (uuid) DO UPDATE SET
                            name = EXCLUDED.name,
                            nation = EXCLUDED.nation,
                            town = EXCLUDED.town,
                            nation_ranks = EXCLUDED.nation_ranks,
                            town_ranks = EXCLUDED.town_ranks,
                            last_updated = EXCLUDED.last_updated
                    ''', (player['uuid'], player['name'], player['nation'], player['town'],
                          player['nation_ranks'], player['town_ranks'], player['last_updated']))
                print(f"   -> {len(all_players)}개 플레이어 마이그레이션 완료")
            else:
                print("   -> 마이그레이션할 플레이어 없음")
        else:
            print("   -> all_players 테이블 없음")

        pg_conn.commit()
        print("\n[OK] 메인 데이터베이스 마이그레이션 완료!")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n[ERROR] 메인 데이터베이스 마이그레이션 실패: {e}")
        raise

    finally:
        sqlite_conn.close()
        pg_conn.close()


def migrate_log_database():
    """로그 데이터베이스 마이그레이션 (bot_logs.db)"""
    print("\n" + "="*60)
    print("로그 데이터베이스 마이그레이션 시작")
    print("="*60)

    if not os.path.exists(SQLITE_LOG_DB):
        print(f"[SKIP] SQLite 로그 파일이 존재하지 않음: {SQLITE_LOG_DB}")
        return

    # SQLite 연결
    sqlite_conn = sqlite3.connect(SQLITE_LOG_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # PostgreSQL 연결
    pg_conn = psycopg2.connect(**get_log_connection_params())
    pg_cursor = pg_conn.cursor()

    try:
        # logs 테이블 생성 (없는 경우)
        pg_cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                time TEXT NOT NULL,
                timestamp DOUBLE PRECISION NOT NULL,
                level TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                user_id BIGINT,
                user_name TEXT,
                target_user_id BIGINT,
                target_user_name TEXT,
                command TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        pg_conn.commit()

        # logs 테이블 마이그레이션
        print("\n[1/1] logs 테이블 마이그레이션...")
        sqlite_cursor.execute("SELECT * FROM logs")
        logs = sqlite_cursor.fetchall()

        if logs:
            # 기존 로그 삭제 (선택적)
            # pg_cursor.execute("DELETE FROM logs")

            batch_size = 1000
            total = len(logs)
            migrated = 0

            for i in range(0, total, batch_size):
                batch = logs[i:i+batch_size]
                for log in batch:
                    pg_cursor.execute('''
                        INSERT INTO logs (time, timestamp, level, category, message, user_id, user_name,
                                         target_user_id, target_user_name, command, details)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (log['time'], log['timestamp'], log['level'], log['category'], log['message'],
                          log['user_id'], log['user_name'], log['target_user_id'], log['target_user_name'],
                          log['command'], log['details']))
                migrated += len(batch)
                print(f"   -> {migrated}/{total} 로그 처리 중...")

            print(f"   -> {total}개 로그 마이그레이션 완료")
        else:
            print("   -> 마이그레이션할 로그 없음")

        pg_conn.commit()
        print("\n[OK] 로그 데이터베이스 마이그레이션 완료!")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n[ERROR] 로그 데이터베이스 마이그레이션 실패: {e}")
        raise

    finally:
        sqlite_conn.close()
        pg_conn.close()


def verify_migration():
    """마이그레이션 검증"""
    print("\n" + "="*60)
    print("마이그레이션 검증")
    print("="*60)

    # PostgreSQL 연결
    pg_conn = psycopg2.connect(**get_connection_params())
    pg_cursor = pg_conn.cursor()

    try:
        tables = ['users', 'minecraft_name_history', 'nation_history',
                  'callsigns', 'callsign_history', 'callsign_cooldowns', 'all_players']

        print("\nPostgreSQL 테이블 레코드 수:")
        for table in tables:
            pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = pg_cursor.fetchone()[0]
            print(f"   - {table}: {count}개")

        # SQLite와 비교 (파일이 있는 경우)
        if os.path.exists(SQLITE_MAIN_DB):
            sqlite_conn = sqlite3.connect(SQLITE_MAIN_DB)
            sqlite_cursor = sqlite_conn.cursor()

            print("\nSQLite vs PostgreSQL 비교:")
            for table in tables:
                try:
                    sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    sqlite_count = sqlite_cursor.fetchone()[0]
                    pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    pg_count = pg_cursor.fetchone()[0]

                    status = "[OK]" if sqlite_count == pg_count else "[DIFF]"
                    print(f"   {status} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
                except Exception as e:
                    print(f"   [SKIP] {table}: {e}")

            sqlite_conn.close()

    finally:
        pg_conn.close()


def main():
    """메인 함수"""
    print("="*60)
    print("SQLite -> PostgreSQL 마이그레이션 스크립트")
    print("="*60)
    print(f"\n시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # 1. 메인 데이터베이스 마이그레이션
        migrate_main_database()

        # 2. 로그 데이터베이스 마이그레이션
        migrate_log_database()

        # 3. 검증
        verify_migration()

        print("\n" + "="*60)
        print("[SUCCESS] 모든 마이그레이션이 완료되었습니다!")
        print("="*60)
        print("\n다음 단계:")
        print("1. .env 파일에 PostgreSQL 연결 정보가 설정되어 있는지 확인하세요")
        print("2. 봇을 재시작하여 PostgreSQL 연결을 테스트하세요")
        print("3. 기존 SQLite 파일은 백업으로 보관하세요")

    except Exception as e:
        print(f"\n[FAILED] 마이그레이션 실패: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
