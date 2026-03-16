# log_manager.py - 디스코드 봇 로그 관리 시스템 (PostgreSQL / SQLite)

import os
import json
import logging
import logging.handlers
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum
from collections import deque
from contextlib import contextmanager
from db_config.db_adapter import create_adapter


# ─── Python logging 설정 ───────────────────────────────────────────

def _setup_logging():
    """Python logging 모듈 초기화 (콘솔 + 파일)"""
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    root_logger = logging.getLogger("bot")
    root_logger.setLevel(log_level)

    # 이미 핸들러가 있으면 중복 방지
    if root_logger.handlers:
        return root_logger

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_fmt)
    root_logger.addHandler(console_handler)

    # 파일 핸들러 (RotatingFileHandler - 5MB x 5)
    log_dir = "data/logs"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "bot.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_fmt)
    root_logger.addHandler(file_handler)

    return root_logger


_setup_logging()

_logger = logging.getLogger("bot.log_manager")


def get_logger(name: str) -> logging.Logger:
    """
    자식 로거 반환. 각 파일에서 사용:
        from log_manager import get_logger
        logger = get_logger(__name__)
    """
    return logging.getLogger(f"bot.{name}")


# ─── 로그 레벨 / 카테고리 ──────────────────────────────────────────

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
    # 기존
    CALLSIGN = "콜사인"
    QUEUE = "대기열"
    ALLIANCE = "동맹"
    ROLE = "역할"
    EXCEPTION = "예외처리"
    SCHEDULER = "스케줄러"
    SYSTEM = "시스템"
    ADMIN = "관리자"
    # 신규
    QUEUE_ADD = "대기열추가"
    QUEUE_PROCESS = "대기열처리"
    RETURN = "복귀"
    WARNING_SYS = "경고"
    TRAVEL = "여행"
    ANNOUNCEMENT = "공지"
    COMMAND = "명령어"


# ─── LogManager ────────────────────────────────────────────────────

class LogManager:
    """로그 관리 클래스 (PostgreSQL / SQLite)"""

    def __init__(self):
        self.adapter = create_adapter(log=True)
        self.log_dir = "data/logs"

        # 메모리 내 최근 로그 (빠른 조회용)
        self.recent_logs = deque(maxlen=1000)

        # 데이터베이스 초기화
        self._init_database()

        # 메모리 캐시 초기화 (최근 1000개 로드)
        self._load_recent_logs()

        _logger.info("로그 관리자 초기화 완료: %s", self.adapter.get_db_label())

    def _init_database(self):
        """데이터베이스 및 테이블 초기화"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self.adapter.adapt_ddl('''
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
                        source TEXT,
                        action TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                '''))

                # 인덱스 생성 (조회 성능 향상)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON logs(timestamp DESC)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_level ON logs(level)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON logs(category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON logs(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_time ON logs(time)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON logs(source)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_action ON logs(action)')

                # 기존 테이블에 source/action 컬럼이 없을 수 있으므로 안전하게 추가
                self.adapter.add_column_safe(cursor, 'logs', 'source', 'TEXT')
                self.adapter.add_column_safe(cursor, 'logs', 'action', 'TEXT')

                conn.commit()

        except Exception as e:
            _logger.error("데이터베이스 초기화 실패: %s", e)

    @contextmanager
    def _get_db_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = self.adapter.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _get_cursor(self, conn):
        """커서 생성 (dict 결과를 반환하는 커서)"""
        return self.adapter.get_dict_cursor(conn)

    def _load_recent_logs(self):
        """최근 1000개 로그를 메모리에 로드"""
        try:
            with self._get_db_connection() as conn:
                cursor = self.adapter.get_dict_cursor(conn)
                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM logs
                    ORDER BY timestamp DESC
                    LIMIT 1000
                '''))

                rows = cursor.fetchall()

                # 최신 로그가 맨 뒤로 가도록 역순으로 추가
                for row in reversed(rows):
                    log_entry = self._row_to_dict(row)
                    self.recent_logs.append(log_entry)

        except Exception as e:
            _logger.error("최근 로그 로드 실패: %s", e)

    def _row_to_dict(self, row) -> Dict:
        """DB Row를 딕셔너리로 변환"""
        r = dict(row) if not isinstance(row, dict) else row
        return {
            "id": r.get("id"),
            "time": r.get("time"),
            "timestamp": r.get("timestamp"),
            "level": r.get("level"),
            "category": r.get("category"),
            "message": r.get("message"),
            "user_id": r.get("user_id"),
            "user_name": r.get("user_name"),
            "target_user_id": r.get("target_user_id"),
            "target_user_name": r.get("target_user_name"),
            "command": r.get("command"),
            "details": json.loads(r.get("details")) if r.get("details") else {},
            "source": r.get("source"),
            "action": r.get("action"),
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
        details: Optional[Dict] = None,
        source: Optional[str] = None,
        action: Optional[str] = None,
    ) -> bool:
        """
        로그 추가 (DB + 메모리 캐시 + Python logging)

        Args:
            level: 로그 레벨
            category: 로그 카테고리
            message: 로그 메시지
            user_id: 실행한 사용자 Discord ID (WHO)
            user_name: 실행한 사용자 이름
            target_user_id: 대상 사용자 ID
            target_user_name: 대상 사용자 이름
            command: 실행된 명령어
            details: 추가 상세 정보 (JSON)
            source: 로그 발생 위치 (admin_command, user_command, event_handler, scheduler, mf_handler, system)
            action: 정규화된 액션 (command_execute, queue_add, queue_requeue, role_assign 등)
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
                "details": details or {},
                "source": source,
                "action": action,
            }

            # 메모리에 추가
            self.recent_logs.append(log_entry)

            # Python logging에도 출력
            audit_logger = logging.getLogger("bot.audit")
            log_parts = [f"[{category.value}] {message}"]
            if user_name:
                log_parts.append(f"by={user_name}")
            if target_user_name:
                log_parts.append(f"target={target_user_name}")
            if source:
                log_parts.append(f"source={source}")
            if action:
                log_parts.append(f"action={action}")
            audit_logger.info(" | ".join(log_parts))

            # 데이터베이스에 저장
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self.adapter.adapt_sql('''
                    INSERT INTO logs
                    (time, timestamp, level, category, message, user_id, user_name,
                     target_user_id, target_user_name, command, details, source, action)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                '''), (
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
                    json.dumps(log_entry["details"], ensure_ascii=False),
                    log_entry["source"],
                    log_entry["action"],
                ))
                conn.commit()

            return True

        except Exception as e:
            _logger.error("로그 추가 실패: %s", e)
            return False

    def get_recent_logs(self, count: int = 50, category: Optional[LogCategory] = None) -> List[Dict]:
        """최근 로그 조회 (메모리 캐시 사용)"""
        logs = list(self.recent_logs)

        if category:
            logs = [log for log in logs if log['category'] == category.value]

        return logs[-count:]

    def get_logs_by_date(self, date: str, category: Optional[LogCategory] = None) -> List[Dict]:
        """특정 날짜의 로그 조회"""
        try:
            with self._get_db_connection() as conn:
                cursor = self.adapter.get_dict_cursor(conn)

                start_time = datetime.strptime(date, '%Y-%m-%d')
                end_time = start_time + timedelta(days=1)

                if category:
                    cursor.execute(self.adapter.adapt_sql('''
                        SELECT * FROM logs
                        WHERE time >= {ph} AND time < {ph} AND category = {ph}
                        ORDER BY timestamp ASC
                    '''), (start_time.strftime('%Y-%m-%d %H:%M:%S'),
                          end_time.strftime('%Y-%m-%d %H:%M:%S'),
                          category.value))
                else:
                    cursor.execute(self.adapter.adapt_sql('''
                        SELECT * FROM logs
                        WHERE time >= {ph} AND time < {ph}
                        ORDER BY timestamp ASC
                    '''), (start_time.strftime('%Y-%m-%d %H:%M:%S'),
                          end_time.strftime('%Y-%m-%d %H:%M:%S')))

                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            _logger.error("로그 조회 실패: %s", e)
            return []

    def get_user_logs(self, user_id: int, days: int = 7) -> List[Dict]:
        """특정 사용자의 로그 조회"""
        try:
            with self._get_db_connection() as conn:
                cursor = self.adapter.get_dict_cursor(conn)

                start_date = datetime.now() - timedelta(days=days)

                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM logs
                    WHERE (user_id = {ph} OR target_user_id = {ph})
                    AND timestamp >= {ph}
                    ORDER BY timestamp DESC
                '''), (user_id, user_id, start_date.timestamp()))

                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            _logger.error("사용자 로그 조회 실패: %s", e)
            return []

    def get_logs_by_filter(
        self,
        source: Optional[str] = None,
        action: Optional[str] = None,
        category: Optional[LogCategory] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict]:
        """source/action 필터로 로그 조회"""
        try:
            with self._get_db_connection() as conn:
                cursor = self.adapter.get_dict_cursor(conn)

                start_date = datetime.now() - timedelta(days=days)
                conditions = ["timestamp >= {ph}"]
                params = [start_date.timestamp()]

                if source:
                    conditions.append("source = {ph}")
                    params.append(source)
                if action:
                    conditions.append("action = {ph}")
                    params.append(action)
                if category:
                    conditions.append("category = {ph}")
                    params.append(category.value)

                where_clause = " AND ".join(conditions)
                query = f"SELECT * FROM logs WHERE {where_clause} ORDER BY timestamp DESC LIMIT {limit}"

                cursor.execute(self.adapter.adapt_sql(query), tuple(params))

                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            _logger.error("필터 로그 조회 실패: %s", e)
            return []

    def export_logs(self, start_date: str, end_date: str, format: str = 'json') -> Optional[str]:
        """로그 내보내기"""
        try:
            os.makedirs(self.log_dir, exist_ok=True)

            with self._get_db_connection() as conn:
                cursor = self.adapter.get_dict_cursor(conn)

                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)

                cursor.execute(self.adapter.adapt_sql('''
                    SELECT * FROM logs
                    WHERE time >= {ph} AND time < {ph}
                    ORDER BY timestamp ASC
                '''), (start.strftime('%Y-%m-%d %H:%M:%S'),
                      end.strftime('%Y-%m-%d %H:%M:%S')))

                rows = cursor.fetchall()
                all_logs = [self._row_to_dict(row) for row in rows]

            export_filename = f"logs_export_{start_date}_to_{end_date}.{format}"
            export_path = os.path.join(self.log_dir, export_filename)

            if format == 'json':
                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(all_logs, f, ensure_ascii=False, indent=2)
            elif format == 'csv':
                import csv
                with open(export_path, 'w', encoding='utf-8', newline='') as f:
                    if all_logs:
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
            _logger.error("로그 내보내기 실패: %s", e)
            return None

    def cleanup_old_logs(self, days: int = 30) -> int:
        """오래된 로그 정리"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()

                cutoff_date = datetime.now() - timedelta(days=days)
                cutoff_timestamp = cutoff_date.timestamp()

                cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) FROM logs WHERE timestamp < {ph}'), (cutoff_timestamp,))
                deleted_count = cursor.fetchone()[0]

                cursor.execute(self.adapter.adapt_sql('DELETE FROM logs WHERE timestamp < {ph}'), (cutoff_timestamp,))
                conn.commit()

                if deleted_count > 0:
                    _logger.info("오래된 로그 %d개 삭제됨", deleted_count)

                return deleted_count

        except Exception as e:
            _logger.error("로그 정리 실패: %s", e)
            return 0

    def get_statistics(self) -> Dict:
        """로그 통계 조회"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

            today_logs = self.get_logs_by_date(today)
            yesterday_logs = self.get_logs_by_date(yesterday)

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
            _logger.error("통계 조회 실패: %s", e)
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
                cursor.execute(self.adapter.adapt_sql('SELECT COUNT(*) FROM logs'))
                return cursor.fetchone()[0]
        except Exception as e:
            _logger.error("로그 개수 조회 실패: %s", e)
            return 0


# ─── BotLogger (편의 래퍼) ─────────────────────────────────────────

class BotLogger:
    """봇 로거 - 간편한 로깅을 위한 래퍼 클래스"""

    def __init__(self, log_manager: LogManager):
        self.log_manager = log_manager

    # ── 명령어 실행 로그 (신규) ──

    def log_command(
        self,
        command_name: str,
        user_id: int,
        user_name: str,
        source: str = "admin_command",
        category: LogCategory = LogCategory.COMMAND,
        target_user_id: int = None,
        target_user_name: str = None,
        details: Dict = None,
    ):
        """명령어 실행 로그 — 모든 슬래시 명령어에서 호출"""
        self.log_manager.add_log(
            LogLevel.INFO, category, f"/{command_name} 실행",
            user_id=user_id, user_name=user_name,
            target_user_id=target_user_id, target_user_name=target_user_name,
            command=command_name, details=details,
            source=source, action="command_execute",
        )

    # ── 기존 메서드 (source/action 파라미터 추가) ──

    def log_callsign(self, message: str, user_id: int = None, user_name: str = None,
                     source: str = None, action: str = None, **kwargs):
        """콜사인 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.CALLSIGN, message,
            user_id=user_id, user_name=user_name, source=source, action=action, **kwargs
        )

    def log_queue(self, message: str, user_id: int = None, user_name: str = None,
                  source: str = None, action: str = None, **kwargs):
        """대기열 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.QUEUE_ADD, message,
            user_id=user_id, user_name=user_name, source=source, action=action, **kwargs
        )

    def log_alliance(self, message: str, user_id: int = None, user_name: str = None,
                     source: str = None, action: str = None, **kwargs):
        """동맹 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.ALLIANCE, message,
            user_id=user_id, user_name=user_name, source=source, action=action, **kwargs
        )

    def log_role(self, message: str, user_id: int = None, user_name: str = None,
                 source: str = None, action: str = None, **kwargs):
        """역할 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.ROLE, message,
            user_id=user_id, user_name=user_name, source=source, action=action, **kwargs
        )

    def log_exception(self, message: str, user_id: int = None, user_name: str = None,
                      source: str = None, action: str = None, **kwargs):
        """예외 처리 관련 로그"""
        self.log_manager.add_log(
            LogLevel.INFO, LogCategory.EXCEPTION, message,
            user_id=user_id, user_name=user_name, source=source, action=action, **kwargs
        )

    def log_scheduler(self, message: str, source: str = "scheduler", action: str = None, **kwargs):
        """스케줄러 관련 로그"""
        self.log_manager.add_log(
            LogLevel.AUTO, LogCategory.SCHEDULER, message, source=source, action=action, **kwargs
        )

    def log_system_event(self, message: str, source: str = "system", action: str = None, **kwargs):
        """시스템 이벤트 로그"""
        self.log_manager.add_log(
            LogLevel.SYSTEM, LogCategory.SYSTEM, message, source=source, action=action, **kwargs
        )

    def log_admin_action(self, message: str, user_id: int = None, user_name: str = None,
                         source: str = "admin_command", action: str = None, **kwargs):
        """관리자 액션 로그"""
        self.log_manager.add_log(
            LogLevel.ADMIN, LogCategory.ADMIN, message,
            user_id=user_id, user_name=user_name, source=source, action=action, **kwargs
        )

    def log_error(self, message: str, source: str = None, action: str = None, **kwargs):
        """에러 로그"""
        self.log_manager.add_log(
            LogLevel.ERROR, LogCategory.SYSTEM, message, source=source, action=action, **kwargs
        )

    def log_warning(self, message: str, source: str = None, action: str = None, **kwargs):
        """경고 로그"""
        self.log_manager.add_log(
            LogLevel.WARNING, LogCategory.SYSTEM, message, source=source, action=action, **kwargs
        )


# ─── send_log_message (통합) ──────────────────────────────────────

async def send_log_message(
    bot,
    channel_id: int,
    embed,
    *,
    audit: bool = False,
    audit_level: LogLevel = LogLevel.INFO,
    audit_category: LogCategory = LogCategory.SYSTEM,
    audit_message: str = None,
    audit_user_id: int = None,
    audit_user_name: str = None,
    audit_target_user_id: int = None,
    audit_target_user_name: str = None,
    audit_source: str = None,
    audit_action: str = None,
    audit_details: dict = None,
):
    """
    Discord 채널에 로그 embed 전송 + (선택) DB 감사 로그 저장

    Args:
        bot: Discord 봇 인스턴스
        channel_id: 전송할 채널 ID
        embed: Discord Embed 객체
        audit: True면 DB에도 감사 로그 저장
        audit_*: DB 저장 시 사용할 필드들
    """
    try:
        if channel_id == 0:
            _logger.warning("채널 ID가 설정되지 않았습니다.")
            return

        channel = bot.get_channel(channel_id)
        if not channel:
            _logger.warning("채널을 찾을 수 없습니다: %d", channel_id)
            return

        await channel.send(embed=embed)
        _logger.debug("로그 메시지 전송됨: %s", channel.name)

    except Exception as e:
        _logger.error("로그 채널 전송 실패 (채널: %d): %s", channel_id, e)

    # DB 감사 로그 저장
    if audit:
        msg = audit_message or (embed.title if hasattr(embed, 'title') and embed.title else "Discord 로그 전송")
        log_manager.add_log(
            audit_level, audit_category, msg,
            user_id=audit_user_id, user_name=audit_user_name,
            target_user_id=audit_target_user_id, target_user_name=audit_target_user_name,
            details=audit_details, source=audit_source, action=audit_action,
        )


# ─── 전역 인스턴스 ────────────────────────────────────────────────

log_manager = LogManager()
bot_logger = BotLogger(log_manager)

_logger.info("로그 시스템 초기화 완료")
