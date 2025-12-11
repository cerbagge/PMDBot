# log_manager.py - 디스코드 봇 로그 관리 시스템 (SQLite)

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum
from collections import deque
from contextlib import contextmanager

class LogLevel(Enum):
    """로그 레벨"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    ADMIN = "ADMIN"
    AUTO = "AUTO"
    SYSTEM = "SYSTEM"

class LogCategory(Enum):
    """로그 카테고리"""
    CALLSIGN = "콜사인"
    QUEUE = "대기열"
    ALLIANCE = "동맹"
    ROLE = "역할"
    EXCEPTION = "예외처리"
    SCHEDULER = "스케줄러"
    SYSTEM = "시스템"
    ADMIN = "관리자"

class LogManager:
    """로그 관리 클래스 (SQLite)"""

    def __init__(self, log_dir: str = "data/logs"):
        """
        로그 관리자 초기화

        Args:
            log_dir: 로그 파일 저장 디렉토리
        """
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        # SQLite 데이터베이스 경로
        self.db_path = os.path.join(self.log_dir, "bot_logs.db")

        # 메모리 내 최근 로그 (빠른 조회용)
        self.recent_logs = deque(maxlen=1000)

        # 데이터베이스 초기화
        self._init_database()

        # 메모리 캐시 초기화 (최근 1000개 로드)
        self._load_recent_logs()

        try:
            print(f"✅ 로그 관리자 초기화 완료: {self.db_path}")
        except UnicodeEncodeError:
            print(f"[OK] Log Manager Initialized: {self.db_path}")

    def _init_database(self):
        """데이터베이스 및 테이블 초기화"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
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
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 인덱스 생성 (조회 성능 향상)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON logs(timestamp DESC)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_level ON logs(level)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON logs(category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON logs(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_time ON logs(time)')

                conn.commit()

        except Exception as e:
            try:
                print(f"❌ 데이터베이스 초기화 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to initialize database: {e}")

    @contextmanager
    def _get_db_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 딕셔너리 형태로 결과 반환
        try:
            yield conn
        finally:
            conn.close()

    def _load_recent_logs(self):
        """최근 1000개 로그를 메모리에 로드"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM logs
                    ORDER BY timestamp DESC
                    LIMIT 1000
                ''')

                rows = cursor.fetchall()

                # 최신 로그가 맨 뒤로 가도록 역순으로 추가
                for row in reversed(rows):
                    log_entry = self._row_to_dict(row)
                    self.recent_logs.append(log_entry)

        except Exception as e:
            try:
                print(f"❌ 최근 로그 로드 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to load recent logs: {e}")

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """SQLite Row를 딕셔너리로 변환"""
        return {
            "id": row["id"],
            "time": row["time"],
            "timestamp": row["timestamp"],
            "level": row["level"],
            "category": row["category"],
            "message": row["message"],
            "user_id": row["user_id"],
            "user_name": row["user_name"],
            "target_user_id": row["target_user_id"],
            "target_user_name": row["target_user_name"],
            "command": row["command"],
            "details": json.loads(row["details"]) if row["details"] else {}
        }

    def add_log(
        self,
        level: LogLevel,
        category: LogCategory,
        message: str,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        target_user_id: Optional[int] = None,
        target_user_name: Optional[str] = None,
        command: Optional[str] = None,
        details: Optional[Dict] = None
    ) -> bool:
        """
        로그 추가

        Args:
            level: 로그 레벨
            category: 로그 카테고리
            message: 로그 메시지
            user_id: 사용자 Discord ID
            user_name: 사용자 이름
            target_user_id: 대상 사용자 ID (있는 경우)
            target_user_name: 대상 사용자 이름 (있는 경우)
            command: 실행된 명령어
            details: 추가 상세 정보

        Returns:
            성공 여부
        """
        try:
            now = datetime.now()

            log_entry = {
                "time": now.strftime('%Y-%m-%d %H:%M:%S'),
                "timestamp": now.timestamp(),
                "level": level.value,
                "category": category.value,
                "message": message,
                "user_id": user_id,
                "user_name": user_name,
                "target_user_id": target_user_id,
                "target_user_name": target_user_name,
                "command": command,
                "details": details or {}
            }

            # 메모리에 추가
            self.recent_logs.append(log_entry)

            # 데이터베이스에 저장
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO logs
                    (time, timestamp, level, category, message, user_id, user_name,
                     target_user_id, target_user_name, command, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    log_entry["time"],
                    log_entry["timestamp"],
                    log_entry["level"],
                    log_entry["category"],
                    log_entry["message"],
                    log_entry["user_id"],
                    log_entry["user_name"],
                    log_entry["target_user_id"],
                    log_entry["target_user_name"],
                    log_entry["command"],
                    json.dumps(log_entry["details"], ensure_ascii=False)
                ))
                conn.commit()

            return True

        except Exception as e:
            try:
                print(f"❌ 로그 추가 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to add log: {e}")
            return False

    def get_recent_logs(self, count: int = 50, category: Optional[LogCategory] = None) -> List[Dict]:
        """
        최근 로그 조회 (메모리 캐시 사용)

        Args:
            count: 조회할 로그 개수
            category: 필터링할 카테고리

        Returns:
            로그 리스트
        """
        logs = list(self.recent_logs)

        if category:
            logs = [log for log in logs if log['category'] == category.value]

        return logs[-count:]

    def get_logs_by_date(self, date: str, category: Optional[LogCategory] = None) -> List[Dict]:
        """
        특정 날짜의 로그 조회

        Args:
            date: 날짜 (YYYY-MM-DD)
            category: 필터링할 카테고리

        Returns:
            로그 리스트
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # 날짜 범위 계산
                start_time = datetime.strptime(date, '%Y-%m-%d')
                end_time = start_time + timedelta(days=1)

                if category:
                    cursor.execute('''
                        SELECT * FROM logs
                        WHERE time >= ? AND time < ? AND category = ?
                        ORDER BY timestamp ASC
                    ''', (start_time.strftime('%Y-%m-%d %H:%M:%S'),
                          end_time.strftime('%Y-%m-%d %H:%M:%S'),
                          category.value))
                else:
                    cursor.execute('''
                        SELECT * FROM logs
                        WHERE time >= ? AND time < ?
                        ORDER BY timestamp ASC
                    ''', (start_time.strftime('%Y-%m-%d %H:%M:%S'),
                          end_time.strftime('%Y-%m-%d %H:%M:%S')))

                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            try:
                print(f"❌ 로그 조회 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to get logs: {e}")
            return []

    def get_user_logs(self, user_id: int, days: int = 7) -> List[Dict]:
        """
        특정 사용자의 로그 조회

        Args:
            user_id: 사용자 Discord ID
            days: 조회할 일수

        Returns:
            로그 리스트
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # 날짜 범위 계산
                start_date = datetime.now() - timedelta(days=days)

                cursor.execute('''
                    SELECT * FROM logs
                    WHERE (user_id = ? OR target_user_id = ?)
                    AND timestamp >= ?
                    ORDER BY timestamp DESC
                ''', (user_id, user_id, start_date.timestamp()))

                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            try:
                print(f"❌ 사용자 로그 조회 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to get user logs: {e}")
            return []

    def export_logs(self, start_date: str, end_date: str, format: str = 'json') -> Optional[str]:
        """
        로그 내보내기

        Args:
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            format: 내보내기 형식 ('json' 또는 'csv')

        Returns:
            내보내기 파일 경로
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # 날짜 범위 계산
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)

                cursor.execute('''
                    SELECT * FROM logs
                    WHERE time >= ? AND time < ?
                    ORDER BY timestamp ASC
                ''', (start.strftime('%Y-%m-%d %H:%M:%S'),
                      end.strftime('%Y-%m-%d %H:%M:%S')))

                rows = cursor.fetchall()
                all_logs = [self._row_to_dict(row) for row in rows]

            # 내보내기 파일명
            export_filename = f"logs_export_{start_date}_to_{end_date}.{format}"
            export_path = os.path.join(self.log_dir, export_filename)

            if format == 'json':
                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(all_logs, f, ensure_ascii=False, indent=2)
            elif format == 'csv':
                import csv
                with open(export_path, 'w', encoding='utf-8', newline='') as f:
                    if all_logs:
                        # details 필드는 JSON 문자열로 변환
                        csv_logs = []
                        for log in all_logs:
                            csv_log = log.copy()
                            csv_log['details'] = json.dumps(csv_log['details'], ensure_ascii=False)
                            csv_logs.append(csv_log)

                        writer = csv.DictWriter(f, fieldnames=csv_logs[0].keys())
                        writer.writeheader()
                        writer.writerows(csv_logs)

            return export_path

        except Exception as e:
            try:
                print(f"❌ 로그 내보내기 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to export logs: {e}")
            return None

    def cleanup_old_logs(self, days: int = 30) -> int:
        """
        오래된 로그 정리

        Args:
            days: 보관 기간 (일)

        Returns:
            삭제된 로그 개수
        """
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                # 날짜 계산
                cutoff_date = datetime.now() - timedelta(days=days)
                cutoff_timestamp = cutoff_date.timestamp()

                # 삭제할 로그 수 조회
                cursor.execute('SELECT COUNT(*) FROM logs WHERE timestamp < ?', (cutoff_timestamp,))
                deleted_count = cursor.fetchone()[0]

                # 오래된 로그 삭제
                cursor.execute('DELETE FROM logs WHERE timestamp < ?', (cutoff_timestamp,))
                conn.commit()

                # VACUUM으로 데이터베이스 최적화
                cursor.execute('VACUUM')

                if deleted_count > 0:
                    try:
                        print(f"🗑️ 오래된 로그 {deleted_count}개 삭제됨")
                    except UnicodeEncodeError:
                        print(f"[DELETE] Removed {deleted_count} old logs")

                return deleted_count

        except Exception as e:
            try:
                print(f"❌ 로그 정리 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to cleanup logs: {e}")
            return 0

    def get_statistics(self) -> Dict:
        """
        로그 통계 조회

        Returns:
            통계 정보 딕셔너리
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

            today_logs = self.get_logs_by_date(today)
            yesterday_logs = self.get_logs_by_date(yesterday)

            # 카테고리별 통계
            category_stats = {}
            for log in today_logs:
                category = log['category']
                category_stats[category] = category_stats.get(category, 0) + 1

            return {
                'today_count': len(today_logs),
                'yesterday_count': len(yesterday_logs),
                'memory_count': len(self.recent_logs),
                'category_stats': category_stats
            }

        except Exception as e:
            try:
                print(f"❌ 통계 조회 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to get statistics: {e}")
            return {
                'today_count': 0,
                'yesterday_count': 0,
                'memory_count': len(self.recent_logs),
                'category_stats': {}
            }

    def get_total_log_count(self) -> int:
        """전체 로그 개수 조회"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM logs')
                return cursor.fetchone()[0]
        except Exception as e:
            try:
                print(f"❌ 로그 개수 조회 실패: {e}")
            except UnicodeEncodeError:
                print(f"[ERROR] Failed to get log count: {e}")
            return 0


class BotLogger:
    """봇 로거 - 간편한 로깅을 위한 래퍼 클래스"""

    def __init__(self, log_manager: LogManager):
        self.log_manager = log_manager

    def log_callsign(self, message: str, user_id: int = None, user_name: str = None, **kwargs):
        """콜사인 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.CALLSIGN, message,
            user_id=user_id, user_name=user_name, **kwargs
        )

    def log_queue(self, message: str, user_id: int = None, user_name: str = None, **kwargs):
        """대기열 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.QUEUE, message,
            user_id=user_id, user_name=user_name, **kwargs
        )

    def log_alliance(self, message: str, user_id: int = None, user_name: str = None, **kwargs):
        """동맹 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.ALLIANCE, message,
            user_id=user_id, user_name=user_name, **kwargs
        )

    def log_role(self, message: str, user_id: int = None, user_name: str = None, **kwargs):
        """역할 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.ROLE, message,
            user_id=user_id, user_name=user_name, **kwargs
        )

    def log_exception(self, message: str, user_id: int = None, user_name: str = None, **kwargs):
        """예외 처리 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.EXCEPTION, message,
            user_id=user_id, user_name=user_name, **kwargs
        )

    def log_scheduler(self, message: str, **kwargs):
        """스케줄러 관련 로그"""
        self.log_manager.add_log(
            LogLevel.AUTO, LogCategory.SCHEDULER, message, **kwargs
        )

    def log_system_event(self, message: str, **kwargs):
        """시스템 이벤트 로그"""
        self.log_manager.add_log(
            LogLevel.SYSTEM, LogCategory.SYSTEM, message, **kwargs
        )

    def log_admin_action(self, message: str, user_id: int = None, user_name: str = None, **kwargs):
        """관리자 액션 로그"""
        self.log_manager.add_log(
            LogLevel.ADMIN, LogCategory.ADMIN, message,
            user_id=user_id, user_name=user_name, **kwargs
        )

    def log_error(self, message: str, **kwargs):
        """에러 로그"""
        self.log_manager.add_log(
            LogLevel.ERROR, LogCategory.SYSTEM, message, **kwargs
        )

    def log_warning(self, message: str, **kwargs):
        """경고 로그"""
        self.log_manager.add_log(
            LogLevel.WARNING, LogCategory.SYSTEM, message, **kwargs
        )


# 전역 인스턴스
log_manager = LogManager()
bot_logger = BotLogger(log_manager)

try:
    print("✅ 로그 시스템 초기화 완료 (SQLite)")
except UnicodeEncodeError:
    print("[OK] Log System Initialized (SQLite)")
