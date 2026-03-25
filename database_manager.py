# database_manager.py - 데이터베이스 관리 (PostgreSQL / SQLite)

import os
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import json
from db_config.db_adapter import create_adapter, DB_TYPE
from db_config.sql_compat import interval_ago, interval_set, interval_fixed, on_conflict_constraint

class DatabaseManager:
    """디스코드 ID, Minecraft UUID, 닉네임 히스토리를 관리하는 데이터베이스"""

    def __init__(self):
        """
        데이터베이스 관리자 초기화
        """
        self.adapter = create_adapter()
        self.init_database()
        print(f"[OK] 데이터베이스 초기화 완료: {self.adapter.get_db_label()}")

    def get_connection(self):
        """데이터베이스 연결 생성"""
        return self.adapter.get_connection()

    def _dict_cursor(self, conn):
        """dict 결과를 반환하는 커서 생성"""
        return self.adapter.get_dict_cursor(conn)

    def ensure_user_exists(self, discord_id: int, cursor=None) -> bool:
        """
        users 테이블에 사용자가 없으면 자동으로 추가 (외래 키 제약 조건 충족용)

        Args:
            discord_id: 디스코드 사용자 ID
            cursor: 기존 커서 (없으면 새로 생성)

        Returns:
            성공 여부
        """
        try:
            close_conn = False
            if cursor is None:
                conn = self.get_connection()
                cursor = conn.cursor()
                close_conn = True

            cursor.execute(self.adapter.adapt_sql('SELECT discord_id FROM users WHERE discord_id = %s'), (discord_id,))
            if not cursor.fetchone():
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO users (discord_id, first_seen, last_updated)
                    VALUES (%s, %s, %s)
                '''), (discord_id, datetime.now(), datetime.now()))
                print(f"[OK] users 테이블에 사용자 자동 추가: {discord_id}")

                if close_conn:
                    conn.commit()
                    conn.close()
                return True

            if close_conn:
                conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 사용자 자동 추가 실패: {e}")
            return False

    def init_database(self):
        """데이터베이스 테이블 생성"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 사용자 기본 정보 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id BIGINT PRIMARY KEY,
                minecraft_uuid TEXT,
                current_minecraft_name TEXT,
                current_nation TEXT,
                current_nation_uuid TEXT,
                current_town TEXT,
                current_town_uuid TEXT,
                first_seen TIMESTAMP DEFAULT NOW(),
                last_updated TIMESTAMP DEFAULT NOW()
            )
        '''))

        # users 테이블에 새 컬럼 추가 (기존 테이블 마이그레이션)
        self.adapter.add_column_safe(cursor, 'users', 'current_nation', 'TEXT')
        self.adapter.add_column_safe(cursor, 'users', 'current_nation_uuid', 'TEXT')
        self.adapter.add_column_safe(cursor, 'users', 'current_town', 'TEXT')
        self.adapter.add_column_safe(cursor, 'users', 'current_town_uuid', 'TEXT')
        self.adapter.add_column_safe(cursor, 'users', 'red_mafia_joined_at', 'TIMESTAMP')

        # Minecraft 닉네임 히스토리 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS minecraft_name_history (
                id SERIAL PRIMARY KEY,
                discord_id BIGINT NOT NULL,
                minecraft_uuid TEXT,
                minecraft_name TEXT NOT NULL,
                changed_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        '''))

        # 국가 히스토리 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS nation_history (
                id SERIAL PRIMARY KEY,
                discord_id BIGINT NOT NULL,
                nation_name TEXT,
                nation_uuid TEXT,
                town_name TEXT,
                town_uuid TEXT,
                nation_ranks TEXT,
                town_ranks TEXT,
                changed_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        '''))

        # 인덱스 생성 (조회 성능 향상)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_discord_id
            ON minecraft_name_history(discord_id)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_minecraft_uuid
            ON users(minecraft_uuid)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_minecraft_name
            ON minecraft_name_history(minecraft_name)
        '''))

        # 국가 히스토리 인덱스
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_nation_history_discord_id
            ON nation_history(discord_id)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_nation_history_nation
            ON nation_history(nation_name)
        '''))

        # 콜사인 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS callsigns (
                discord_id BIGINT PRIMARY KEY,
                callsign TEXT NOT NULL,
                set_at TIMESTAMP DEFAULT NOW(),
                admin_override INTEGER DEFAULT 0,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        '''))

        # callsigns 테이블에 새 컬럼 추가 (기존 테이블 마이그레이션)
        self.adapter.add_column_safe(cursor, 'callsigns', 'set_at', 'TIMESTAMP', "CURRENT_TIMESTAMP")
        self.adapter.add_column_safe(cursor, 'callsigns', 'admin_override', 'INTEGER', '0')

        # 콜사인 히스토리 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS callsign_history (
                id SERIAL PRIMARY KEY,
                discord_id BIGINT NOT NULL,
                callsign TEXT NOT NULL,
                set_at TIMESTAMP DEFAULT NOW(),
                admin_override INTEGER DEFAULT 0,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        '''))

        # 콜사인 인덱스
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_callsign_discord_id
            ON callsigns(discord_id)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_callsign_history_discord_id
            ON callsign_history(discord_id)
        '''))

        # 모든 마인크래프트 플레이어 정보 테이블 (Bulk API 전체 데이터)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS all_players (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                nation TEXT,
                nation_uuid TEXT,
                town TEXT,
                town_uuid TEXT,
                nation_ranks TEXT,
                town_ranks TEXT,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        '''))

        # all_players 테이블에 새 컬럼 추가 (기존 테이블 마이그레이션)
        self.adapter.add_column_safe(cursor, 'all_players', 'nation_uuid', 'TEXT')
        self.adapter.add_column_safe(cursor, 'all_players', 'town_uuid', 'TEXT')

        # 모든 플레이어 인덱스
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_players_name
            ON all_players(name)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_players_nation
            ON all_players(nation)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_players_town
            ON all_players(town)
        '''))

        # 콜사인 쿨타임 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS callsign_cooldowns (
                discord_id BIGINT PRIMARY KEY,
                cooldown_end TIMESTAMP NOT NULL,
                set_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        '''))

        # 콜사인 쿨타임 인덱스
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_cooldown_discord_id
            ON callsign_cooldowns(discord_id)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_cooldown_end
            ON callsign_cooldowns(cooldown_end)
        '''))

        # 모든 국가 정보 테이블 (nation/bulk API 전체 데이터)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS all_nations (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                king TEXT,
                capital TEXT,
                map_color TEXT,
                nation_board TEXT,
                registered BIGINT,
                nation_spawn_x DOUBLE PRECISION,
                nation_spawn_y DOUBLE PRECISION,
                nation_spawn_z DOUBLE PRECISION,
                is_public BOOLEAN DEFAULT FALSE,
                is_open BOOLEAN DEFAULT FALSE,
                is_neutral BOOLEAN DEFAULT FALSE,
                allies TEXT,
                enemies TEXT,
                towns TEXT,
                residents TEXT,
                sanctioned_towns TEXT,
                num_towns INTEGER DEFAULT 0,
                num_residents INTEGER DEFAULT 0,
                num_town_blocks INTEGER DEFAULT 0,
                nation_tax_percent DOUBLE PRECISION DEFAULT 0,
                nation_tax_max DOUBLE PRECISION DEFAULT 0,
                conquered_tax DOUBLE PRECISION DEFAULT 0,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        '''))

        # 국가 테이블 인덱스
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_nations_name
            ON all_nations(name)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_nations_king
            ON all_nations(king)
        '''))

        # 모든 마을 정보 테이블 (town/bulk API 전체 데이터)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS all_towns (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                nation TEXT,
                mayor TEXT,
                founder TEXT,
                town_board TEXT,
                tag TEXT,
                registered BIGINT,
                town_spawn_x DOUBLE PRECISION,
                town_spawn_y DOUBLE PRECISION,
                town_spawn_z DOUBLE PRECISION,
                home_block TEXT,
                is_public BOOLEAN DEFAULT FALSE,
                is_open BOOLEAN DEFAULT FALSE,
                is_neutral BOOLEAN DEFAULT FALSE,
                is_conquered BOOLEAN DEFAULT FALSE,
                is_ruined BOOLEAN DEFAULT FALSE,
                is_for_sale BOOLEAN DEFAULT FALSE,
                for_sale_price DOUBLE PRECISION DEFAULT 0,
                has_unlimited_claims BOOLEAN DEFAULT FALSE,
                residents TEXT,
                outlaws TEXT,
                trusted TEXT,
                num_residents INTEGER DEFAULT 0,
                num_town_blocks INTEGER DEFAULT 0,
                max_town_blocks INTEGER DEFAULT 0,
                bonus_blocks INTEGER DEFAULT 0,
                town_tax DOUBLE PRECISION DEFAULT 0,
                town_tax_percent DOUBLE PRECISION DEFAULT 0,
                town_tax_percent_cap DOUBLE PRECISION DEFAULT 0,
                max_tax_percent_amount DOUBLE PRECISION DEFAULT 0,
                is_tax_percent BOOLEAN DEFAULT FALSE,
                embassy_plot_tax DOUBLE PRECISION DEFAULT 0,
                commercial_plot_tax DOUBLE PRECISION DEFAULT 0,
                arena_plot_tax DOUBLE PRECISION DEFAULT 0,
                shop_plot_tax DOUBLE PRECISION DEFAULT 0,
                farm_plot_tax DOUBLE PRECISION DEFAULT 0,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        '''))

        # 마을 테이블 인덱스
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_towns_name
            ON all_towns(name)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_towns_nation
            ON all_towns(nation)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_all_towns_mayor
            ON all_towns(mayor)
        '''))

        # 부계정 연결 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS alt_accounts (
                id SERIAL PRIMARY KEY,
                main_discord_id BIGINT NOT NULL,
                alt_discord_id BIGINT NOT NULL UNIQUE,
                linked_at TIMESTAMP DEFAULT NOW(),
                linked_by BIGINT NOT NULL
            )
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_alt_accounts_main
            ON alt_accounts(main_discord_id)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_alt_accounts_alt
            ON alt_accounts(alt_discord_id)
        '''))

        # 부계정 설정 테이블 (서버별 자동 부여 역할)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS alt_config (
                guild_id BIGINT PRIMARY KEY,
                alt_role_id BIGINT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        '''))

        # 국가 통계 히스토리 테이블 (변경 발생 시 스냅샷 저장)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS nation_stats_history (
                id SERIAL PRIMARY KEY,
                nation_uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                king TEXT,
                capital TEXT,
                nation_board TEXT,
                num_residents INTEGER DEFAULT 0,
                num_towns INTEGER DEFAULT 0,
                num_town_blocks INTEGER DEFAULT 0,
                towns TEXT,
                allies TEXT,
                enemies TEXT,
                is_neutral BOOLEAN DEFAULT FALSE,
                recorded_at TIMESTAMP DEFAULT NOW()
            )
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_nation_stats_history_uuid
            ON nation_stats_history(nation_uuid)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_nation_stats_history_name
            ON nation_stats_history(name)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_nation_stats_history_recorded
            ON nation_stats_history(recorded_at)
        '''))

        # 마을 통계 히스토리 테이블 (변경 발생 시 스냅샷 저장)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS town_stats_history (
                id SERIAL PRIMARY KEY,
                town_uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                nation TEXT,
                mayor TEXT,
                founder TEXT,
                town_board TEXT,
                num_residents INTEGER DEFAULT 0,
                num_town_blocks INTEGER DEFAULT 0,
                max_town_blocks INTEGER DEFAULT 0,
                is_conquered BOOLEAN DEFAULT FALSE,
                is_neutral BOOLEAN DEFAULT FALSE,
                recorded_at TIMESTAMP DEFAULT NOW()
            )
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_town_stats_history_uuid
            ON town_stats_history(town_uuid)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_town_stats_history_name
            ON town_stats_history(name)
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_town_stats_history_recorded
            ON town_stats_history(recorded_at)
        '''))

        # user_changes 큐 테이블 (다른 봇에 변경사항 전달용)
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS user_changes (
                id SERIAL PRIMARY KEY,
                discord_id BIGINT NOT NULL,
                change_type TEXT NOT NULL,
                old_name TEXT,
                new_name TEXT,
                old_nation TEXT,
                new_nation TEXT,
                old_nation_uuid TEXT,
                new_nation_uuid TEXT,
                old_town TEXT,
                new_town TEXT,
                old_town_uuid TEXT,
                new_town_uuid TEXT,
                processed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_user_changes_processed
            ON user_changes(processed)
        '''))

        # 역할 신청 패널 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS role_panels (
                id SERIAL PRIMARY KEY,
                panel_id TEXT UNIQUE NOT NULL,
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                channel_id BIGINT,
                message_id BIGINT,
                review_channel_id BIGINT,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        '''))

        self.adapter.add_column_safe(cursor, 'role_panels', 'review_channel_id', 'BIGINT')

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_role_panels_guild
            ON role_panels(guild_id)
        '''))

        # 역할 신청 유저 추적 테이블
        cursor.execute(self.adapter.adapt_ddl('''
            CREATE TABLE IF NOT EXISTS role_panel_users (
                id SERIAL PRIMARY KEY,
                panel_id TEXT NOT NULL,
                discord_id BIGINT NOT NULL,
                status TEXT DEFAULT 'pending',
                applied_at TIMESTAMP DEFAULT NOW(),
                reviewed_by BIGINT,
                reviewed_at TIMESTAMP,
                UNIQUE(panel_id, discord_id)
            )
        '''))

        self.adapter.add_column_safe(cursor, 'role_panel_users', 'status', "TEXT DEFAULT 'pending'")
        self.adapter.add_column_safe(cursor, 'role_panel_users', 'reviewed_by', 'BIGINT')
        self.adapter.add_column_safe(cursor, 'role_panel_users', 'reviewed_at', 'TIMESTAMP')

        cursor.execute(self.adapter.adapt_ddl('''
            CREATE INDEX IF NOT EXISTS idx_role_panel_users_panel
            ON role_panel_users(panel_id)
        '''))

        conn.commit()
        conn.close()

    def add_or_update_user(self, discord_id: int, minecraft_uuid: str, minecraft_name: str) -> bool:
        """
        사용자 정보 추가 또는 업데이트

        Args:
            discord_id: 디스코드 사용자 ID
            minecraft_uuid: Minecraft UUID
            minecraft_name: Minecraft 닉네임

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # 기존 사용자 확인
            cursor.execute(self.adapter.adapt_sql('SELECT * FROM users WHERE discord_id = %s'), (discord_id,))
            existing_user = cursor.fetchone()

            if existing_user:
                # dict 또는 RealDictRow에서 값 가져오기
                old_name = existing_user['current_minecraft_name'] if isinstance(existing_user, dict) else existing_user[2]

                # 닉네임이 변경되었는지 확인
                if old_name != minecraft_name:
                    # 사용자 정보 업데이트
                    cursor.execute(self.adapter.adapt_sql('''
                        UPDATE users
                        SET minecraft_uuid = %s, current_minecraft_name = %s, last_updated = %s
                        WHERE discord_id = %s
                    '''), (minecraft_uuid, minecraft_name, datetime.now(), discord_id))

                    # 닉네임 히스토리에 추가
                    cursor.execute(self.adapter.adapt_sql('''
                        INSERT INTO minecraft_name_history (discord_id, minecraft_uuid, minecraft_name)
                        VALUES (%s, %s, %s)
                    '''), (discord_id, minecraft_uuid, minecraft_name))

                    print(f"[UPDATE] 닉네임 변경 감지: {discord_id} - {old_name} -> {minecraft_name}")
                else:
                    # 닉네임은 같지만 UUID나 last_updated만 업데이트
                    cursor.execute(self.adapter.adapt_sql('''
                        UPDATE users
                        SET minecraft_uuid = %s, last_updated = %s
                        WHERE discord_id = %s
                    '''), (minecraft_uuid, datetime.now(), discord_id))
            else:
                # 새 사용자 추가
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO users (discord_id, minecraft_uuid, current_minecraft_name)
                    VALUES (%s, %s, %s)
                '''), (discord_id, minecraft_uuid, minecraft_name))

                # 첫 닉네임 히스토리 추가
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO minecraft_name_history (discord_id, minecraft_uuid, minecraft_name)
                    VALUES (%s, %s, %s)
                '''), (discord_id, minecraft_uuid, minecraft_name))

                print(f"[ADD] 새 사용자 추가: {discord_id} - {minecraft_name}")

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 사용자 정보 저장 실패: {e}")
            return False

    def update_user_nation_info(self, discord_id: int, nation: str = None, nation_uuid: str = None,
                                 town: str = None, town_uuid: str = None) -> bool:
        """
        사용자의 현재 국가/마을 정보 업데이트

        Args:
            discord_id: 디스코드 사용자 ID
            nation: 국가 이름
            nation_uuid: 국가 UUID
            town: 마을 이름
            town_uuid: 마을 UUID

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE users
                SET current_nation = %s, current_nation_uuid = %s,
                    current_town = %s, current_town_uuid = %s,
                    last_updated = %s
                WHERE discord_id = %s
            '''), (nation, nation_uuid, town, town_uuid, datetime.now(), discord_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 사용자 국가 정보 업데이트 실패: {e}")
            return False

    def get_user_info(self, discord_id: int) -> Optional[Dict]:
        """
        사용자 기본 정보 조회
        부계정인 경우 본계정의 데이터를 반환

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            사용자 정보 딕셔너리 또는 None
        """
        try:
            # 부계정 여부 확인: 부계정이면 본계정 ID로 조회
            main_id = self.get_main_account(discord_id)
            lookup_id = main_id if main_id is not None else discord_id

            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM users WHERE discord_id = %s'), (lookup_id,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row) if not isinstance(row, dict) else row
            return None

        except Exception as e:
            print(f"[ERROR] 사용자 정보 조회 실패: {e}")
            return None

    def get_main_account(self, alt_discord_id: int) -> Optional[int]:
        """
        부계정의 본계정 Discord ID 조회

        Args:
            alt_discord_id: 부계정 Discord ID

        Returns:
            본계정 Discord ID 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(self.adapter.adapt_sql(
                'SELECT main_discord_id FROM alt_accounts WHERE alt_discord_id = %s'
            ), (alt_discord_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return row[0]
            return None
        except Exception as e:
            print(f"[ERROR] 본계정 조회 실패: {e}")
            return None

    def add_alt_account(self, main_discord_id: int, alt_discord_id: int, linked_by: int):
        """
        부계정 등록

        Args:
            main_discord_id: 본계정 Discord ID
            alt_discord_id: 부계정 Discord ID
            linked_by: 등록한 관리자 Discord ID

        Returns:
            (성공 여부, 메시지) 튜플
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 이미 다른 본계정에 연결된 부계정인지 확인
            cursor.execute(self.adapter.adapt_sql(
                'SELECT main_discord_id FROM alt_accounts WHERE alt_discord_id = %s'
            ), (alt_discord_id,))
            existing = cursor.fetchone()
            if existing:
                conn.close()
                return False, f"이미 다른 본계정(<@{existing[0]}>)에 연결된 부계정입니다."

            # 본계정으로 지정한 사용자가 이미 부계정인지 확인
            cursor.execute(self.adapter.adapt_sql(
                'SELECT main_discord_id FROM alt_accounts WHERE alt_discord_id = %s'
            ), (main_discord_id,))
            if cursor.fetchone():
                conn.close()
                return False, "본계정으로 지정한 사용자가 이미 부계정으로 등록되어 있습니다."

            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO alt_accounts (main_discord_id, alt_discord_id, linked_by)
                VALUES (%s, %s, %s)
            '''), (main_discord_id, alt_discord_id, linked_by))
            conn.commit()
            conn.close()
            return True, "부계정이 등록되었습니다."

        except Exception as e:
            print(f"[ERROR] 부계정 등록 실패: {e}")
            return False, f"DB 오류: {e}"

    def remove_alt_account(self, alt_discord_id: int):
        """
        부계정 연결 해제

        Args:
            alt_discord_id: 해제할 부계정 Discord ID

        Returns:
            (성공 여부, 메시지) 튜플
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(self.adapter.adapt_sql(
                'DELETE FROM alt_accounts WHERE alt_discord_id = %s'
            ), (alt_discord_id,))
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            if rows_affected == 0:
                return False, "등록된 부계정이 아닙니다."
            return True, "부계정 연결이 해제되었습니다."
        except Exception as e:
            print(f"[ERROR] 부계정 해제 실패: {e}")
            return False, f"DB 오류: {e}"

    def get_alt_accounts(self, main_discord_id: int) -> List[Dict]:
        """
        본계정에 연결된 부계정 목록 조회

        Args:
            main_discord_id: 본계정 Discord ID

        Returns:
            부계정 목록 (alt_discord_id, linked_at, linked_by)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)
            cursor.execute(self.adapter.adapt_sql('''
                SELECT alt_discord_id, linked_at, linked_by
                FROM alt_accounts
                WHERE main_discord_id = %s
                ORDER BY linked_at ASC
            '''), (main_discord_id,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[ERROR] 부계정 목록 조회 실패: {e}")
            return []

    def set_alt_role(self, guild_id: int, role_id: int) -> bool:
        """서버별 부계정 자동 부여 역할 설정"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO alt_config (guild_id, alt_role_id, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (guild_id) DO UPDATE SET
                    alt_role_id = EXCLUDED.alt_role_id,
                    updated_at = NOW()
            '''), (guild_id, role_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[ERROR] 부계정 역할 설정 실패: {e}")
            return False

    def get_alt_role(self, guild_id: int) -> Optional[int]:
        """서버별 부계정 자동 부여 역할 ID 조회 (없으면 None)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)
            cursor.execute(self.adapter.adapt_sql(
                'SELECT alt_role_id FROM alt_config WHERE guild_id = %s'
            ), (guild_id,))
            row = cursor.fetchone()
            conn.close()
            if row and row.get('alt_role_id'):
                return int(row['alt_role_id'])
            return None
        except Exception as e:
            print(f"[ERROR] 부계정 역할 조회 실패: {e}")
            return None

    def get_all_alt_accounts(self) -> List[Dict]:
        """모든 부계정 연결 목록 조회 (본계정 기준 오름차순)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)
            cursor.execute(self.adapter.adapt_sql('''
                SELECT main_discord_id, alt_discord_id, linked_at
                FROM alt_accounts
                ORDER BY main_discord_id, linked_at ASC
            '''))
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[ERROR] 전체 부계정 목록 조회 실패: {e}")
            return []

    def get_name_history(self, discord_id: int, limit: int = 10) -> List[Dict]:
        """
        Minecraft 닉네임 히스토리 조회

        Args:
            discord_id: 디스코드 사용자 ID
            limit: 조회할 최대 개수

        Returns:
            닉네임 히스토리 리스트 (최신순)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT * FROM minecraft_name_history
                WHERE discord_id = {ph}
                ORDER BY changed_at DESC
                LIMIT %s
            '''), (discord_id, limit))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) if not isinstance(row, dict) else row for row in rows]

        except Exception as e:
            print(f"[ERROR] 닉네임 히스토리 조회 실패: {e}")
            return []

    def search_by_minecraft_name(self, minecraft_name: str) -> List[Dict]:
        """
        Minecraft 닉네임으로 사용자 검색

        Args:
            minecraft_name: 검색할 Minecraft 닉네임

        Returns:
            매칭되는 사용자 리스트
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # 현재 닉네임 또는 과거 닉네임에서 검색 (ILIKE로 대소문자 무시)
            cursor.execute(self.adapter.adapt_sql('''
                SELECT DISTINCT u.*
                FROM users u
                LEFT JOIN minecraft_name_history h ON u.discord_id = h.discord_id
                WHERE u.current_minecraft_name ILIKE %s OR h.minecraft_name ILIKE %s
            '''), (f'%{minecraft_name}%', f'%{minecraft_name}%'))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) if not isinstance(row, dict) else row for row in rows]

        except Exception as e:
            print(f"[ERROR] 닉네임 검색 실패: {e}")
            return []

    def search_by_uuid(self, minecraft_uuid: str) -> Optional[Dict]:
        """
        Minecraft UUID로 사용자 검색

        Args:
            minecraft_uuid: 검색할 Minecraft UUID

        Returns:
            사용자 정보 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM users WHERE minecraft_uuid = %s'), (minecraft_uuid,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row) if not isinstance(row, dict) else row
            return None

        except Exception as e:
            print(f"[ERROR] UUID 검색 실패: {e}")
            return None

    def get_all_users(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """
        모든 사용자 조회 (페이지네이션)

        Args:
            limit: 조회할 최대 개수 (None이면 전체 조회)
            offset: 건너뛸 개수

        Returns:
            사용자 리스트
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            if limit is None:
                # limit이 None이면 전체 조회
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM users
                    ORDER BY last_updated DESC
                '''))
            else:
                # limit이 있으면 페이지네이션
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM users
                    ORDER BY last_updated DESC
                    LIMIT %s OFFSET %s
                '''), (limit, offset))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) if not isinstance(row, dict) else row for row in rows]

        except Exception as e:
            print(f"[ERROR] 전체 사용자 조회 실패: {e}")
            return []

    def get_total_users(self) -> int:
        """전체 사용자 수 조회"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) as count FROM users'))
            result = cursor.fetchone()

            conn.close()

            if isinstance(result, dict):
                return result['count']
            return result[0] if result else 0

        except Exception as e:
            print(f"[ERROR] 사용자 수 조회 실패: {e}")
            return 0

    def get_statistics(self) -> Dict:
        """데이터베이스 통계 정보 조회"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # 전체 사용자 수
            cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) as count FROM users'))
            total_users = cursor.fetchone()['count']

            # 전체 닉네임 변경 횟수
            cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) as count FROM minecraft_name_history'))
            total_name_changes = cursor.fetchone()['count']

            # 최근 24시간 내 업데이트된 사용자 수
            cursor.execute(self.adapter.adapt_sql(f'''
                SELECT COUNT(*) as count FROM users
                WHERE last_updated >= {interval_fixed('1 day')}
            '''))
            recent_updates = cursor.fetchone()['count']

            # 닉네임을 가장 많이 변경한 사용자 Top 5
            cursor.execute(self.adapter.adapt_sql('''
                SELECT discord_id, COUNT(*) as change_count
                FROM minecraft_name_history
                GROUP BY discord_id
                ORDER BY change_count DESC
                LIMIT 5
            '''))
            top_changers = [dict(row) for row in cursor.fetchall()]

            conn.close()

            return {
                'total_users': total_users,
                'total_name_changes': total_name_changes,
                'recent_updates': recent_updates,
                'top_changers': top_changers
            }

        except Exception as e:
            print(f"[ERROR] 통계 조회 실패: {e}")
            return {}

    def delete_user(self, discord_id: int) -> bool:
        """
        사용자 정보 삭제 (히스토리 포함)

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()


            # 히스토리 먼저 삭제
            cursor.execute(self.adapter.adapt_sql('DELETE FROM minecraft_name_history WHERE discord_id = %s'), (discord_id,))

            # 사용자 정보 삭제
            cursor.execute(self.adapter.adapt_sql('DELETE FROM users WHERE discord_id = %s'), (discord_id,))

            conn.commit()
            conn.close()

            print(f"[DELETE] 사용자 정보 삭제: {discord_id}")
            return True

        except Exception as e:
            print(f"[ERROR] 사용자 삭제 실패: {e}")
            return False

    def cleanup_old_history(self, days: int = 365) -> int:
        """
        오래된 닉네임 히스토리 정리

        Args:
            days: 보관할 일수

        Returns:
            삭제된 레코드 수
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql(f'''
                DELETE FROM minecraft_name_history
                WHERE {interval_ago('changed_at', '<')}
            '''), (days,))

            deleted_count = cursor.rowcount

            conn.commit()
            conn.close()

            print(f"[CLEANUP] {days}일 이전 히스토리 {deleted_count}개 삭제")
            return deleted_count

        except Exception as e:
            print(f"[ERROR] 히스토리 정리 실패: {e}")
            return 0

    def add_nation_history(self, discord_id: int, nation_name: str = None, nation_uuid: str = None,
                           town_name: str = None, town_uuid: str = None,
                           nation_ranks: str = None, town_ranks: str = None) -> bool:
        """
        국가/마을 히스토리 추가

        Args:
            discord_id: 디스코드 사용자 ID
            nation_name: 국가 이름
            nation_uuid: 국가 UUID
            town_name: 마을 이름
            town_uuid: 마을 UUID
            nation_ranks: 국가 계급/직위
            town_ranks: 마을 계급/직위

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # users 테이블에 사용자가 없으면 먼저 추가 (외래 키 제약 조건 충족)
            self.ensure_user_exists(discord_id, cursor)

            # 가장 최근 국가 히스토리 조회
            cursor.execute(self.adapter.adapt_sql('''
                SELECT nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks
                FROM nation_history
                WHERE discord_id = {ph}
                ORDER BY changed_at DESC
                LIMIT 1
            '''), (discord_id,))

            last_record = cursor.fetchone()

            # 변경사항이 있는지 확인
            if last_record:
                lr = dict(last_record) if not isinstance(last_record, dict) else last_record
                if (lr['nation_name'] == nation_name and
                    lr['nation_uuid'] == nation_uuid and
                    lr['town_name'] == town_name and
                    lr['town_uuid'] == town_uuid and
                    lr['nation_ranks'] == nation_ranks and
                    lr['town_ranks'] == town_ranks):
                    # 변경사항 없음
                    conn.close()
                    return True

            # 새 히스토리 추가
            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO nation_history (discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            '''), (discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks))

            conn.commit()
            conn.close()

            print(f"[ADD] 국가 히스토리 추가: {discord_id} - {nation_name}/{town_name} (국가 계급: {nation_ranks}, 마을 계급: {town_ranks})")
            return True

        except Exception as e:
            print(f"[ERROR] 국가 히스토리 저장 실패: {e}")
            return False

    def backfill_history_uuid(self, discord_id: int, nation_uuid: str = None, town_uuid: str = None) -> bool:
        """
        nation_history에서 UUID가 없는 최근 레코드에 UUID 보충 저장
        캐시에서 조회한 UUID를 DB에 저장하여 중복 조회 방지

        Args:
            discord_id: 디스코드 사용자 ID
            nation_uuid: 보충할 국가 UUID
            town_uuid: 보충할 마을 UUID

        Returns:
            성공 여부
        """
        try:
            if not nation_uuid and not town_uuid:
                return True

            conn = self.get_connection()
            cursor = conn.cursor()

            updates = []
            params = []

            if nation_uuid:
                updates.append("nation_uuid = %s")
                params.append(nation_uuid)
            if town_uuid:
                updates.append("town_uuid = %s")
                params.append(town_uuid)

            params.append(discord_id)

            # 조건: UUID가 NULL인 최근 레코드만 업데이트
            where_conditions = []
            if nation_uuid:
                where_conditions.append("nation_uuid IS NULL")
            if town_uuid:
                where_conditions.append("town_uuid IS NULL")

            cursor.execute(self.adapter.adapt_sql(f'''
                UPDATE nation_history
                SET {", ".join(updates)}
                WHERE discord_id = %s
                AND ({" OR ".join(where_conditions)})
                AND changed_at = (
                    SELECT MAX(changed_at) FROM nation_history WHERE discord_id = %s
                )
            '''), (*params, discord_id))

            updated = cursor.rowcount
            conn.commit()
            conn.close()

            if updated > 0:
                parts = []
                if nation_uuid:
                    parts.append(f"nation_uuid={nation_uuid[:8]}")
                if town_uuid:
                    parts.append(f"town_uuid={town_uuid[:8]}")
                print(f"[BACKFILL] nation_history UUID 보충: discord_id={discord_id}, {', '.join(parts)}")
            return True

        except Exception as e:
            print(f"[ERROR] nation_history UUID 보충 실패: {e}")
            return False

    def get_nation_history(self, discord_id: int, limit: int = 10) -> List[Dict]:
        """
        국가/마을 히스토리 조회

        Args:
            discord_id: 디스코드 사용자 ID
            limit: 조회할 최대 개수

        Returns:
            국가 히스토리 리스트 (최신순)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT * FROM nation_history
                WHERE discord_id = {ph}
                ORDER BY changed_at DESC
                LIMIT %s
            '''), (discord_id, limit))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) if not isinstance(row, dict) else row for row in rows]

        except Exception as e:
            print(f"[ERROR] 국가 히스토리 조회 실패: {e}")
            return []

    def get_earliest_nation_join(self, discord_id: int, nation_name: str) -> Optional[datetime]:
        """
        nation_history에서 특정 국가에 최초로 소속된 날짜(가장 오래된 기록) 반환.
        뉴비 판정 시 가장 이른 가입일을 기준으로 삼기 위해 사용.

        Args:
            discord_id: 디스코드 사용자 ID
            nation_name: 국가 이름 (대소문자 무시)

        Returns:
            최초 소속일 datetime 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT MIN(changed_at) as earliest
                FROM nation_history
                WHERE discord_id = %s
                  AND nation_name ILIKE %s
            '''), (discord_id, nation_name))

            row = cursor.fetchone()
            conn.close()

            if row and row.get('earliest'):
                val = row['earliest']
                if isinstance(val, datetime):
                    return val
                # SQLite는 문자열로 반환될 수 있음
                from datetime import datetime as _dt
                try:
                    return _dt.fromisoformat(str(val))
                except Exception:
                    return None
            return None

        except Exception as e:
            print(f"[ERROR] 최초 국가 가입일 조회 실패: {e}")
            return None

    def get_current_nation(self, discord_id: int) -> Optional[Dict]:
        """
        사용자의 현재 국가 정보 조회 (가장 최근 기록)

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            국가 정보 딕셔너리 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks, changed_at
                FROM nation_history
                WHERE discord_id = {ph}
                ORDER BY changed_at DESC
                LIMIT 1
            '''), (discord_id,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row) if not isinstance(row, dict) else row
            return None

        except Exception as e:
            print(f"[ERROR] 현재 국가 조회 실패: {e}")
            return None

    def get_nation_membership_days(self, discord_id: int, nation_name: str) -> int:
        """
        사용자가 특정 국가에 소속된 총 일수 계산 (과거 기록 포함)

        Args:
            discord_id: 디스코드 사용자 ID
            nation_name: 국가 이름

        Returns:
            해당 국가 소속 총 일수 (기록이 없으면 0)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # 해당 사용자의 모든 국가 히스토리 조회 (시간순)
            cursor.execute(self.adapter.adapt_sql('''
                SELECT nation_name, changed_at
                FROM nation_history
                WHERE discord_id = %s
                ORDER BY changed_at ASC
            '''), (discord_id,))

            records = cursor.fetchall()
            conn.close()

            if not records:
                return 0

            total_days = 0
            last_join_time = None

            for i, record in enumerate(records):
                current_nation = record['nation_name']
                current_time = record['changed_at']

                # 대소문자 무시하고 비교 (Red_Mafia, red_mafia 등)
                is_target_nation = (
                    current_nation and
                    nation_name and
                    current_nation.lower() == nation_name.lower()
                )

                if is_target_nation:
                    # 해당 국가에 가입한 시점
                    if last_join_time is None:
                        last_join_time = current_time
                else:
                    # 다른 국가로 변경됨 - 이전 소속 기간 계산
                    if last_join_time is not None:
                        days = (current_time - last_join_time).days
                        total_days += max(days, 0)
                        last_join_time = None

            # 현재도 해당 국가에 소속 중이면 현재까지의 기간 추가
            if last_join_time is not None:
                from datetime import datetime
                days = (datetime.now() - last_join_time).days
                total_days += max(days, 0)

            return total_days

        except Exception as e:
            print(f"[ERROR] 국가 소속 기간 조회 실패: {e}")
            return 0

    def was_member_of_nation(self, discord_id: int, nation_name: str, min_days: int = 7) -> bool:
        """
        사용자가 특정 국가에 일정 기간 이상 소속된 적이 있는지 확인

        Args:
            discord_id: 디스코드 사용자 ID
            nation_name: 국가 이름
            min_days: 최소 소속 일수 (기본 7일)

        Returns:
            min_days 이상 소속된 적이 있으면 True
        """
        total_days = self.get_nation_membership_days(discord_id, nation_name)
        return total_days >= min_days

    def export_to_json(self, output_file: str = "database_export.json") -> bool:
        """
        데이터베이스를 JSON 파일로 내보내기

        Args:
            output_file: 출력 파일 경로

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # 모든 사용자 조회
            cursor.execute(self.adapter.adapt_sql('SELECT * FROM users'))
            users = [dict(row) for row in cursor.fetchall()]

            # 모든 히스토리 조회
            cursor.execute(self.adapter.adapt_sql('SELECT * FROM minecraft_name_history ORDER BY discord_id, changed_at'))
            history = [dict(row) for row in cursor.fetchall()]

            conn.close()

            # JSON 파일로 저장
            export_data = {
                'export_time': datetime.now().isoformat(),
                'users': users,
                'history': history
            }

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)

            print(f"[EXPORT] 데이터베이스 내보내기 완료: {output_file}")
            return True

        except Exception as e:
            print(f"[ERROR] 데이터베이스 내보내기 실패: {e}")
            return False

    def set_callsign(self, discord_id: int, callsign: str, admin_override: bool = False, guild_id: int = None) -> bool:
        """
        사용자 콜사인 설정 (DB에 저장)

        Args:
            discord_id: 디스코드 사용자 ID
            callsign: 콜사인
            admin_override: 관리자가 강제로 설정했는지 여부
            guild_id: 길드(서버) ID (None이면 config에서 자동으로 가져옴)

        Returns:
            성공 여부
        """
        try:
            # guild_id가 없으면 config에서 가져오기
            if guild_id is None:
                try:
                    from config import config
                    guild_id = config.GUILD_ID
                except Exception:
                    guild_id = None

            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # users 테이블에 사용자가 없으면 먼저 추가 (외래 키 제약 조건 충족)
            self.ensure_user_exists(discord_id, cursor)

            # 기존 콜사인 확인 (guild_id 포함하여 조회)
            if guild_id is not None:
                cursor.execute(self.adapter.adapt_sql('SELECT callsign, admin_override FROM callsigns WHERE discord_id = %s AND guild_id = %s'), (discord_id, guild_id))
            else:
                cursor.execute(self.adapter.adapt_sql('SELECT callsign, admin_override FROM callsigns WHERE discord_id = %s AND guild_id IS NULL'), (discord_id,))
            existing = cursor.fetchone()

            # 이미 같은 콜사인이 저장되어 있으면 건너뛰기
            if existing:
                ex = dict(existing) if not isinstance(existing, dict) else existing
                if ex['callsign'] == callsign and ex['admin_override'] == (1 if admin_override else 0):
                    conn.close()
                    return True  # 중복 저장 방지

            now = datetime.now()
            admin_val = 1 if admin_override else 0

            # UPSERT: INSERT 시 충돌하면 UPDATE로 처리
            conflict_clause = on_conflict_constraint(
                'callsigns_guild_discord_unique',
                ['guild_id', 'discord_id'],
                ['callsign', 'set_at', 'admin_override']
            )
            cursor.execute(self.adapter.adapt_sql(f'''
                INSERT INTO callsigns (discord_id, callsign, set_at, admin_override, guild_id)
                VALUES (%s, %s, %s, %s, %s)
                {conflict_clause}
            '''), (discord_id, callsign, now, admin_val, guild_id))

            # 히스토리에 추가
            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO callsign_history (discord_id, callsign, set_at, admin_override)
                VALUES (%s, %s, %s, %s)
            '''), (discord_id, callsign, now, admin_val))

            action = "업데이트" if existing else "저장"
            print(f"[OK] DB에 콜사인 {action} 완료: {discord_id} -> {callsign}")

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            print(f"[ERROR] DB 콜사인 저장 실패: {e}")
            return False

    def get_callsign(self, discord_id: int) -> Optional[str]:
        """
        사용자 콜사인 조회

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            콜사인 (없으면 None)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT callsign FROM callsigns WHERE discord_id = %s'), (discord_id,))
            result = cursor.fetchone()
            conn.close()

            if result:
                return result['callsign'] if isinstance(result, dict) else result[0]
            return None

        except Exception as e:
            print(f"[ERROR] DB 콜사인 조회 실패: {e}")
            return None

    def get_callsign_history(self, discord_id: int) -> List[Dict]:
        """
        사용자 콜사인 변경 히스토리 조회

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            콜사인 히스토리 목록
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT callsign, set_at, admin_override
                FROM callsign_history
                WHERE discord_id = {ph}
                ORDER BY set_at DESC
            '''), (discord_id,))

            results = cursor.fetchall()
            conn.close()

            history = []
            for row in results:
                r = dict(row) if not isinstance(row, dict) else row
                history.append({
                    'callsign': r['callsign'],
                    'set_at': r['set_at'],
                    'admin_override': bool(r['admin_override'])
                })

            return history

        except Exception as e:
            print(f"[ERROR] 콜사인 히스토리 조회 실패: {e}")
            return []

    def delete_callsign(self, discord_id: int) -> bool:
        """
        사용자 콜사인 삭제

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()


            cursor.execute(self.adapter.adapt_sql('DELETE FROM callsigns WHERE discord_id = %s'), (discord_id,))

            conn.commit()
            conn.close()

            print(f"[OK] DB에서 콜사인 삭제 완료: {discord_id}")
            return True

        except Exception as e:
            print(f"[ERROR] DB 콜사인 삭제 실패: {e}")
            return False

    def set_cooldown(self, discord_id: int, cooldown_end: datetime) -> bool:
        """
        사용자 콜사인 쿨타임 설정

        Args:
            discord_id: 디스코드 사용자 ID
            cooldown_end: 쿨타임 종료 시간

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            # FK 제약 충족: users 테이블에 사용자 존재 확인
            self.ensure_user_exists(discord_id, cursor)

            # 기존 쿨타임 확인
            cursor.execute(self.adapter.adapt_sql('SELECT discord_id FROM callsign_cooldowns WHERE discord_id = %s'), (discord_id,))
            existing = cursor.fetchone()

            if existing:
                # 기존 쿨타임 업데이트
                cursor.execute(self.adapter.adapt_sql('''
                    UPDATE callsign_cooldowns
                    SET cooldown_end = %s, set_at = %s
                    WHERE discord_id = %s
                '''), (cooldown_end, datetime.now(), discord_id))
            else:
                # 새로운 쿨타임 추가
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO callsign_cooldowns (discord_id, cooldown_end, set_at)
                    VALUES (%s, %s, %s)
                '''), (discord_id, cooldown_end, datetime.now()))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] DB 쿨타임 저장 실패: {e}")
            return False

    def get_cooldown(self, discord_id: int) -> Optional[datetime]:
        """
        사용자 콜사인 쿨타임 조회

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            쿨타임 종료 시간 (없으면 None)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT cooldown_end FROM callsign_cooldowns WHERE discord_id = %s'), (discord_id,))
            result = cursor.fetchone()
            conn.close()

            if result:
                cooldown_val = result['cooldown_end'] if isinstance(result, dict) else result[0]
                # datetime 객체이면 그대로 반환
                if isinstance(cooldown_val, datetime):
                    return cooldown_val
                elif isinstance(cooldown_val, str):
                    return datetime.fromisoformat(cooldown_val)

            return None

        except Exception as e:
            print(f"[ERROR] DB 쿨타임 조회 실패: {e}")
            return None

    def delete_cooldown(self, discord_id: int) -> bool:
        """
        사용자 콜사인 쿨타임 삭제

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()


            cursor.execute(self.adapter.adapt_sql('DELETE FROM callsign_cooldowns WHERE discord_id = %s'), (discord_id,))

            conn.commit()
            conn.close()

            print(f"[OK] DB에서 쿨타임 삭제 완료: {discord_id}")
            return True

        except Exception as e:
            print(f"[ERROR] DB 쿨타임 삭제 실패: {e}")
            return False

    def delete_all_cooldowns(self) -> int:
        """
        모든 사용자의 콜사인 쿨타임 삭제

        Returns:
            삭제된 레코드 수
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('DELETE FROM callsign_cooldowns'))
            deleted_count = cursor.rowcount

            conn.commit()
            conn.close()

            print(f"[OK] DB에서 모든 쿨타임 삭제 완료: {deleted_count}개")
            return deleted_count

        except Exception as e:
            print(f"[ERROR] DB 모든 쿨타임 삭제 실패: {e}")
            return 0

    # ===== 변경사항 큐 (다른 봇 전달용) =====

    def insert_user_change(self, discord_id: int, change_type: str,
                           old_name=None, new_name=None,
                           old_nation=None, new_nation=None,
                           old_nation_uuid=None, new_nation_uuid=None,
                           old_town=None, new_town=None,
                           old_town_uuid=None, new_town_uuid=None):
        """변경사항을 user_changes 큐 테이블에 삽입"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)
            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO user_changes
                    (discord_id, change_type, old_name, new_name,
                     old_nation, new_nation, old_nation_uuid, new_nation_uuid,
                     old_town, new_town, old_town_uuid, new_town_uuid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''), (discord_id, change_type, old_name, new_name,
                   old_nation, new_nation, old_nation_uuid, new_nation_uuid,
                   old_town, new_town, old_town_uuid, new_town_uuid))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ERROR] user_changes 삽입 실패: {e}")

    # ===== 모든 플레이어 정보 관리 (all_players 테이블) =====

    def upsert_all_players(self, players: List[Dict]) -> int:
        """
        Bulk API에서 가져온 모든 플레이어 정보를 DB에 저장/업데이트

        Args:
            players: 플레이어 정보 리스트

        Returns:
            저장/업데이트된 레코드 수
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()


            saved_count = 0
            error_count = 0

            for player in players:
              try:
                uuid = player.get('uuid')
                name = player.get('name')
                # 빈 문자열을 None으로 정규화 (API는 빈 문자열 반환, DB는 None 저장)
                nation = player.get('nation') or None
                town = player.get('town') or None
                nation_uuid = player.get('_nation_uuid') or None
                town_uuid = player.get('_town_uuid') or None
                nation_ranks = player.get('nationRanks') or None
                town_ranks = player.get('townRanks') or None

                if not uuid or not name:
                    continue

                # UPSERT (INSERT ... ON CONFLICT DO UPDATE)
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO all_players (uuid, name, nation, nation_uuid, town, town_uuid, nation_ranks, town_ranks, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        name = EXCLUDED.name,
                        nation = EXCLUDED.nation,
                        nation_uuid = EXCLUDED.nation_uuid,
                        town = EXCLUDED.town,
                        town_uuid = EXCLUDED.town_uuid,
                        nation_ranks = EXCLUDED.nation_ranks,
                        town_ranks = EXCLUDED.town_ranks,
                        last_updated = EXCLUDED.last_updated
                '''), (uuid, name, nation, nation_uuid, town, town_uuid, nation_ranks, town_ranks, datetime.now()))

                saved_count += 1
              except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"[ERROR] 플레이어 upsert 실패 ({player.get('name')}): {e}")

            conn.commit()
            conn.close()

            if error_count > 0:
                print(f"[WARN] 플레이어 upsert 중 {error_count}건 오류 (성공: {saved_count})")

            return saved_count

        except Exception as e:
            print(f"[ERROR] 모든 플레이어 정보 저장 실패: {e}")
            return 0

    def get_player_by_uuid(self, uuid: str) -> Optional[Dict]:
        """
        UUID로 플레이어 정보 조회 (all_players 테이블)

        Args:
            uuid: Minecraft UUID

        Returns:
            플레이어 정보 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM all_players WHERE uuid = %s'), (uuid,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row) if not isinstance(row, dict) else row
            return None

        except Exception as e:
            print(f"[ERROR] 플레이어 UUID 조회 실패: {e}")
            return None

    def get_player_by_name(self, name: str) -> Optional[Dict]:
        """
        이름으로 플레이어 정보 조회 (all_players 테이블)

        Args:
            name: Minecraft 닉네임

        Returns:
            플레이어 정보 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM all_players WHERE name ILIKE %s'), (name,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row) if not isinstance(row, dict) else row
            return None

        except Exception as e:
            print(f"[ERROR] 플레이어 이름 조회 실패: {e}")
            return None

    def get_all_players(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """
        모든 플레이어 조회 (all_players 테이블)

        Args:
            limit: 조회할 최대 개수 (None이면 전체 조회)
            offset: 건너뛸 개수

        Returns:
            플레이어 리스트
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            if limit is None:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM all_players
                    ORDER BY last_updated DESC
                '''))
            else:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM all_players
                    ORDER BY last_updated DESC
                    LIMIT %s OFFSET %s
                '''), (limit, offset))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) if not isinstance(row, dict) else row for row in rows]

        except Exception as e:
            print(f"[ERROR] 모든 플레이어 조회 실패: {e}")
            return []

    def get_players_by_nation(self, nation_name: str) -> List[Dict]:
        """
        국가별 플레이어 조회

        Args:
            nation_name: 국가 이름

        Returns:
            플레이어 리스트
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT * FROM all_players
                WHERE nation {like_op} {ph}
                ORDER BY name
            '''), (nation_name,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) if not isinstance(row, dict) else row for row in rows]

        except Exception as e:
            print(f"[ERROR] 국가별 플레이어 조회 실패: {e}")
            return []

    def get_players_by_town(self, town_name: str) -> List[Dict]:
        """
        마을별 플레이어 조회

        Args:
            town_name: 마을 이름

        Returns:
            플레이어 리스트
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT * FROM all_players
                WHERE town {like_op} {ph}
                ORDER BY name
            '''), (town_name,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) if not isinstance(row, dict) else row for row in rows]

        except Exception as e:
            print(f"[ERROR] 마을별 플레이어 조회 실패: {e}")
            return []

    def get_total_players(self) -> int:
        """전체 플레이어 수 조회 (all_players 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) as count FROM all_players'))
            result = cursor.fetchone()

            conn.close()

            if isinstance(result, dict):
                return result['count']
            return result[0] if result else 0

        except Exception as e:
            print(f"[ERROR] 플레이어 수 조회 실패: {e}")
            return 0


    # ===== 모든 국가 정보 관리 (all_nations 테이블) =====

    def upsert_all_nations(self, nations: List[Dict]) -> int:
        """
        Nation Bulk API에서 가져온 모든 국가 정보를 DB에 저장/업데이트.
        주요 필드 변경 시 nation_stats_history에 스냅샷 기록.

        Args:
            nations: 국가 정보 리스트

        Returns:
            저장/업데이트된 레코드 수
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            dict_cursor = self._dict_cursor(conn)

            saved_count = 0
            history_count = 0
            error_count = 0
            deleted_count = 0

            # API 응답에 있는 국가 UUID 목록
            api_uuids = set()
            for n in nations:
                if n.get('uuid'):
                    api_uuids.add(n['uuid'])

            # DB에 있지만 API에 없는 국가 삭제 (멸망/삭제된 국가)
            if api_uuids:
                dict_cursor.execute(self.adapter.adapt_sql(
                    'SELECT uuid, name FROM all_nations'
                ))
                db_nations = dict_cursor.fetchall()
                for db_nation in db_nations:
                    db_row = dict(db_nation)
                    if db_row['uuid'] not in api_uuids:
                        cursor.execute(self.adapter.adapt_sql(
                            'DELETE FROM all_nations WHERE uuid = %s'
                        ), (db_row['uuid'],))
                        deleted_count += 1
                        print(f"[DELETE] 국가 삭제됨 (API에서 사라짐): {db_row.get('name')} ({db_row['uuid'][:8]}...)")

            for nation in nations:
              try:
                uuid = nation.get('uuid')
                name = nation.get('name')

                if not uuid or not name:
                    continue

                # allies, enemies, towns, residents, sanctioned_towns를 JSON 문자열로 변환
                allies = json.dumps(nation.get('allies', []), ensure_ascii=False) if nation.get('allies') else None
                enemies = json.dumps(nation.get('enemies', []), ensure_ascii=False) if nation.get('enemies') else None
                towns = json.dumps(nation.get('towns', []), ensure_ascii=False) if nation.get('towns') else None
                residents = json.dumps(nation.get('residents', []), ensure_ascii=False) if nation.get('residents') else None
                sanctioned_towns = json.dumps(nation.get('sanctionedTowns', []), ensure_ascii=False) if nation.get('sanctionedTowns') else None

                king = nation.get('king')
                capital = nation.get('capital')
                nation_board = nation.get('nationBoard')
                num_residents = nation.get('numResidents', 0)
                num_towns = nation.get('numTowns', 0)
                num_town_blocks = nation.get('numTownBlocks', 0)
                is_neutral = nation.get('isNeutral', False)

                # 변경 감지: 기존 DB 데이터와 비교
                dict_cursor.execute(self.adapter.adapt_sql(
                    'SELECT king, capital, nation_board, num_residents, num_towns, towns, allies, enemies FROM all_nations WHERE uuid = %s'
                ), (uuid,))
                _row = dict_cursor.fetchone()
                existing = dict(_row) if _row else None

                should_record = not existing or (
                    existing.get('king') != king or
                    existing.get('capital') != capital or
                    existing.get('nation_board') != nation_board or
                    existing.get('num_residents') != num_residents or
                    existing.get('num_towns') != num_towns or
                    existing.get('towns') != towns or
                    existing.get('allies') != allies or
                    existing.get('enemies') != enemies
                )

                # UPSERT into all_nations
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO all_nations (
                        uuid, name, king, capital, map_color, nation_board, registered,
                        nation_spawn_x, nation_spawn_y, nation_spawn_z,
                        is_public, is_open, is_neutral,
                        allies, enemies, towns, residents, sanctioned_towns,
                        num_towns, num_residents, num_town_blocks,
                        nation_tax_percent, nation_tax_max, conquered_tax, last_updated
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        name = EXCLUDED.name,
                        king = EXCLUDED.king,
                        capital = EXCLUDED.capital,
                        map_color = EXCLUDED.map_color,
                        nation_board = EXCLUDED.nation_board,
                        registered = EXCLUDED.registered,
                        nation_spawn_x = EXCLUDED.nation_spawn_x,
                        nation_spawn_y = EXCLUDED.nation_spawn_y,
                        nation_spawn_z = EXCLUDED.nation_spawn_z,
                        is_public = EXCLUDED.is_public,
                        is_open = EXCLUDED.is_open,
                        is_neutral = EXCLUDED.is_neutral,
                        allies = EXCLUDED.allies,
                        enemies = EXCLUDED.enemies,
                        towns = EXCLUDED.towns,
                        residents = EXCLUDED.residents,
                        sanctioned_towns = EXCLUDED.sanctioned_towns,
                        num_towns = EXCLUDED.num_towns,
                        num_residents = EXCLUDED.num_residents,
                        num_town_blocks = EXCLUDED.num_town_blocks,
                        nation_tax_percent = EXCLUDED.nation_tax_percent,
                        nation_tax_max = EXCLUDED.nation_tax_max,
                        conquered_tax = EXCLUDED.conquered_tax,
                        last_updated = EXCLUDED.last_updated
                '''), (
                    uuid, name, king, capital,
                    nation.get('mapColor'),
                    nation_board,
                    nation.get('registered'),
                    nation.get('nationSpawn', {}).get('x') if nation.get('nationSpawn') else None,
                    nation.get('nationSpawn', {}).get('y') if nation.get('nationSpawn') else None,
                    nation.get('nationSpawn', {}).get('z') if nation.get('nationSpawn') else None,
                    nation.get('isPublic', False),
                    nation.get('isOpen', False),
                    is_neutral,
                    allies, enemies, towns, residents, sanctioned_towns,
                    num_towns, num_residents, num_town_blocks,
                    nation.get('nationTaxPercent', 0),
                    nation.get('nationTaxMax', 0),
                    nation.get('conqueredTax', 0),
                    datetime.now()
                ))

                # 변경 발생 시 히스토리 스냅샷 기록
                if should_record:
                    cursor.execute(self.adapter.adapt_sql('''
                        INSERT INTO nation_stats_history (
                            nation_uuid, name, king, capital, nation_board,
                            num_residents, num_towns, num_town_blocks,
                            towns, allies, enemies, is_neutral, recorded_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    '''), (
                        uuid, name, king, capital, nation_board,
                        num_residents, num_towns, num_town_blocks,
                        towns, allies, enemies, is_neutral,
                        datetime.now()
                    ))
                    history_count += 1

                saved_count += 1

              except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"[ERROR] 국가 upsert 실패 ({nation.get('name')}): {e}")

            conn.commit()
            conn.close()

            if deleted_count > 0:
                print(f"[DELETE] 총 {deleted_count}개 국가 삭제됨 (API에서 사라짐)")
            if history_count > 0:
                print(f"[HISTORY] 국가 변경 히스토리 {history_count}건 기록됨")
            if error_count > 0:
                print(f"[WARN] 국가 upsert 중 {error_count}건 오류 (성공: {saved_count})")

            return saved_count

        except Exception as e:
            print(f"[ERROR] 모든 국가 정보 저장 실패: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def get_nation_by_uuid(self, uuid: str) -> Optional[Dict]:
        """UUID로 국가 정보 조회 (all_nations 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM all_nations WHERE uuid = %s'), (uuid,))
            row = cursor.fetchone()

            conn.close()

            if row:
                result = dict(row)
                # JSON 문자열을 리스트로 파싱
                for field in ['allies', 'enemies', 'towns', 'residents', 'sanctioned_towns']:
                    if result.get(field):
                        try:
                            result[field] = json.loads(result[field])
                        except:
                            pass
                return result
            return None

        except Exception as e:
            print(f"[ERROR] 국가 UUID 조회 실패: {e}")
            return None

    def get_nation_by_name(self, name: str) -> Optional[Dict]:
        """이름으로 국가 정보 조회 (all_nations 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM all_nations WHERE name ILIKE %s'), (name,))
            row = cursor.fetchone()

            conn.close()

            if row:
                result = dict(row)
                for field in ['allies', 'enemies', 'towns', 'residents', 'sanctioned_towns']:
                    if result.get(field):
                        try:
                            result[field] = json.loads(result[field])
                        except:
                            pass
                return result
            return None

        except Exception as e:
            print(f"[ERROR] 국가 이름 조회 실패: {e}")
            return None

    def get_all_nations_list(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """모든 국가 조회 (all_nations 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            if limit is None:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM all_nations
                    ORDER BY num_residents DESC
                '''))
            else:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM all_nations
                    ORDER BY num_residents DESC
                    LIMIT %s OFFSET %s
                '''), (limit, offset))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 모든 국가 조회 실패: {e}")
            return []

    def get_total_nations(self) -> int:
        """전체 국가 수 조회 (all_nations 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) as count FROM all_nations'))
            result = cursor.fetchone()

            conn.close()

            return result['count'] if result else 0

        except Exception as e:
            print(f"[ERROR] 국가 수 조회 실패: {e}")
            return 0

    # ===== 모든 마을 정보 관리 (all_towns 테이블) =====

    def upsert_all_towns(self, towns: List[Dict]) -> int:
        """
        Town Bulk API에서 가져온 모든 마을 정보를 DB에 저장/업데이트.
        주요 필드 변경 시 town_stats_history에 스냅샷 기록.

        Args:
            towns: 마을 정보 리스트

        Returns:
            저장/업데이트된 레코드 수
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            dict_cursor = self._dict_cursor(conn)

            saved_count = 0
            history_count = 0
            error_count = 0

            for town in towns:
              try:
                uuid = town.get('uuid')
                name = town.get('name')

                if not uuid or not name:
                    continue

                # residents, outlaws, trusted를 JSON 문자열로 변환
                residents = json.dumps(town.get('residents', []), ensure_ascii=False) if town.get('residents') else None
                outlaws = json.dumps(town.get('outlaws', []), ensure_ascii=False) if town.get('outlaws') else None
                trusted = json.dumps(town.get('trusted', []), ensure_ascii=False) if town.get('trusted') else None

                nation = town.get('nation')
                mayor = town.get('mayor')
                founder = town.get('founder')
                town_board = town.get('townBoard')
                num_residents = town.get('numResidents', 0)
                num_town_blocks = town.get('numTownBlocks', 0)
                max_town_blocks = town.get('maxTownBlocks', 0)
                is_conquered = town.get('isConquered', False)
                is_neutral = town.get('isNeutral', False)

                # 변경 감지: 기존 DB 데이터와 비교
                dict_cursor.execute(self.adapter.adapt_sql(
                    'SELECT mayor, nation, num_residents, num_town_blocks, is_conquered, town_board FROM all_towns WHERE uuid = %s'
                ), (uuid,))
                _row = dict_cursor.fetchone()
                existing = dict(_row) if _row else None

                should_record = not existing or (
                    existing.get('mayor') != mayor or
                    existing.get('nation') != nation or
                    existing.get('num_residents') != num_residents or
                    existing.get('num_town_blocks') != num_town_blocks or
                    existing.get('is_conquered') != is_conquered or
                    existing.get('town_board') != town_board
                )

                # UPSERT into all_towns
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO all_towns (
                        uuid, name, nation, mayor, founder, town_board, tag, registered,
                        town_spawn_x, town_spawn_y, town_spawn_z, home_block,
                        is_public, is_open, is_neutral, is_conquered, is_ruined, is_for_sale,
                        for_sale_price, has_unlimited_claims,
                        residents, outlaws, trusted,
                        num_residents, num_town_blocks, max_town_blocks, bonus_blocks,
                        town_tax, town_tax_percent, town_tax_percent_cap, max_tax_percent_amount, is_tax_percent,
                        embassy_plot_tax, commercial_plot_tax, arena_plot_tax, shop_plot_tax, farm_plot_tax,
                        last_updated
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        name = EXCLUDED.name,
                        nation = EXCLUDED.nation,
                        mayor = EXCLUDED.mayor,
                        founder = EXCLUDED.founder,
                        town_board = EXCLUDED.town_board,
                        tag = EXCLUDED.tag,
                        registered = EXCLUDED.registered,
                        town_spawn_x = EXCLUDED.town_spawn_x,
                        town_spawn_y = EXCLUDED.town_spawn_y,
                        town_spawn_z = EXCLUDED.town_spawn_z,
                        home_block = EXCLUDED.home_block,
                        is_public = EXCLUDED.is_public,
                        is_open = EXCLUDED.is_open,
                        is_neutral = EXCLUDED.is_neutral,
                        is_conquered = EXCLUDED.is_conquered,
                        is_ruined = EXCLUDED.is_ruined,
                        is_for_sale = EXCLUDED.is_for_sale,
                        for_sale_price = EXCLUDED.for_sale_price,
                        has_unlimited_claims = EXCLUDED.has_unlimited_claims,
                        residents = EXCLUDED.residents,
                        outlaws = EXCLUDED.outlaws,
                        trusted = EXCLUDED.trusted,
                        num_residents = EXCLUDED.num_residents,
                        num_town_blocks = EXCLUDED.num_town_blocks,
                        max_town_blocks = EXCLUDED.max_town_blocks,
                        bonus_blocks = EXCLUDED.bonus_blocks,
                        town_tax = EXCLUDED.town_tax,
                        town_tax_percent = EXCLUDED.town_tax_percent,
                        town_tax_percent_cap = EXCLUDED.town_tax_percent_cap,
                        max_tax_percent_amount = EXCLUDED.max_tax_percent_amount,
                        is_tax_percent = EXCLUDED.is_tax_percent,
                        embassy_plot_tax = EXCLUDED.embassy_plot_tax,
                        commercial_plot_tax = EXCLUDED.commercial_plot_tax,
                        arena_plot_tax = EXCLUDED.arena_plot_tax,
                        shop_plot_tax = EXCLUDED.shop_plot_tax,
                        farm_plot_tax = EXCLUDED.farm_plot_tax,
                        last_updated = EXCLUDED.last_updated
                '''), (
                    uuid, name, nation, mayor, founder, town_board,
                    town.get('tag'),
                    town.get('registered'),
                    town.get('townSpawn', {}).get('x') if town.get('townSpawn') else None,
                    town.get('townSpawn', {}).get('y') if town.get('townSpawn') else None,
                    town.get('townSpawn', {}).get('z') if town.get('townSpawn') else None,
                    town.get('homeBlock'),
                    town.get('isPublic', False),
                    town.get('isOpen', False),
                    is_neutral, is_conquered,
                    town.get('isRuined', False),
                    town.get('isForSale', False),
                    town.get('forSalePrice', 0),
                    town.get('hasUnlimitedClaims', False),
                    residents, outlaws, trusted,
                    num_residents, num_town_blocks, max_town_blocks,
                    town.get('bonusBlocks', 0),
                    town.get('townTax', 0),
                    town.get('townTaxPercent', 0),
                    town.get('townTaxPercentCap', 0),
                    town.get('maxTaxPercentAmount', 0),
                    town.get('isTaxPercent', False),
                    town.get('embassyPlotTax', 0),
                    town.get('commercialPlotTax', 0),
                    town.get('arenaPlotTax', 0),
                    town.get('shopPlotTax', 0),
                    town.get('farmPlotTax', 0),
                    datetime.now()
                ))

                # 변경 발생 시 히스토리 스냅샷 기록
                if should_record:
                    cursor.execute(self.adapter.adapt_sql('''
                        INSERT INTO town_stats_history (
                            town_uuid, name, nation, mayor, founder, town_board,
                            num_residents, num_town_blocks, max_town_blocks,
                            is_conquered, is_neutral, recorded_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    '''), (
                        uuid, name, nation, mayor, founder, town_board,
                        num_residents, num_town_blocks, max_town_blocks,
                        is_conquered, is_neutral,
                        datetime.now()
                    ))
                    history_count += 1

                saved_count += 1

              except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"[ERROR] 마을 upsert 실패 ({town.get('name')}): {e}")

            conn.commit()
            conn.close()

            if history_count > 0:
                print(f"[HISTORY] 마을 변경 히스토리 {history_count}건 기록됨")
            if error_count > 0:
                print(f"[WARN] 마을 upsert 중 {error_count}건 오류 (성공: {saved_count})")

            return saved_count

        except Exception as e:
            print(f"[ERROR] 모든 마을 정보 저장 실패: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def get_town_by_uuid(self, uuid: str) -> Optional[Dict]:
        """UUID로 마을 정보 조회 (all_towns 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM all_towns WHERE uuid = %s'), (uuid,))
            row = cursor.fetchone()

            conn.close()

            if row:
                result = dict(row)
                for field in ['residents', 'outlaws', 'trusted']:
                    if result.get(field):
                        try:
                            result[field] = json.loads(result[field])
                        except:
                            pass
                return result
            return None

        except Exception as e:
            print(f"[ERROR] 마을 UUID 조회 실패: {e}")
            return None

    def get_town_by_name(self, name: str) -> Optional[Dict]:
        """이름으로 마을 정보 조회 (all_towns 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM all_towns WHERE name ILIKE %s'), (name,))
            row = cursor.fetchone()

            conn.close()

            if row:
                result = dict(row)
                for field in ['residents', 'outlaws', 'trusted']:
                    if result.get(field):
                        try:
                            result[field] = json.loads(result[field])
                        except:
                            pass
                return result
            return None

        except Exception as e:
            print(f"[ERROR] 마을 이름 조회 실패: {e}")
            return None

    def get_all_towns_list(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """모든 마을 조회 (all_towns 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            if limit is None:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM all_towns
                    ORDER BY num_residents DESC
                '''))
            else:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM all_towns
                    ORDER BY num_residents DESC
                    LIMIT %s OFFSET %s
                '''), (limit, offset))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 모든 마을 조회 실패: {e}")
            return []

    def get_towns_by_nation_name(self, nation_name: str) -> List[Dict]:
        """국가에 속한 마을 조회"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT * FROM all_towns
                WHERE nation ILIKE %s
                ORDER BY num_residents DESC
            '''), (nation_name,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 국가별 마을 조회 실패: {e}")
            return []

    def get_total_towns(self) -> int:
        """전체 마을 수 조회 (all_towns 테이블)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) as count FROM all_towns'))
            result = cursor.fetchone()

            conn.close()

            return result['count'] if result else 0

        except Exception as e:
            print(f"[ERROR] 마을 수 조회 실패: {e}")
            return 0

    # ===== 국가/마을 통계 히스토리 조회 =====

    def get_nation_stats_history(self, name: str, limit: int = 30) -> List[Dict]:
        """
        국가 통계 히스토리 조회 (nation_stats_history 테이블)

        Args:
            name: 국가 이름 (대소문자 무시)
            limit: 최대 반환 건수

        Returns:
            히스토리 리스트 (최신순)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT * FROM nation_stats_history
                WHERE name ILIKE %s
                ORDER BY recorded_at DESC
                LIMIT %s
            '''), (name, limit))
            rows = cursor.fetchall()

            conn.close()
            return [dict(r) for r in rows] if rows else []

        except Exception as e:
            print(f"[ERROR] 국가 히스토리 조회 실패: {e}")
            return []

    def get_town_stats_history(self, name: str, limit: int = 30) -> List[Dict]:
        """
        마을 통계 히스토리 조회 (town_stats_history 테이블)

        Args:
            name: 마을 이름 (대소문자 무시)
            limit: 최대 반환 건수

        Returns:
            히스토리 리스트 (최신순)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT * FROM town_stats_history
                WHERE name ILIKE %s
                ORDER BY recorded_at DESC
                LIMIT %s
            '''), (name, limit))
            rows = cursor.fetchall()

            conn.close()
            return [dict(r) for r in rows] if rows else []

        except Exception as e:
            print(f"[ERROR] 마을 히스토리 조회 실패: {e}")
            return []

    # ===== Red Mafia 가입일 관리 =====

    def set_red_mafia_joined(self, discord_id: int, joined_at: datetime = None) -> bool:
        """
        Red Mafia 가입일 설정

        Args:
            discord_id: 디스코드 사용자 ID
            joined_at: 가입 시간 (None이면 현재 시간)

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if joined_at is None:
                joined_at = datetime.now()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE users
                SET red_mafia_joined_at = %s
                WHERE discord_id = %s
            '''), (joined_at, discord_id))

            conn.commit()
            conn.close()

            print(f"[OK] Red Mafia 가입일 설정: {discord_id} -> {joined_at}")
            return True

        except Exception as e:
            print(f"[ERROR] Red Mafia 가입일 설정 실패: {e}")
            return False

    def get_red_mafia_joined(self, discord_id: int) -> Optional[datetime]:
        """
        Red Mafia 가입일 조회

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            가입 시간 (없으면 None)
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT red_mafia_joined_at FROM users WHERE discord_id = %s'), (discord_id,))
            result = cursor.fetchone()
            conn.close()

            if result and result['red_mafia_joined_at']:
                joined_val = result['red_mafia_joined_at']
                if isinstance(joined_val, datetime):
                    return joined_val
                elif isinstance(joined_val, str):
                    return datetime.fromisoformat(joined_val)

            return None

        except Exception as e:
            print(f"[ERROR] Red Mafia 가입일 조회 실패: {e}")
            return None

    def clear_red_mafia_joined(self, discord_id: int) -> bool:
        """
        Red Mafia 가입일 초기화 (국가 탈퇴 시)

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE users
                SET red_mafia_joined_at = NULL
                WHERE discord_id = %s
            '''), (discord_id,))

            conn.commit()
            conn.close()

            print(f"[OK] Red Mafia 가입일 초기화: {discord_id}")
            return True

        except Exception as e:
            print(f"[ERROR] Red Mafia 가입일 초기화 실패: {e}")
            return False

    def get_newbies_in_base_nation(self, nation_name: str, days: int = 14) -> List[Dict]:
        """
        특정 국가에서 지정된 기간 이내에 가입한 뉴비 목록 조회

        Args:
            nation_name: 국가 이름
            days: 기간 (일)

        Returns:
            뉴비 목록 [{discord_id, minecraft_name, red_mafia_joined_at, ...}]
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql(f'''
                SELECT u.discord_id, u.current_minecraft_name, u.minecraft_uuid,
                       u.red_mafia_joined_at, u.current_nation
                FROM users u
                WHERE u.current_nation ILIKE %s
                  AND u.red_mafia_joined_at IS NOT NULL
                  AND {interval_ago('u.red_mafia_joined_at', '>=')}
                ORDER BY u.red_mafia_joined_at DESC
            '''), (nation_name, days))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 뉴비 목록 조회 실패: {e}")
            return []

    def get_expired_newbies(self, nation_name: str, days: int = 14) -> List[Dict]:
        """
        특정 국가에서 뉴비 기간이 만료된 사용자 목록 조회

        Args:
            nation_name: 국가 이름
            days: 뉴비 기간 (일)

        Returns:
            만료된 뉴비 목록
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql(f'''
                SELECT u.discord_id, u.current_minecraft_name, u.minecraft_uuid,
                       u.red_mafia_joined_at, u.current_nation
                FROM users u
                WHERE u.current_nation ILIKE %s
                  AND u.red_mafia_joined_at IS NOT NULL
                  AND {interval_ago('u.red_mafia_joined_at', '<')}
                ORDER BY u.red_mafia_joined_at ASC
            '''), (nation_name, days))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 만료된 뉴비 목록 조회 실패: {e}")
            return []

    def backfill_red_mafia_joined(self, nation_name: str, days_ago: int = 14) -> int:
        """
        이미 BASE_NATION에 있지만 red_mafia_joined_at이 NULL인 사용자들의 가입일을 설정
        기존 멤버는 이미 뉴비 기간이 지났다고 가정하여 기본값으로 2주 전으로 설정

        Args:
            nation_name: 국가 이름
            days_ago: 며칠 전으로 설정할지 (기본값: 14일 = 2주)

        Returns:
            업데이트된 레코드 수
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql(f'''
                UPDATE users
                SET red_mafia_joined_at = {interval_set()}
                WHERE current_nation ILIKE %s
                  AND red_mafia_joined_at IS NULL
            '''), (days_ago, nation_name))

            updated_count = cursor.rowcount

            conn.commit()
            conn.close()

            print(f"[OK] Red Mafia 가입일 일괄 설정: {updated_count}명 ({days_ago}일 전으로)")
            return updated_count

        except Exception as e:
            print(f"[ERROR] Red Mafia 가입일 일괄 설정 실패: {e}")
            return 0

    # ===== 여행 시스템 관리 =====

    def init_travel_tables(self):
        """여행 관련 테이블 생성"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 여행 신청 테이블
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE TABLE IF NOT EXISTS travels (
                    id SERIAL PRIMARY KEY,
                    travel_id TEXT UNIQUE NOT NULL,
                    discord_id BIGINT NOT NULL,
                    minecraft_name TEXT,
                    current_nation TEXT,
                    current_town TEXT,
                    destination_nation TEXT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    callsign TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    reviewed_by BIGINT,
                    review_reason TEXT,
                    reviewed_at TIMESTAMP,
                    message_id BIGINT,
                    notified_1day BOOLEAN DEFAULT FALSE,
                    notified_end BOOLEAN DEFAULT FALSE
                )
            '''))

            # 여행 테이블 인덱스
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_travels_discord_id
                ON travels(discord_id)
            '''))

            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_travels_status
                ON travels(status)
            '''))

            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_travels_end_date
                ON travels(end_date)
            '''))

            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_travels_travel_id
                ON travels(travel_id)
            '''))

            conn.commit()
            conn.close()
            print("[OK] 여행 테이블 초기화 완료")
            return True

        except Exception as e:
            print(f"[ERROR] 여행 테이블 초기화 실패: {e}")
            return False

    def set_user_traveling(self, discord_id: int, is_traveling: bool = True) -> bool:
        """
        사용자의 여행 상태 설정

        Args:
            discord_id: 디스코드 사용자 ID
            is_traveling: 여행 중 여부

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # users 테이블에 is_traveling 컬럼이 없으면 추가
            self.adapter.add_column_safe(cursor, 'users', 'is_traveling', 'BOOLEAN', 'FALSE')

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE users
                SET is_traveling = %s, last_updated = %s
                WHERE discord_id = %s
            '''), (is_traveling, datetime.now(), discord_id))

            conn.commit()
            conn.close()

            print(f"[OK] 사용자 여행 상태 설정: {discord_id} -> {is_traveling}")
            return True

        except Exception as e:
            print(f"[ERROR] 사용자 여행 상태 설정 실패: {e}")
            return False

    def is_user_traveling(self, discord_id: int) -> bool:
        """
        사용자가 여행 중인지 확인

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            여행 중 여부
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT is_traveling FROM users WHERE discord_id = %s
            '''), (discord_id,))

            result = cursor.fetchone()
            conn.close()

            if result:
                return result.get('is_traveling', False) or False

            return False

        except Exception as e:
            print(f"[ERROR] 사용자 여행 상태 조회 실패: {e}")
            return False

    # ===== 경고 시스템 관리 =====

    def init_warning_tables(self):
        """경고 관련 테이블 생성"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 경고 테이블
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE TABLE IF NOT EXISTS warnings (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    discord_id BIGINT NOT NULL,
                    warned_by BIGINT NOT NULL,
                    reason TEXT DEFAULT '사유 없음',
                    count INTEGER DEFAULT 1,
                    action_type TEXT DEFAULT 'give',
                    reference_id INTEGER,
                    created_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    removed_by BIGINT,
                    removed_at TIMESTAMP,
                    message_id BIGINT,
                    FOREIGN KEY (discord_id) REFERENCES users(discord_id)
                )
            '''))

            # 기존 테이블에 새 컬럼 추가 (이미 있으면 무시)
            for i, col_sql in enumerate([
                'ALTER TABLE warnings ADD COLUMN count INTEGER DEFAULT 1',
                "ALTER TABLE warnings ADD COLUMN action_type TEXT DEFAULT 'give'",
                'ALTER TABLE warnings ADD COLUMN reference_id INTEGER',
            ]):
                try:
                    cursor.execute(f"SAVEPOINT sp_alter_{i}")
                    cursor.execute(self.adapter.adapt_ddl(col_sql))
                    cursor.execute(f"RELEASE SAVEPOINT sp_alter_{i}")
                except Exception:
                    cursor.execute(f"ROLLBACK TO SAVEPOINT sp_alter_{i}")

            # 경고 테이블 인덱스
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_warnings_discord_id
                ON warnings(discord_id)
            '''))
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_warnings_guild_id
                ON warnings(guild_id)
            '''))
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_warnings_is_active
                ON warnings(is_active)
            '''))
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE INDEX IF NOT EXISTS idx_warnings_guild_discord
                ON warnings(guild_id, discord_id)
            '''))

            # 경고 설정 테이블
            cursor.execute(self.adapter.adapt_ddl('''
                CREATE TABLE IF NOT EXISTS warning_config (
                    guild_id BIGINT PRIMARY KEY,
                    log_channel_id BIGINT,
                    expiration_days INTEGER DEFAULT 30,
                    punishments TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            '''))

            conn.commit()
            conn.close()
            print("[OK] 경고 테이블 초기화 완료")
            return True

        except Exception as e:
            print(f"[ERROR] 경고 테이블 초기화 실패: {e}")
            return False

    def add_warning(self, guild_id: int, discord_id: int, warned_by: int,
                    reason: str = '사유 없음', count: int = 1) -> Optional[Dict]:
        """
        경고 추가

        Args:
            guild_id: 길드 ID
            discord_id: 대상 디스코드 ID
            warned_by: 경고 부여 관리자 ID
            reason: 경고 사유
            count: 경고 횟수

        Returns:
            생성된 경고 레코드 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            self.ensure_user_exists(discord_id, cursor)

            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO warnings (guild_id, discord_id, warned_by, reason, count, action_type)
                VALUES (%s, %s, %s, %s, %s, 'give')
                RETURNING id, guild_id, discord_id, warned_by, reason, count, action_type, reference_id, created_at, is_active
            '''), (guild_id, discord_id, warned_by, reason, count))

            result = cursor.fetchone()
            conn.commit()
            conn.close()

            if result:
                print(f"[OK] 경고 추가: {discord_id} (#{result['id']}, {count}회)")
                return dict(result)
            return None

        except Exception as e:
            print(f"[ERROR] 경고 추가 실패: {e}")
            return None

    def log_warning_action(self, guild_id: int, discord_id: int, action_by: int,
                           action_type: str, reason: str = '', reference_id: int = None) -> Optional[Dict]:
        """
        경고 행위 로그 기록 (취소/수정/삭제/초기화 등)
        모든 행위에 고유 ID가 부여됨.
        """
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            self.ensure_user_exists(discord_id, cursor)

            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO warnings (guild_id, discord_id, warned_by, action_type, reason, count, reference_id, is_active)
                VALUES (%s, %s, %s, %s, %s, 0, %s, FALSE)
                RETURNING id, guild_id, discord_id, warned_by, action_type, reason, count, reference_id, created_at
            '''), (guild_id, discord_id, action_by, action_type, reason, reference_id))

            result = cursor.fetchone()
            conn.commit()
            conn.close()

            if result:
                ref_text = f" (#{reference_id})" if reference_id else ""
                print(f"[OK] 경고 행위 로그: {action_type}{ref_text} -> #{result['id']}")
                return dict(result)
            return None

        except Exception as e:
            print(f"[ERROR] 경고 행위 로그 실패: {e}")
            return None

    def update_warning_reason(self, warning_id: int, new_reason: str) -> bool:
        """경고 사유 수정"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE warnings SET reason = %s WHERE id = %s
            '''), (new_reason, warning_id))

            updated = cursor.rowcount
            conn.commit()
            conn.close()

            if updated > 0:
                print(f"[OK] 경고 사유 수정: #{warning_id}")
            return updated > 0

        except Exception as e:
            print(f"[ERROR] 경고 사유 수정 실패: {e}")
            return False

    def update_warning_message_id(self, warning_id: int, message_id: int) -> bool:
        """경고 로그 메시지 ID 저장"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE warnings SET message_id = %s WHERE id = %s
            '''), (message_id, warning_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 경고 메시지 ID 저장 실패: {e}")
            return False

    def get_warning_by_id(self, warning_id: int) -> Optional[Dict]:
        """특정 경고 ID로 조회"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM warnings WHERE id = %s'), (warning_id,))
            row = cursor.fetchone()
            conn.close()

            return dict(row) if row else None

        except Exception as e:
            print(f"[ERROR] 경고 조회 실패: {e}")
            return None

    def remove_warning(self, warning_id: int, removed_by: int) -> bool:
        """특정 경고 ID 비활성화"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE warnings
                SET is_active = FALSE, removed_by = %s, removed_at = NOW()
                WHERE id = %s AND is_active = TRUE
            '''), (removed_by, warning_id))

            updated = cursor.rowcount
            conn.commit()
            conn.close()

            if updated > 0:
                print(f"[OK] 경고 제거: #{warning_id}")
            return updated > 0

        except Exception as e:
            print(f"[ERROR] 경고 제거 실패: {e}")
            return False

    def remove_latest_warning(self, guild_id: int, discord_id: int, removed_by: int) -> Optional[int]:
        """최근 활성 경고 1건 제거, 제거된 경고 ID 반환"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE warnings
                SET is_active = FALSE, removed_by = %s, removed_at = NOW()
                WHERE id = (
                    SELECT id FROM warnings
                    WHERE guild_id = %s AND discord_id = %s AND is_active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                RETURNING id
            '''), (removed_by, guild_id, discord_id))

            result = cursor.fetchone()
            conn.commit()
            conn.close()

            if result:
                print(f"[OK] 최근 경고 제거: #{result['id']}")
                return result['id']
            return None

        except Exception as e:
            print(f"[ERROR] 최근 경고 제거 실패: {e}")
            return None

    def reset_warnings(self, guild_id: int, discord_id: int, removed_by: int) -> int:
        """유저의 모든 활성 경고 비활성화"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE warnings
                SET is_active = FALSE, removed_by = %s, removed_at = NOW()
                WHERE guild_id = %s AND discord_id = %s AND is_active = TRUE
            '''), (removed_by, guild_id, discord_id))

            count = cursor.rowcount
            conn.commit()
            conn.close()

            print(f"[OK] 경고 초기화: {discord_id} ({count}개)")
            return count

        except Exception as e:
            print(f"[ERROR] 경고 초기화 실패: {e}")
            return 0

    def get_user_warnings(self, guild_id: int, discord_id: int, active_only: bool = True) -> List[Dict]:
        """유저 경고 목록 조회"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            if active_only:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM warnings
                    WHERE guild_id = %s AND discord_id = %s
                        AND is_active = TRUE
                    ORDER BY created_at DESC
                '''), (guild_id, discord_id))
            else:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM warnings
                    WHERE guild_id = %s AND discord_id = %s
                    ORDER BY created_at DESC
                '''), (guild_id, discord_id))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 유저 경고 조회 실패: {e}")
            return []

    def get_active_warning_count(self, guild_id: int, discord_id: int) -> int:
        """활성 경고 수 (count 컬럼 합산, give 타입만)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT COALESCE(SUM(count), 0) as count FROM warnings
                WHERE guild_id = %s AND discord_id = %s
                    AND is_active = TRUE AND action_type = 'give'
            '''), (guild_id, discord_id))

            result = cursor.fetchone()
            conn.close()

            return result['count'] if result else 0

        except Exception as e:
            print(f"[ERROR] 활성 경고 수 조회 실패: {e}")
            return 0

    def get_all_warned_users(self, guild_id: int) -> List[Dict]:
        """활성 경고가 있는 전체 유저 목록"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT discord_id,
                       COALESCE(SUM(count), 0) as active_count,
                       MAX(created_at) as latest_warning_at
                FROM warnings
                WHERE guild_id = %s AND is_active = TRUE AND action_type = 'give'
                GROUP BY discord_id
                ORDER BY active_count DESC
            '''), (guild_id,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 경고 유저 목록 조회 실패: {e}")
            return []

    def get_warnings_with_message_id(self, guild_id: int) -> List[Dict]:
        """message_id가 있는 활성 경고 목록 (영구 View 복원용)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT id, message_id FROM warnings
                WHERE guild_id = %s AND is_active = TRUE AND message_id IS NOT NULL
                    AND action_type = 'give'
            '''), (guild_id,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"[ERROR] 경고 메시지 목록 조회 실패: {e}")
            return []

    # ===== 경고 설정 관리 =====

    def get_warning_config(self, guild_id: int) -> Dict:
        """길드 경고 설정 조회 (없으면 기본값)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT * FROM warning_config WHERE guild_id = %s'), (guild_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)

            return {
                'guild_id': guild_id,
                'log_channel_id': None,
                'punishments': '{}',
                'updated_at': None
            }

        except Exception as e:
            print(f"[ERROR] 경고 설정 조회 실패: {e}")
            return {
                'guild_id': guild_id,
                'log_channel_id': None,
                'punishments': '{}',
                'updated_at': None
            }

    def set_warning_log_channel(self, guild_id: int, channel_id: int) -> bool:
        """경고 로그 채널 설정"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO warning_config (guild_id, log_channel_id, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (guild_id) DO UPDATE SET
                    log_channel_id = EXCLUDED.log_channel_id,
                    updated_at = EXCLUDED.updated_at
            '''), (guild_id, channel_id))

            conn.commit()
            conn.close()

            print(f"[OK] 경고 로그 채널 설정: {guild_id} -> {channel_id}")
            return True

        except Exception as e:
            print(f"[ERROR] 경고 로그 채널 설정 실패: {e}")
            return False

    def set_warning_punishments(self, guild_id: int, punishments_json: str) -> bool:
        """자동 처벌 규칙 설정"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO warning_config (guild_id, punishments, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (guild_id) DO UPDATE SET
                    punishments = EXCLUDED.punishments,
                    updated_at = EXCLUDED.updated_at
            '''), (guild_id, punishments_json))

            conn.commit()
            conn.close()

            print(f"[OK] 자동 처벌 규칙 설정: {guild_id}")
            return True

        except Exception as e:
            print(f"[ERROR] 자동 처벌 규칙 설정 실패: {e}")
            return False

    # ===== 역할 신청 패널 메서드 =====

    def create_role_panel(self, guild_id: int, role_id: int, title: str, description: str, created_by: int) -> Optional[str]:
        """역할 신청 패널 생성, panel_id 반환"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('SELECT MAX(id) as max_id FROM role_panels'))
            row = cursor.fetchone()
            next_num = ((row['max_id'] if isinstance(row, dict) else row[0]) or 0) + 1
            panel_id = f"RP{next_num:04d}"

            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO role_panels (panel_id, guild_id, role_id, title, description, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            '''), (panel_id, guild_id, role_id, title, description, created_by))

            conn.commit()
            conn.close()
            print(f"[OK] 역할 패널 생성: {panel_id}")
            return panel_id

        except Exception as e:
            print(f"[ERROR] 역할 패널 생성 실패: {e}")
            return None

    def get_role_panel(self, panel_id: str) -> Optional[Dict]:
        """패널 ID로 패널 정보 조회"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql(
                'SELECT * FROM role_panels WHERE panel_id = %s'
            ), (panel_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None

        except Exception as e:
            print(f"[ERROR] 역할 패널 조회 실패: {e}")
            return None

    def update_role_panel_message(self, panel_id: str, channel_id: int, message_id: int) -> bool:
        """패널의 채널/메시지 ID 업데이트"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE role_panels SET channel_id = %s, message_id = %s WHERE panel_id = %s
            '''), (channel_id, message_id, panel_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 역할 패널 메시지 업데이트 실패: {e}")
            return False

    def set_role_panel_review_channel(self, panel_id: str, channel_id: int) -> bool:
        """패널의 리뷰 채널 설정"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE role_panels SET review_channel_id = %s WHERE panel_id = %s
            '''), (channel_id, panel_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 리뷰 채널 설정 실패: {e}")
            return False

    def add_role_panel_user(self, panel_id: str, discord_id: int) -> bool:
        """패널에 유저 신청 추가 (기각된 유저는 재신청 가능)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                INSERT INTO role_panel_users (panel_id, discord_id, status, applied_at)
                VALUES (%s, %s, 'pending', NOW())
                ON CONFLICT (panel_id, discord_id) DO UPDATE SET
                    status = 'pending',
                    applied_at = NOW(),
                    reviewed_by = NULL,
                    reviewed_at = NULL
            '''), (panel_id, discord_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 역할 패널 유저 추가 실패: {e}")
            return False

    def update_role_panel_user_status(self, panel_id: str, discord_id: int, status: str, reviewed_by: int) -> bool:
        """유저 신청 상태 업데이트 (approved/denied)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                UPDATE role_panel_users
                SET status = %s, reviewed_by = %s, reviewed_at = NOW()
                WHERE panel_id = %s AND discord_id = %s
            '''), (status, reviewed_by, panel_id, discord_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"[ERROR] 유저 상태 업데이트 실패: {e}")
            return False

    def check_role_panel_user(self, panel_id: str, discord_id: int) -> Optional[Dict]:
        """유저 신청 상태 조회 (없으면 None)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            cursor.execute(self.adapter.adapt_sql('''
                SELECT status, applied_at FROM role_panel_users
                WHERE panel_id = %s AND discord_id = %s
            '''), (panel_id, discord_id))

            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None

        except Exception as e:
            print(f"[ERROR] 역할 패널 유저 확인 실패: {e}")
            return None

    def get_role_panel_users(self, panel_id: str, status: str = None) -> List[Dict]:
        """패널의 신청 유저 조회 (status 필터 가능)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            if status:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT discord_id, status, applied_at FROM role_panel_users
                    WHERE panel_id = %s AND status = %s ORDER BY applied_at
                '''), (panel_id, status))
            else:
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT discord_id, status, applied_at FROM role_panel_users
                    WHERE panel_id = %s ORDER BY applied_at
                '''), (panel_id,))

            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

        except Exception as e:
            print(f"[ERROR] 역할 패널 유저 목록 조회 실패: {e}")
            return []

    def clear_role_panel_users(self, panel_id: str) -> int:
        """패널의 모든 유저 삭제, 삭제된 수 반환"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql('''
                DELETE FROM role_panel_users WHERE panel_id = %s
            '''), (panel_id,))

            count = cursor.rowcount
            conn.commit()
            conn.close()
            return count

        except Exception as e:
            print(f"[ERROR] 역할 패널 유저 일괄 삭제 실패: {e}")
            return 0

    def delete_role_panel(self, panel_id: str) -> bool:
        """패널 및 관련 유저 데이터 삭제"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(self.adapter.adapt_sql(
                'DELETE FROM role_panel_users WHERE panel_id = %s'
            ), (panel_id,))
            cursor.execute(self.adapter.adapt_sql(
                'DELETE FROM role_panels WHERE panel_id = %s'
            ), (panel_id,))

            conn.commit()
            conn.close()
            print(f"[OK] 역할 패널 삭제: {panel_id}")
            return True

        except Exception as e:
            print(f"[ERROR] 역할 패널 삭제 실패: {e}")
            return False

    def get_active_role_panels(self, guild_id: int = None) -> List[Dict]:
        """활성 역할 패널 목록 조회 (View 복구용)"""
        try:
            conn = self.get_connection()
            cursor = self._dict_cursor(conn)

            if guild_id:
                cursor.execute(self.adapter.adapt_sql(
                    'SELECT * FROM role_panels WHERE guild_id = %s'
                ), (guild_id,))
            else:
                cursor.execute(self.adapter.adapt_sql(
                    'SELECT * FROM role_panels'
                ))

            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]

        except Exception as e:
            print(f"[ERROR] 역할 패널 목록 조회 실패: {e}")
            return []


# 전역 데이터베이스 관리자 인스턴스
db_manager = DatabaseManager()
print("[OK] DatabaseManager 인스턴스 생성됨")

# 여행 테이블 초기화
db_manager.init_travel_tables()

# 경고 테이블 초기화
db_manager.init_warning_tables()
