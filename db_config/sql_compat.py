# db_config/sql_compat.py - SQL 호환성 헬퍼 (PostgreSQL / SQLite)
#
# adapt_sql()로 자동 변환이 불가능한 복잡한 SQL 패턴을 위한 헬퍼 함수들

from db_config.db_adapter import DB_TYPE


def interval_ago(column: str, op: str = ">=") -> str:
    """
    타임스탬프 컬럼과 N일 전 비교 SQL 생성.

    PostgreSQL: column >= NOW() - INTERVAL '%s days'
    SQLite:     column >= datetime('now', '-' || ? || ' days')

    Args:
        column: 비교할 타임스탬프 컬럼명
        op: 비교 연산자 (>=, <, >, <= 등)
    """
    if DB_TYPE == "postgresql":
        return f"{column} {op} NOW() - INTERVAL '%s days'"
    else:
        return f"{column} {op} datetime('now', '-' || ? || ' days')"


def interval_set(days_placeholder: bool = True) -> str:
    """
    SET 절에서 N일 전 타임스탬프 값을 생성하는 SQL.

    PostgreSQL: NOW() - INTERVAL '%s days'
    SQLite:     datetime('now', '-' || ? || ' days')

    Args:
        days_placeholder: 파라미터로 일수를 받을지 여부
    """
    if DB_TYPE == "postgresql":
        return "NOW() - INTERVAL '%s days'"
    else:
        return "datetime('now', '-' || ? || ' days')"


def interval_fixed(duration: str) -> str:
    """
    고정된 기간으로 비교하는 SQL (예: '1 day').

    PostgreSQL: NOW() - INTERVAL '1 day'
    SQLite:     datetime('now', '-1 day')

    Args:
        duration: PostgreSQL INTERVAL 문자열 (예: '1 day', '7 days')
    """
    if DB_TYPE == "postgresql":
        return f"NOW() - INTERVAL '{duration}'"
    else:
        return f"datetime('now', '-{duration}')"


def on_conflict_constraint(constraint_name: str, columns: list, update_cols: list) -> str:
    """
    ON CONFLICT ... DO UPDATE SET 절 생성.

    PostgreSQL: ON CONFLICT ON CONSTRAINT name DO UPDATE SET ...
    SQLite:     ON CONFLICT (col1, col2) DO UPDATE SET ...

    Args:
        constraint_name: PostgreSQL constraint 이름
        columns: 충돌 대상 컬럼 리스트 (SQLite용)
        update_cols: 업데이트할 컬럼 리스트
    """
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    if DB_TYPE == "postgresql":
        return f"ON CONFLICT ON CONSTRAINT {constraint_name} DO UPDATE SET {set_clause}"
    else:
        col_list = ", ".join(columns)
        return f"ON CONFLICT ({col_list}) DO UPDATE SET {set_clause}"
