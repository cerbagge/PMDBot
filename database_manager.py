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
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id)
            )
        ''')

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
                           town_name: str = None, town_uuid: str = None) -> bool:
        """
        국가/마을 히스토리 추가

        Args:
            discord_id: 디스코드 사용자 ID
            nation_name: 국가 이름
            nation_uuid: 국가 UUID
            town_name: 마을 이름
            town_uuid: 마을 UUID

        Returns:
            성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # 가장 최근 국가 히스토리 조회
            cursor.execute('''
                SELECT nation_name, nation_uuid, town_name, town_uuid
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
                    last_record['town_uuid'] == town_uuid):
                    # 변경사항 없음
                    conn.close()
                    return True

            # 새 히스토리 추가
            cursor.execute('''
                INSERT INTO nation_history (discord_id, nation_name, nation_uuid, town_name, town_uuid)
                VALUES (?, ?, ?, ?, ?)
            ''', (discord_id, nation_name, nation_uuid, town_name, town_uuid))

            conn.commit()
            conn.close()

            print(f"📝 국가 히스토리 추가: {discord_id} - {nation_name}/{town_name}")
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


# 전역 데이터베이스 관리자 인스턴스
db_manager = DatabaseManager()
print("✅ DatabaseManager 인스턴스 생성됨")
