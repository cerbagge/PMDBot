# cli_newbie_adjust.py - 뉴비 가입일 조정 터미널 명령어
# 사용법: noob -day / <디스코드ID> / YYYY.MM.DD

import sys
from datetime import datetime

def print_usage():
    print("사용법: noob -day / <디스코드ID> / YYYY.MM.DD")
    print("예시: noob -day / 123456789012345678 / 2025.01.15")

def main():
    # 인자 확인 (noob -day / id / date)
    if len(sys.argv) < 5:
        print_usage()
        sys.exit(1)

    # 인자 파싱: noob -day / id / date
    if sys.argv[1] != "-day" or sys.argv[2] != "/" or sys.argv[4] != "/":
        print_usage()
        sys.exit(1)

    discord_id_str = sys.argv[3]
    date_str = sys.argv[5] if len(sys.argv) > 5 else ""

    # 디스코드 ID 파싱
    try:
        discord_id = int(discord_id_str)
    except ValueError:
        print(f"❌ 잘못된 디스코드 ID: {discord_id_str}")
        print("   디스코드 ID는 숫자여야 합니다.")
        sys.exit(1)

    # 날짜 파싱
    try:
        new_joined_at = datetime.strptime(date_str, "%Y.%m.%d")
    except ValueError:
        print(f"❌ 잘못된 날짜 형식: {date_str}")
        print("   형식: YYYY.MM.DD (예: 2025.01.15)")
        sys.exit(1)

    # 데이터베이스 연결
    try:
        from database_manager import db_manager
    except Exception as e:
        print(f"❌ 데이터베이스 연결 실패: {e}")
        sys.exit(1)

    # 사용자 정보 확인
    user_info = db_manager.get_user_info(discord_id)
    if not user_info:
        print(f"❌ 디스코드 ID {discord_id}는 데이터베이스에 없습니다.")
        sys.exit(1)

    # 기존 가입일 확인
    old_joined_at = db_manager.get_red_mafia_joined(discord_id)
    old_joined_str = old_joined_at.strftime('%Y.%m.%d %H:%M:%S') if old_joined_at else "미설정"

    # 사용자 정보 출력
    mc_name = user_info.get('current_minecraft_name', '알 수 없음')
    nation = user_info.get('current_nation', '없음')

    print(f"\n{'='*50}")
    print(f"👤 대상: {discord_id}")
    print(f"🎮 마인크래프트: {mc_name}")
    print(f"🏛️ 현재 국가: {nation}")
    print(f"📅 이전 가입일: {old_joined_str}")
    print(f"📅 새 가입일: {new_joined_at.strftime('%Y.%m.%d %H:%M:%S')}")
    print(f"{'='*50}")

    # 가입일 업데이트
    success = db_manager.set_red_mafia_joined(discord_id, new_joined_at)

    if success:
        # 남은 뉴비 기간 계산
        days_since = (datetime.now() - new_joined_at).days
        days_left = 14 - days_since

        if days_left > 0:
            status = f"D-{days_left} (뉴비)"
        else:
            status = f"뉴비 기간 만료 ({abs(days_left)}일 초과)"

        print(f"✅ 가입일 조정 완료!")
        print(f"📊 뉴비 상태: {status}")
    else:
        print("❌ 가입일 조정 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
