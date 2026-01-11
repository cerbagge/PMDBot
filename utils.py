# utils.py - 개선된 버전
import datetime

def log_message(msg: str):
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def format_duration(seconds: int) -> str:
    """
    초 단위 시간을 시:분:초 형식으로 변환하는 함수
    
    Args:
        seconds (int): 초 단위 시간
        
    Returns:
        str: "X시간 Y분 Z초" 또는 "Y분 Z초" 또는 "Z초" 형식의 문자열
    """
    if seconds <= 0:
        return "즉시"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    
    parts = []
    
    if hours > 0:
        parts.append(f"{hours}시간")
    if minutes > 0:
        parts.append(f"{minutes}분")
    if remaining_seconds > 0 or not parts:  # 초가 있거나 다른 단위가 없으면 초 표시
        parts.append(f"{remaining_seconds}초")
    
    return " ".join(parts)

def format_estimated_time(queue_size: int, seconds_per_item: int = 20, use_bulk_optimization: bool = True) -> str:
    """
    대기열 크기와 아이템당 처리 시간을 바탕으로 예상 완료 시간을 계산

    Args:
        queue_size (int): 대기열 크기
        seconds_per_item (int): 아이템당 예상 처리 시간 (기본값: 20초, Bulk 미사용 시)
        use_bulk_optimization (bool): Bulk 최적화 여부 (기본값: True)

    Returns:
        str: 포맷된 예상 시간 문자열
    """
    if queue_size <= 0:
        return "대기열이 비어있습니다"

    # Bulk 최적화 활성화 시 예상 시간 단축
    if use_bulk_optimization:
        try:
            from bulk_updater import bulk_data_manager

            # Bulk 데이터가 사용 가능한지 확인
            if bulk_data_manager.is_data_available():
                # Bulk 데이터 사용 시: 대부분 DB 유저 = 5초/명, 신규 유저 = 15초/명
                # 평균적으로 80% DB 유저, 20% 신규 유저로 가정
                # 평균 시간 = 0.8 * 5초 + 0.2 * 15초 = 4초 + 3초 = 7초
                seconds_per_item = 7
            else:
                # Bulk 데이터 없으면 기존 방식 사용
                seconds_per_item = 20
        except:
            # bulk_updater를 불러올 수 없으면 기존 방식 사용
            seconds_per_item = 20

    total_seconds = queue_size * seconds_per_item
    return f"약 {format_duration(total_seconds)}"

def format_time_until(target_datetime: datetime.datetime) -> str:
    """
    특정 시간까지 남은 시간을 계산하여 포맷
    
    Args:
        target_datetime (datetime.datetime): 목표 시간
        
    Returns:
        str: 남은 시간 문자열
    """
    now = datetime.datetime.now()
    if target_datetime <= now:
        return "시간 초과"
    
    diff = target_datetime - now
    total_seconds = int(diff.total_seconds())
    
    return format_duration(total_seconds)

# 테스트용 함수
def test_format_duration():
    """format_duration 함수 테스트"""
    test_cases = [
        (0, "즉시"),
        (30, "30초"),
        (60, "1분"),
        (90, "1분 30초"),
        (3600, "1시간"),
        (3661, "1시간 1분 1초"),
        (7200, "2시간"),
        (7320, "2시간 2분"),
        (7323, "2시간 2분 3초"),
        (86400, "24시간"),
        (90061, "25시간 1분 1초")
    ]
    
    print("🧪 format_duration 테스트:")
    for seconds, expected in test_cases:
        result = format_duration(seconds)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {seconds}초 → '{result}' (예상: '{expected}')")

if __name__ == "__main__":
    test_format_duration()