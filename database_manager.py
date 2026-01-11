# database_manager.py - SQLite 데이터베이스 관리

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import json

class DatabaseManager:
    """디스코드 ID, Minecraft UUID, 닉네임 히스토리를 관리하는 데이터베이스"""

    def __init__(self, db_path: str = "data/discord_minecraft.db"):
        """
        데이터베이스 관리자 초기화

        Args:
            db_path: 데이터베이스 파일 경로
        """
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.db_path = db_path
        self.init_database()
        print(f"✅ 데이터베이스 초기화 완료: {db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """데이터베이스 연결 생성"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 딕셔너리 형태로 결과 반환
        return conn

    def init_database(self):
        """데이터베이스 테이블 생성"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 사용자 기본 정보 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                minecraft_uuid TEXT,
                current_minecraft_name TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Minecraft 닉네임 히스토리 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS minecraft_name_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                minecraft_uuid TEXT,
                minecraft_name TEXT NOT NULL,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        ''')

        # 국가 히스토리 테이블 (신규)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                nation_name TEXT,
                nation_uuid TEXT,
                town_name TEXT,
                town_uuid TEXT,
                nation_ranks TEXT,
                town_ranks TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        ''')

        # nation_ranks, town_ranks 컬럼 추가 (기존 테이블에 없는 경우)
        try:
            cursor.execute('ALTER TABLE nation_history ADD COLUMN nation_ranks TEXT')
            print("✅ nation_history 테이블에 nation_ranks 컬럼 추가됨")
        except sqlite3.OperationalError:
            pass  # 이미 존재하는 경우 무시

        try:
            cursor.execute('ALTER TABLE nation_history ADD COLUMN town_ranks TEXT')
            print("✅ nation_history 테이블에 town_ranks 컬럼 추가됨")
        except sqlite3.OperationalError:
            pass  # 이미 존재하는 경우 무시

        # 인덱스 생성 (조회 성능 향상)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_discord_id
            ON minecraft_name_history(discord_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_minecraft_uuid
            ON users(minecraft_uuid)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_minecraft_name
            ON minecraft_name_history(minecraft_name)
        ''')

        # 국가 히스토리 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_nation_history_discord_id
            ON nation_history(discord_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_nation_history_nation
            ON nation_history(nation_name)
        ''')

        # 콜사인 테이블 (신규)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS callsigns (
                discord_id INTEGER PRIMARY KEY,
                callsign TEXT NOT NULL,
                set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                admin_override INTEGER DEFAULT 0,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        ''')

        # 콜사인 히스토리 테이블 (신규)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS callsign_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                callsign TEXT NOT NULL,
                set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                admin_override INTEGER DEFAULT 0,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        ''')

        # 콜사인 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_callsign_discord_id
            ON callsigns(discord_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_callsign_history_discord_id
            ON callsign_history(discord_id)
        ''')

        # 모든 마인크래프트 플레이어 정보 테이블 (Bulk API 전체 데이터)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS all_players (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                nation TEXT,
                town TEXT,
                nation_ranks TEXT,
                town_ranks TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 모든 플레이어 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_all_players_name
            ON all_players(name)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_all_players_nation
            ON all_players(nation)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_all_players_town
            ON all_players(town)
        ''')

        # 콜사인 쿨타임 테이블 (신규)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS callsign_cooldowns (
                discord_id INTEGER PRIMARY KEY,
                cooldown_end TIMESTAMP NOT NULL,
                set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        ''')

        # 콜사인 쿨타임 인덱스
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cooldown_discord_id
            ON callsign_cooldowns(discord_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cooldown_end
            ON callsign_cooldowns(cooldown_end)
        ''')

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
            cursor = conn.cursor()

            # 기존 사용자 확인
            cursor.execute('SELECT * FROM users WHERE discord_id = ?', (discord_id,))
            existing_user = cursor.fetchone()

            if existing_user:
                # 기존 사용자 업데이트
                old_name = existing_user['current_minecraft_name']

                # 닉네임이 변경되었는지 확인
                if old_name != minecraft_name:
                    # 사용자 정보 업데이트
                    cursor.execute('''
                        UPDATE users
                        SET minecraft_uuid = ?, current_minecraft_name = ?, last_updated = ?
                        WHERE discord_id = ?
                    ''', (minecraft_uuid, minecraft_name, datetime.now(), discord_id))

                    # 닉네임 히스토리에 추가
                    cursor.execute('''
                        INSERT INTO minecraft_name_history (discord_id, minecraft_uuid, minecraft_name)
                        VALUES (?, ?, ?)
                    ''', (discord_id, minecraft_uuid, minecraft_name))

                    print(f"📝 닉네임 변경 감지: {discord_id} - {old_name} → {minecraft_name}")
                else:
                    # 닉네임은 같지만 UUID나 last_updated만 업데이트
                    cursor.execute('''
                        UPDATE users
                        SET minecraft_uuid = ?, last_updated = ?
                        WHERE discord_id = ?
                    ''', (minecraft_uuid, datetime.now(), discord_id))
            else:
                # 새 사용자 추가
                cursor.execute('''
                    INSERT INTO users (discord_id, minecraft_uuid, current_minecraft_name)
                    VALUES (?, ?, ?)
                ''', (discord_id, minecraft_uuid, minecraft_name))

                # 첫 닉네임 히스토리 추가
                cursor.execute('''
                    INSERT INTO minecraft_name_history (discord_id, minecraft_uuid, minecraft_name)
                    VALUES (?, ?, ?)
                ''', (discord_id, minecraft_uuid, minecraft_name))

                print(f"➕ 새 사용자 추가: {discord_id} - {minecraft_name}")

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"❌ 사용자 정보 저장 실패: {e}")
            return False

    def get_user_info(self, discord_id: int) -> Optional[Dict]:
        """
        사용자 기본 정보 조회

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            사용자 정보 딕셔너리 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM users WHERE discord_id = ?', (discord_id,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row)
            return None

        except Exception as e:
            print(f"❌ 사용자 정보 조회 실패: {e}")
            return None

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
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM minecraft_name_history
                WHERE discord_id = ?
                ORDER BY changed_at DESC
                LIMIT ?
            ''', (discord_id, limit))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"❌ 닉네임 히스토리 조회 실패: {e}")
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
            cursor = conn.cursor()

            # 현재 닉네임 또는 과거 닉네임에서 검색
            cursor.execute('''
                SELECT DISTINCT u.*
                FROM users u
                LEFT JOIN minecraft_name_history h ON u.discord_id = h.discord_id
                WHERE u.current_minecraft_name LIKE ? OR h.minecraft_name LIKE ?
            ''', (f'%{minecraft_name}%', f'%{minecraft_name}%'))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"❌ 닉네임 검색 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM users WHERE minecraft_uuid = ?', (minecraft_uuid,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row)
            return None

        except Exception as e:
            print(f"❌ UUID 검색 실패: {e}")
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
            cursor = conn.cursor()

            if limit is None:
                # limit이 None이면 전체 조회
                cursor.execute('''
                    SELECT * FROM users
                    ORDER BY last_updated DESC
                ''')
            else:
                # limit이 있으면 페이지네이션
                cursor.execute('''
                    SELECT * FROM users
                    ORDER BY last_updated DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"❌ 전체 사용자 조회 실패: {e}")
            return []

    def get_total_users(self) -> int:
        """전체 사용자 수 조회"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) as count FROM users')
            result = cursor.fetchone()

            conn.close()

            return result['count'] if result else 0

        except Exception as e:
            print(f"❌ 사용자 수 조회 실패: {e}")
            return 0

    def get_statistics(self) -> Dict:
        """데이터베이스 통계 정보 조회"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 전체 사용자 수
            cursor.execute('SELECT COUNT(*) as count FROM users')
            total_users = cursor.fetchone()['count']

            # 전체 닉네임 변경 횟수
            cursor.execute('SELECT COUNT(*) as count FROM minecraft_name_history')
            total_name_changes = cursor.fetchone()['count']

            # 최근 24시간 내 업데이트된 사용자 수
            cursor.execute('''
                SELECT COUNT(*) as count FROM users
                WHERE last_updated >= datetime('now', '-1 day')
            ''')
            recent_updates = cursor.fetchone()['count']

            # 닉네임을 가장 많이 변경한 사용자 Top 5
            cursor.execute('''
                SELECT discord_id, COUNT(*) as change_count
                FROM minecraft_name_history
                GROUP BY discord_id
                ORDER BY change_count DESC
                LIMIT 5
            ''')
            top_changers = [dict(row) for row in cursor.fetchall()]

            conn.close()

            return {
                'total_users': total_users,
                'total_name_changes': total_name_changes,
                'recent_updates': recent_updates,
                'top_changers': top_changers
            }

        except Exception as e:
            print(f"❌ 통계 조회 실패: {e}")
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
            cursor.execute('DELETE FROM minecraft_name_history WHERE discord_id = ?', (discord_id,))

            # 사용자 정보 삭제
            cursor.execute('DELETE FROM users WHERE discord_id = ?', (discord_id,))

            conn.commit()
            conn.close()

            print(f"🗑️ 사용자 정보 삭제: {discord_id}")
            return True

        except Exception as e:
            print(f"❌ 사용자 삭제 실패: {e}")
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

            cursor.execute('''
                DELETE FROM minecraft_name_history
                WHERE changed_at < datetime('now', '-' || ? || ' days')
            ''', (days,))

            deleted_count = cursor.rowcount

            conn.commit()
            conn.close()

            print(f"🗑️ {days}일 이전 히스토리 {deleted_count}개 삭제")
            return deleted_count

        except Exception as e:
            print(f"❌ 히스토리 정리 실패: {e}")
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
            cursor = conn.cursor()

            # 가장 최근 국가 히스토리 조회
            cursor.execute('''
                SELECT nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks
                FROM nation_history
                WHERE discord_id = ?
                ORDER BY changed_at DESC
                LIMIT 1
            ''', (discord_id,))

            last_record = cursor.fetchone()

            # 변경사항이 있는지 확인
            if last_record:
                if (last_record['nation_name'] == nation_name and
                    last_record['nation_uuid'] == nation_uuid and
                    last_record['town_name'] == town_name and
                    last_record['town_uuid'] == town_uuid and
                    last_record['nation_ranks'] == nation_ranks and
                    last_record['town_ranks'] == town_ranks):
                    # 변경사항 없음
                    conn.close()
                    return True

            # 새 히스토리 추가
            cursor.execute('''
                INSERT INTO nation_history (discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (discord_id, nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks))

            conn.commit()
            conn.close()

            print(f"📝 국가 히스토리 추가: {discord_id} - {nation_name}/{town_name} (국가 계급: {nation_ranks}, 마을 계급: {town_ranks})")
            return True

        except Exception as e:
            print(f"❌ 국가 히스토리 저장 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM nation_history
                WHERE discord_id = ?
                ORDER BY changed_at DESC
                LIMIT ?
            ''', (discord_id, limit))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"❌ 국가 히스토리 조회 실패: {e}")
            return []

    def get_current_nation(self, discord_id: int) -> Optional[Dict]:
        """
        사용자의 현재 국가 정보 조회 (가장 최근 기록)

        Args:
            discord_id: 디스코드 사용자 ID

        Returns:
            국가 정보 딕셔너리 또는 None
            {
                'nation_name': str,
                'nation_uuid': str,
                'town_name': str,
                'town_uuid': str,
                'nation_ranks': str,
                'town_ranks': str,
                'changed_at': str
            }
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT nation_name, nation_uuid, town_name, town_uuid, nation_ranks, town_ranks, changed_at
                FROM nation_history
                WHERE discord_id = ?
                ORDER BY changed_at DESC
                LIMIT 1
            ''', (discord_id,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
            return None

        except Exception as e:
            print(f"❌ 현재 국가 조회 실패: {e}")
            return None

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
            cursor = conn.cursor()

            # 모든 사용자 조회
            cursor.execute('SELECT * FROM users')
            users = [dict(row) for row in cursor.fetchall()]

            # 모든 히스토리 조회
            cursor.execute('SELECT * FROM minecraft_name_history ORDER BY discord_id, changed_at')
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

            print(f"📤 데이터베이스 내보내기 완료: {output_file}")
            return True

        except Exception as e:
            print(f"❌ 데이터베이스 내보내기 실패: {e}")
            return False

    def set_callsign(self, discord_id: int, callsign: str, admin_override: bool = False) -> bool:
        """
        사용자 콜사인 설정 (DB에 저장)

        Args:
            discord_id: 디스코드 사용자 ID
            callsign: 콜사인
            admin_override: 관리자가 강제로 설정했는지 여부

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 기존 콜사인 확인
            cursor.execute('SELECT callsign, admin_override FROM callsigns WHERE discord_id = ?', (discord_id,))
            existing = cursor.fetchone()

            # 이미 같은 콜사인이 저장되어 있으면 건너뛰기
            if existing and existing[0] == callsign and existing[1] == (1 if admin_override else 0):
                conn.close()
                return True  # 중복 저장 방지, 로그 없이 조용히 성공 반환

            if existing:
                # 기존 콜사인이 있으면 업데이트
                cursor.execute('''
                    UPDATE callsigns
                    SET callsign = ?, set_at = ?, admin_override = ?
                    WHERE discord_id = ?
                ''', (callsign, datetime.now(), 1 if admin_override else 0, discord_id))

                # 콜사인이 변경된 경우에만 히스토리에 추가
                cursor.execute('''
                    INSERT INTO callsign_history (discord_id, callsign, set_at, admin_override)
                    VALUES (?, ?, ?, ?)
                ''', (discord_id, callsign, datetime.now(), 1 if admin_override else 0))

                print(f"✅ DB에 콜사인 업데이트 완료: {discord_id} -> {callsign}")
            else:
                # 새로운 콜사인 추가
                cursor.execute('''
                    INSERT INTO callsigns (discord_id, callsign, set_at, admin_override)
                    VALUES (?, ?, ?, ?)
                ''', (discord_id, callsign, datetime.now(), 1 if admin_override else 0))

                # 새로운 콜사인 히스토리에 추가
                cursor.execute('''
                    INSERT INTO callsign_history (discord_id, callsign, set_at, admin_override)
                    VALUES (?, ?, ?, ?)
                ''', (discord_id, callsign, datetime.now(), 1 if admin_override else 0))

                print(f"✅ DB에 콜사인 저장 완료: {discord_id} -> {callsign}")

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            print(f"❌ DB 콜사인 저장 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('SELECT callsign FROM callsigns WHERE discord_id = ?', (discord_id,))
            result = cursor.fetchone()
            conn.close()

            return result['callsign'] if result else None

        except Exception as e:
            print(f"❌ DB 콜사인 조회 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('''
                SELECT callsign, set_at, admin_override
                FROM callsign_history
                WHERE discord_id = ?
                ORDER BY set_at DESC
            ''', (discord_id,))

            results = cursor.fetchall()
            conn.close()

            history = []
            for row in results:
                history.append({
                    'callsign': row['callsign'],
                    'set_at': row['set_at'],
                    'admin_override': bool(row['admin_override'])
                })

            return history

        except Exception as e:
            print(f"❌ 콜사인 히스토리 조회 실패: {e}")
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

            cursor.execute('DELETE FROM callsigns WHERE discord_id = ?', (discord_id,))

            conn.commit()
            conn.close()

            print(f"✅ DB에서 콜사인 삭제 완료: {discord_id}")
            return True

        except Exception as e:
            print(f"❌ DB 콜사인 삭제 실패: {e}")
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
            cursor = conn.cursor()

            # 기존 쿨타임 확인
            cursor.execute('SELECT discord_id FROM callsign_cooldowns WHERE discord_id = ?', (discord_id,))
            existing = cursor.fetchone()

            if existing:
                # 기존 쿨타임 업데이트
                cursor.execute('''
                    UPDATE callsign_cooldowns
                    SET cooldown_end = ?, set_at = ?
                    WHERE discord_id = ?
                ''', (cooldown_end, datetime.now(), discord_id))
            else:
                # 새로운 쿨타임 추가
                cursor.execute('''
                    INSERT INTO callsign_cooldowns (discord_id, cooldown_end, set_at)
                    VALUES (?, ?, ?)
                ''', (discord_id, cooldown_end, datetime.now()))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"❌ DB 쿨타임 저장 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('SELECT cooldown_end FROM callsign_cooldowns WHERE discord_id = ?', (discord_id,))
            result = cursor.fetchone()
            conn.close()

            if result:
                # 문자열을 datetime 객체로 변환
                cooldown_str = result['cooldown_end']
                return datetime.fromisoformat(cooldown_str) if isinstance(cooldown_str, str) else cooldown_str

            return None

        except Exception as e:
            print(f"❌ DB 쿨타임 조회 실패: {e}")
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

            cursor.execute('DELETE FROM callsign_cooldowns WHERE discord_id = ?', (discord_id,))

            conn.commit()
            conn.close()

            print(f"✅ DB에서 쿨타임 삭제 완료: {discord_id}")
            return True

        except Exception as e:
            print(f"❌ DB 쿨타임 삭제 실패: {e}")
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

            cursor.execute('DELETE FROM callsign_cooldowns')
            deleted_count = cursor.rowcount

            conn.commit()
            conn.close()

            print(f"✅ DB에서 모든 쿨타임 삭제 완료: {deleted_count}개")
            return deleted_count

        except Exception as e:
            print(f"❌ DB 모든 쿨타임 삭제 실패: {e}")
            return 0

    # ===== 모든 플레이어 정보 관리 (all_players 테이블) =====

    def upsert_all_players(self, players: List[Dict]) -> int:
        """
        Bulk API에서 가져온 모든 플레이어 정보를 DB에 저장/업데이트

        Args:
            players: 플레이어 정보 리스트 [{'uuid': ..., 'name': ..., 'nation': ..., 'town': ..., 'nationRanks': ..., 'townRanks': ...}]

        Returns:
            저장/업데이트된 레코드 수
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            saved_count = 0

            for player in players:
                uuid = player.get('uuid')
                name = player.get('name')
                nation = player.get('nation')
                town = player.get('town')
                nation_ranks = player.get('nationRanks', '')
                town_ranks = player.get('townRanks', '')

                if not uuid or not name:
                    continue

                # UPSERT (INSERT OR REPLACE)
                cursor.execute('''
                    INSERT OR REPLACE INTO all_players
                    (uuid, name, nation, town, nation_ranks, town_ranks, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (uuid, name, nation, town, nation_ranks, town_ranks, datetime.now()))

                saved_count += 1

            conn.commit()
            conn.close()

            return saved_count

        except Exception as e:
            print(f"❌ 모든 플레이어 정보 저장 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM all_players WHERE uuid = ?', (uuid,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row)
            return None

        except Exception as e:
            print(f"❌ 플레이어 UUID 조회 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM all_players WHERE name = ? COLLATE NOCASE', (name,))
            row = cursor.fetchone()

            conn.close()

            if row:
                return dict(row)
            return None

        except Exception as e:
            print(f"❌ 플레이어 이름 조회 실패: {e}")
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
            cursor = conn.cursor()

            if limit is None:
                cursor.execute('''
                    SELECT * FROM all_players
                    ORDER BY last_updated DESC
                ''')
            else:
                cursor.execute('''
                    SELECT * FROM all_players
                    ORDER BY last_updated DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"❌ 모든 플레이어 조회 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM all_players
                WHERE nation = ? COLLATE NOCASE
                ORDER BY name
            ''', (nation_name,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"❌ 국가별 플레이어 조회 실패: {e}")
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
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM all_players
                WHERE town = ? COLLATE NOCASE
                ORDER BY name
            ''', (town_name,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"❌ 마을별 플레이어 조회 실패: {e}")
            return []

    def get_total_players(self) -> int:
        """전체 플레이어 수 조회 (all_players 테이블)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) as count FROM all_players')
            result = cursor.fetchone()

            conn.close()

            return result['count'] if result else 0

        except Exception as e:
            print(f"❌ 플레이어 수 조회 실패: {e}")
            return 0


# 전역 데이터베이스 관리자 인스턴스
db_manager = DatabaseManager()
print("✅ DatabaseManager 인스턴스 생성됨")
