#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
백업 파일에서 누락된 콜사인만 복구하는 스크립트
"""

import sys
import io

# Windows 콘솔 인코딩 문제 해결
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from callsign_backup import CallsignBackupManager
import os

def main():
    # 백업 파일 경로
    backup_file = "data/callsign_backups/callsigns_backup_2025-08-25_17-00-00_auto.json"

    if not os.path.exists(backup_file):
        print(f"❌ 백업 파일을 찾을 수 없습니다: {backup_file}")
        return False

    print("=" * 70)
    print("📦 백업 파일에서 누락된 콜사인 복구")
    print("=" * 70)
    print(f"백업 파일: {backup_file}\n")

    # 백업 관리자 초기화
    backup_manager = CallsignBackupManager()

    # 선택적 복구 실행
    success, message, stats = backup_manager.restore_missing_only(backup_file)

    if success:
        print(f"\n✅ {message}\n")

        if stats.get("added", 0) > 0:
            print("📋 추가된 유저 목록:")
            print("-" * 70)
            for user_id, callsign_info in stats["added_users"].items():
                if isinstance(callsign_info, dict):
                    callsign = callsign_info.get("callsign", "알 수 없음")
                    set_at = callsign_info.get("set_at", "알 수 없음")
                else:
                    callsign = callsign_info
                    set_at = "알 수 없음"

                print(f"  • User ID: {user_id}")
                print(f"    콜사인: {callsign}")
                print(f"    설정 시간: {set_at}")
                print()
        else:
            print("ℹ️ 추가할 새로운 콜사인이 없습니다.")
    else:
        print(f"\n❌ {message}\n")
        return False

    print("=" * 70)
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
