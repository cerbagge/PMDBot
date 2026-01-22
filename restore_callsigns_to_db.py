#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
백업 파일에서 콜사인을 DB에 복구하는 스크립트
이미 DB에 있는 유저는 건너뜁니다.
"""

import sys
import io
import json
import os

# Windows 콘솔 인코딩 문제 해결
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from database_manager import DatabaseManager

def restore_callsigns_to_db(backup_file: str):
    """
    백업 파일에서 DB로 콜사인 복구

    Args:
        backup_file: 백업 파일 경로
    """
    if not os.path.exists(backup_file):
        print(f"❌ 백업 파일을 찾을 수 없습니다: {backup_file}")
        return False

    print("=" * 70)
    print("📦 백업 파일에서 DB로 콜사인 복구")
    print("=" * 70)
    print(f"백업 파일: {backup_file}\n")

    try:
        # 백업 파일 읽기
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        # 메타데이터가 있는 새 형식인지 확인
        if "metadata" in backup_data and "data" in backup_data:
            backup_callsigns = backup_data["data"]
            print(f"📊 백업 메타데이터:")
            print(f"   - 백업 시간: {backup_data['metadata'].get('backup_time', 'Unknown')}")
            print(f"   - 총 콜사인: {backup_data['metadata'].get('total_callsigns', 'Unknown')}개\n")
        else:
            # 구 형식 백업 파일
            backup_callsigns = backup_data
            print(f"📊 구 형식 백업 파일 감지\n")

        # DB 매니저 초기화
        db_manager = DatabaseManager()

        # 메타데이터 필드 무시
        metadata_fields = {"count", "description", "metadata"}

        # 통계
        added_count = 0
        skipped_count = 0
        error_count = 0

        print("🔄 콜사인 복구 시작...\n")

        for user_id_str, callsign_info in backup_callsigns.items():
            # 메타데이터 필드는 스킵
            if user_id_str in metadata_fields:
                continue

            # Discord User ID는 숫자로만 구성되어야 함
            if not user_id_str.isdigit():
                print(f"⚠️ 잘못된 User ID 형식 건너뜀: {user_id_str}")
                continue

            try:
                user_id = int(user_id_str)

                # 콜사인 정보 추출
                if isinstance(callsign_info, dict):
                    callsign = callsign_info.get("callsign", "")
                    admin_override = callsign_info.get("admin_override", False)
                else:
                    # 구 형식: 문자열로만 저장된 경우
                    callsign = callsign_info
                    admin_override = False

                if not callsign:
                    print(f"⚠️ 콜사인이 비어있음: User ID {user_id}")
                    continue

                # DB에 이미 콜사인이 있는지 확인
                existing_callsign = db_manager.get_callsign(user_id)

                if existing_callsign:
                    # 이미 DB에 있으면 스킵
                    skipped_count += 1
                    print(f"  ⏭️  User ID {user_id}: 이미 존재함 (현재: '{existing_callsign}', 백업: '{callsign}')")
                else:
                    # DB에 없으면 추가
                    success = db_manager.set_callsign(user_id, callsign, admin_override)
                    if success:
                        added_count += 1
                        print(f"  ✅ User ID {user_id}: '{callsign}' 추가됨")
                    else:
                        error_count += 1
                        print(f"  ❌ User ID {user_id}: 추가 실패")

            except Exception as e:
                error_count += 1
                print(f"  ❌ User ID {user_id_str}: 오류 발생 - {e}")

        # 결과 출력
        print("\n" + "=" * 70)
        print("📊 복구 완료")
        print("=" * 70)
        print(f"✅ 새로 추가됨: {added_count}개")
        print(f"⏭️  이미 존재함 (스킵): {skipped_count}개")
        print(f"❌ 오류 발생: {error_count}개")
        print(f"📦 백업 총 콜사인: {len(backup_callsigns)}개")
        print("=" * 70)

        return error_count == 0

    except Exception as e:
        print(f"\n❌ 복구 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    # 백업 파일 경로
    backup_file = "data/callsign_backups/callsigns_backup_2025-12-22_17-00-00_auto.json"

    success = restore_callsigns_to_db(backup_file)
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
