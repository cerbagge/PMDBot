# migrate_database.py - SQLite <-> PostgreSQL 양방향 마이그레이션
# 사용법: python migrate_database.py [sqlite_to_pg | pg_to_sqlite | auto]
# -*- coding: utf-8 -*-

import sys
import io
import os
import argparse

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
from datetime import datetime
from db_config.database import (
    is_sqlite, is_postgresql,
    get_sqlite_db_path, get_sqlite_log_db_path,
    get_connection_params, get_log_connection_params
)

# PostgreSQL 지원 (선택적)
try:
    import psycopg2
    from psycopg2.extras import execute_values
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


class DatabaseMigrator:
    """양방향 데이터베이스 마이그레이션 클래스"""

    def __init__(self):
        self.sqlite_main_db = get_sqlite_db_path()
        self.sqlite_log_db = get_sqlite_log_db_path()

    def sqlite_to_postgresql(self):
        """SQLite에서 PostgreSQL로 마이그레이션"""
        if not HAS_PSYCOPG2:
            print("[ERROR] PostgreSQL을 사용하려면 psycopg2를 설치하세요: pip install psycopg2-binary")
            return False

        print("\n" + "=" * 60)
        print("SQLite -> PostgreSQL 마이그레이션")
        print("=" * 60)

        try:
            self._migrate_main_sqlite_to_pg()
            self._migrate_logs_sqlite_to_pg()
            print("\n[OK] SQLite -> PostgreSQL 마이그레이션 완료!")
            return True
        except Exception as e:
            print(f"\n[ERROR] 마이그레이션 실패: {e}")
            return False

    def postgresql_to_sqlite(self):
        """PostgreSQL에서 SQLite로 마이그레이션"""
        if not HAS_PSYCOPG2:
            print("[ERROR] PostgreSQL을 사용하려면 psycopg2를 설치하세요: pip install psycopg2-binary")
            return False

        print("\n" + "=" * 60)
        print("PostgreSQL -> SQLite 마이그레이션")
        print("=" * 60)

        try:
            self._migrate_main_pg_to_sqlite()
            self._migrate_logs_pg_to_sqlite()
            print("\n[OK] PostgreSQL -> SQLite 마이그레이션 완료!")
            return True
        except Exception as e:
            print(f"\n[ERROR] 마이그레이션 실패: {e}")
            return False

    def _migrate_main_sqlite_to_pg(self):
        """메인 DB: SQLite -> PostgreSQL"""
        print("\n[메인 DB] SQLite -> PostgreSQL")

        if not os.path.exists(self.sqlite_main_db):
            print(f"   [SKIP] SQLite 파일 없음: {self.sqlite_main_db}")
            return

        sqlite_conn = sqlite3.connect(self.sqlite_main_db)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()

        pg_conn = psycopg2.connect(**get_connection_params())
        pg_cursor = pg_conn.cursor()

        try:
            # users 테이블
            print("   - users 테이블...")
            sqlite_cursor.execute("SELECT * FROM users")
            users = sqlite_cursor.fetchall()
            if users:
                for user in users:
                    pg_cursor.execute('''
                        INSERT INTO users (discord_id, minecraft_uuid, current_minecraft_name, first_seen, last_updated)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (discord_id) DO UPDATE SET
                            minecraft_uuid = EXCLUDED.minecraft_uuid,
                            current_minecraft_name = EXCLUDED.current_minecraft_name,
                            last_updated = EXCLUDED.last_updated
                    ''', (user['discord_id'], user['minecraft_uuid'], user['current_minecraft_name'],
                          user['first_seen'], user['last_updated']))
                print(f"     -> {len(users)}개 완료")

            # minecraft_name_history 테이블
            print("   - minecraft_name_history 테이블...")
            sqlite_cursor.execute("SELECT * FROM minecraft_name_history")
            history = sqlite_cursor.fetchall()
            if history:
                for record in history:
                    pg_cursor.execute('''
                        INSERT INTO minecraft_name_history (discord_id, minecraft_uuid, minecraft_name, changed_at)
                        VALUES (%s, %s, %s, %s)
                    ''', (record['discord_id'], record['minecraft_uuid'], record['minecraft_name'], record['changed_at']))
                print(f"     -> {len(history)}개 완료")

            # nation_history 테이블
            print("   - nation_history 테이블...")
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nation_history'")
            if sqlite_cursor.fetchone():
                sqlite_cursor.execute("SELECT * FROM nation_history")
                nation_history = sqlite_cursor.fetchall()
                if nation_history:
                    for record in nation_history:
                        nation_ranks = record['nation_ranks'] if 'nation_ranks' in record.keys() else None
                        town_ranks = record['town_ranks'] if 'town_ranks' in record.keys() else None
                        pg_cursor.execute('''
                            INSERT INTO nation_history (discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks, changed_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (record['discord_id'], record['nation_name'], record['nation_uuid'],
                              record['town_name'], record['town_uuid'], nation_ranks, town_ranks, record['changed_at']))
                    print(f"     -> {len(nation_history)}개 완료")

            # callsigns 테이블
            self._migrate_table_sqlite_to_pg(sqlite_cursor, pg_cursor, 'callsigns',
                ['discord_id', 'callsign', 'set_at', 'admin_override'],
                upsert_key='discord_id')

            # callsign_history 테이블
            self._migrate_table_sqlite_to_pg(sqlite_cursor, pg_cursor, 'callsign_history',
                ['discord_id', 'callsign', 'set_at', 'admin_override'])

            # callsign_cooldowns 테이블
            self._migrate_table_sqlite_to_pg(sqlite_cursor, pg_cursor, 'callsign_cooldowns',
                ['discord_id', 'cooldown_end', 'set_at'],
                upsert_key='discord_id')

            # all_players 테이블
            self._migrate_table_sqlite_to_pg(sqlite_cursor, pg_cursor, 'all_players',
                ['uuid', 'name', 'nation', 'town', 'nation_ranks', 'town_ranks', 'last_updated'],
                upsert_key='uuid')

            pg_conn.commit()

        finally:
            sqlite_conn.close()
            pg_conn.close()

    def _migrate_table_sqlite_to_pg(self, sqlite_cursor, pg_cursor, table_name, columns, upsert_key=None):
        """SQLite 테이블을 PostgreSQL로 마이그레이션"""
        print(f"   - {table_name} 테이블...")
        sqlite_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not sqlite_cursor.fetchone():
            print(f"     [SKIP] 테이블 없음")
            return

        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()
        if not rows:
            print(f"     -> 0개 (비어있음)")
            return

        placeholders = ', '.join(['%s'] * len(columns))
        cols = ', '.join(columns)

        for row in rows:
            values = tuple(row[col] if col in row.keys() else None for col in columns)

            if upsert_key:
                update_cols = [f"{col} = EXCLUDED.{col}" for col in columns if col != upsert_key]
                pg_cursor.execute(f'''
                    INSERT INTO {table_name} ({cols})
                    VALUES ({placeholders})
                    ON CONFLICT ({upsert_key}) DO UPDATE SET {', '.join(update_cols)}
                ''', values)
            else:
                pg_cursor.execute(f'''
                    INSERT INTO {table_name} ({cols})
                    VALUES ({placeholders})
                ''', values)

        print(f"     -> {len(rows)}개 완료")

    def _migrate_logs_sqlite_to_pg(self):
        """로그 DB: SQLite -> PostgreSQL"""
        print("\n[로그 DB] SQLite -> PostgreSQL")

        if not os.path.exists(self.sqlite_log_db):
            print(f"   [SKIP] SQLite 로그 파일 없음: {self.sqlite_log_db}")
            return

        sqlite_conn = sqlite3.connect(self.sqlite_log_db)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()

        pg_conn = psycopg2.connect(**get_log_connection_params())
        pg_cursor = pg_conn.cursor()

        try:
            print("   - logs 테이블...")
            sqlite_cursor.execute("SELECT * FROM logs")
            logs = sqlite_cursor.fetchall()

            if logs:
                for log in logs:
                    pg_cursor.execute('''
                        INSERT INTO logs (time, timestamp, level, category, message, user_id, user_name,
                                         target_user_id, target_user_name, command, details)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (log['time'], log['timestamp'], log['level'], log['category'], log['message'],
                          log['user_id'], log['user_name'], log['target_user_id'], log['target_user_name'],
                          log['command'], log['details']))
                print(f"     -> {len(logs)}개 완료")

            pg_conn.commit()

        finally:
            sqlite_conn.close()
            pg_conn.close()

    def _migrate_main_pg_to_sqlite(self):
        """메인 DB: PostgreSQL -> SQLite"""
        print("\n[메인 DB] PostgreSQL -> SQLite")

        # SQLite 디렉토리 생성
        os.makedirs(os.path.dirname(self.sqlite_main_db), exist_ok=True)

        pg_conn = psycopg2.connect(**get_connection_params())
        pg_conn.set_client_encoding('UTF8')
        pg_cursor = pg_conn.cursor()

        sqlite_conn = sqlite3.connect(self.sqlite_main_db)
        sqlite_cursor = sqlite_conn.cursor()

        try:
            # users 테이블
            print("   - users 테이블...")
            pg_cursor.execute("SELECT discord_id, minecraft_uuid, current_minecraft_name, first_seen, last_updated FROM users")
            users = pg_cursor.fetchall()
            if users:
                for user in users:
                    sqlite_cursor.execute('''
                        INSERT OR REPLACE INTO users (discord_id, minecraft_uuid, current_minecraft_name, first_seen, last_updated)
                        VALUES (?, ?, ?, ?, ?)
                    ''', user)
                print(f"     -> {len(users)}개 완료")

            # minecraft_name_history 테이블
            print("   - minecraft_name_history 테이블...")
            pg_cursor.execute("SELECT discord_id, minecraft_uuid, minecraft_name, changed_at FROM minecraft_name_history")
            history = pg_cursor.fetchall()
            if history:
                for record in history:
                    sqlite_cursor.execute('''
                        INSERT INTO minecraft_name_history (discord_id, minecraft_uuid, minecraft_name, changed_at)
                        VALUES (?, ?, ?, ?)
                    ''', record)
                print(f"     -> {len(history)}개 완료")

            # nation_history 테이블
            print("   - nation_history 테이블...")
            pg_cursor.execute("SELECT discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks, changed_at FROM nation_history")
            nation_history = pg_cursor.fetchall()
            if nation_history:
                for record in nation_history:
                    sqlite_cursor.execute('''
                        INSERT INTO nation_history (discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks, changed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', record)
                print(f"     -> {len(nation_history)}개 완료")

            # callsigns 테이블
            self._migrate_table_pg_to_sqlite(pg_cursor, sqlite_cursor, 'callsigns',
                ['discord_id', 'callsign', 'set_at', 'admin_override'])

            # callsign_history 테이블
            self._migrate_table_pg_to_sqlite(pg_cursor, sqlite_cursor, 'callsign_history',
                ['discord_id', 'callsign', 'set_at', 'admin_override'])

            # callsign_cooldowns 테이블
            self._migrate_table_pg_to_sqlite(pg_cursor, sqlite_cursor, 'callsign_cooldowns',
                ['discord_id', 'cooldown_end', 'set_at'])

            # all_players 테이블
            self._migrate_table_pg_to_sqlite(pg_cursor, sqlite_cursor, 'all_players',
                ['uuid', 'name', 'nation', 'town', 'nation_ranks', 'town_ranks', 'last_updated'])

            sqlite_conn.commit()

        finally:
            pg_conn.close()
            sqlite_conn.close()

    def _migrate_table_pg_to_sqlite(self, pg_cursor, sqlite_cursor, table_name, columns):
        """PostgreSQL 테이블을 SQLite로 마이그레이션"""
        print(f"   - {table_name} 테이블...")

        try:
            cols = ', '.join(columns)
            pg_cursor.execute(f"SELECT {cols} FROM {table_name}")
            rows = pg_cursor.fetchall()
        except Exception as e:
            print(f"     [SKIP] 테이블 조회 실패: {e}")
            return

        if not rows:
            print(f"     -> 0개 (비어있음)")
            return

        placeholders = ', '.join(['?'] * len(columns))

        for row in rows:
            sqlite_cursor.execute(f'''
                INSERT OR REPLACE INTO {table_name} ({cols})
                VALUES ({placeholders})
            ''', row)

        print(f"     -> {len(rows)}개 완료")

    def _migrate_logs_pg_to_sqlite(self):
        """로그 DB: PostgreSQL -> SQLite"""
        print("\n[로그 DB] PostgreSQL -> SQLite")

        # SQLite 로그 디렉토리 생성
        os.makedirs(os.path.dirname(self.sqlite_log_db), exist_ok=True)

        pg_conn = psycopg2.connect(**get_log_connection_params())
        pg_conn.set_client_encoding('UTF8')
        pg_cursor = pg_conn.cursor()

        sqlite_conn = sqlite3.connect(self.sqlite_log_db)
        sqlite_cursor = sqlite_conn.cursor()

        # SQLite 로그 테이블 생성
        sqlite_cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL,
                timestamp REAL NOT NULL,
                level TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                user_id INTEGER,
                user_name TEXT,
                target_user_id INTEGER,
                target_user_name TEXT,
                command TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        try:
            print("   - logs 테이블...")
            pg_cursor.execute('''
                SELECT time, timestamp, level, category, message, user_id, user_name,
                       target_user_id, target_user_name, command, details
                FROM logs
            ''')
            logs = pg_cursor.fetchall()

            if logs:
                for log in logs:
                    sqlite_cursor.execute('''
                        INSERT INTO logs (time, timestamp, level, category, message, user_id, user_name,
                                         target_user_id, target_user_name, command, details)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', log)
                print(f"     -> {len(logs)}개 완료")

            sqlite_conn.commit()

        finally:
            pg_conn.close()
            sqlite_conn.close()

    def check_and_migrate(self):
        """
        현재 DB_TYPE 설정과 기존 데이터를 확인하고 필요시 마이그레이션 제안
        """
        current_is_sqlite = is_sqlite()

        # 현재 SQLite 모드인데 PostgreSQL에 데이터가 있는 경우
        if current_is_sqlite:
            if HAS_PSYCOPG2:
                try:
                    pg_conn = psycopg2.connect(**get_connection_params())
                    pg_cursor = pg_conn.cursor()
                    pg_cursor.execute("SELECT COUNT(*) FROM users")
                    pg_count = pg_cursor.fetchone()[0]
                    pg_conn.close()

                    if pg_count > 0:
                        sqlite_count = 0
                        if os.path.exists(self.sqlite_main_db):
                            sqlite_conn = sqlite3.connect(self.sqlite_main_db)
                            sqlite_cursor = sqlite_conn.cursor()
                            try:
                                sqlite_cursor.execute("SELECT COUNT(*) FROM users")
                                sqlite_count = sqlite_cursor.fetchone()[0]
                            except:
                                pass
                            sqlite_conn.close()

                        if sqlite_count == 0:
                            print("\n" + "=" * 60)
                            print("[알림] PostgreSQL에 데이터가 있지만 SQLite가 비어있습니다.")
                            print(f"       PostgreSQL: {pg_count}명의 사용자")
                            print(f"       SQLite: {sqlite_count}명의 사용자")
                            print("\n마이그레이션을 실행하시겠습니까?")
                            print("  python migrate_database.py pg_to_sqlite")
                            print("=" * 60)
                            return "pg_to_sqlite_suggested"
                except Exception as e:
                    pass  # PostgreSQL 연결 실패시 무시

        # 현재 PostgreSQL 모드인데 SQLite에 데이터가 있는 경우
        else:
            if os.path.exists(self.sqlite_main_db):
                sqlite_conn = sqlite3.connect(self.sqlite_main_db)
                sqlite_cursor = sqlite_conn.cursor()
                try:
                    sqlite_cursor.execute("SELECT COUNT(*) FROM users")
                    sqlite_count = sqlite_cursor.fetchone()[0]
                except:
                    sqlite_count = 0
                sqlite_conn.close()

                if sqlite_count > 0:
                    pg_count = 0
                    try:
                        pg_conn = psycopg2.connect(**get_connection_params())
                        pg_cursor = pg_conn.cursor()
                        pg_cursor.execute("SELECT COUNT(*) FROM users")
                        pg_count = pg_cursor.fetchone()[0]
                        pg_conn.close()
                    except:
                        pass

                    if pg_count == 0:
                        print("\n" + "=" * 60)
                        print("[알림] SQLite에 데이터가 있지만 PostgreSQL이 비어있습니다.")
                        print(f"       SQLite: {sqlite_count}명의 사용자")
                        print(f"       PostgreSQL: {pg_count}명의 사용자")
                        print("\n마이그레이션을 실행하시겠습니까?")
                        print("  python migrate_database.py sqlite_to_pg")
                        print("=" * 60)
                        return "sqlite_to_pg_suggested"

        return None


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='데이터베이스 마이그레이션 도구')
    parser.add_argument('direction', nargs='?', default='check',
                        choices=['sqlite_to_pg', 'pg_to_sqlite', 'check', 'auto'],
                        help='마이그레이션 방향 (sqlite_to_pg, pg_to_sqlite, check, auto)')

    args = parser.parse_args()

    migrator = DatabaseMigrator()

    print("=" * 60)
    print("PMDBot 데이터베이스 마이그레이션 도구")
    print("=" * 60)
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"현재 DB_TYPE: {'SQLite' if is_sqlite() else 'PostgreSQL'}")

    if args.direction == 'check':
        result = migrator.check_and_migrate()
        if result:
            print(f"\n권장 명령어: python migrate_database.py {result.replace('_suggested', '')}")
        else:
            print("\n마이그레이션이 필요하지 않습니다.")
        return 0

    elif args.direction == 'auto':
        result = migrator.check_and_migrate()
        if result == 'sqlite_to_pg_suggested':
            print("\n자동 마이그레이션 실행: SQLite -> PostgreSQL")
            success = migrator.sqlite_to_postgresql()
        elif result == 'pg_to_sqlite_suggested':
            print("\n자동 마이그레이션 실행: PostgreSQL -> SQLite")
            success = migrator.postgresql_to_sqlite()
        else:
            print("\n마이그레이션이 필요하지 않습니다.")
            return 0
        return 0 if success else 1

    elif args.direction == 'sqlite_to_pg':
        success = migrator.sqlite_to_postgresql()
        return 0 if success else 1

    elif args.direction == 'pg_to_sqlite':
        success = migrator.postgresql_to_sqlite()
        return 0 if success else 1


if __name__ == "__main__":
    exit(main())
