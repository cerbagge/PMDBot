#!/usr/bin/env python
# mfcommands.py - MF 명령어 봇 관리 CLI

import sys
import mf_config


def print_usage():
    print("MF Commands - 허용된 봇 관리")
    print("")
    print("사용법:")
    print("  mfcommands -add <봇ID>      봇 추가")
    print("  mfcommands -remove <봇ID>   봇 제거")
    print("  mfcommands -list            허용된 봇 목록")
    print("")
    print("예시:")
    print("  mfcommands -add 123456789012345678")


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1].lower()

    if command == "-add":
        if len(sys.argv) < 3:
            print("오류: 봇 ID를 입력해주세요.")
            print("사용법: mfcommands -add <봇ID>")
            return

        try:
            bot_id = int(sys.argv[2])
        except ValueError:
            print("오류: 봇 ID는 숫자여야 합니다.")
            return

        if mf_config.is_allowed_bot(bot_id):
            print(f"이미 허용된 봇입니다: {bot_id}")
        elif mf_config.add_bot_id(bot_id):
            print(f"봇이 추가되었습니다: {bot_id}")
        else:
            print(f"봇 추가 실패: {bot_id}")

    elif command == "-remove":
        if len(sys.argv) < 3:
            print("오류: 봇 ID를 입력해주세요.")
            print("사용법: mfcommands -remove <봇ID>")
            return

        try:
            bot_id = int(sys.argv[2])
        except ValueError:
            print("오류: 봇 ID는 숫자여야 합니다.")
            return

        if not mf_config.is_allowed_bot(bot_id):
            print(f"허용 목록에 없는 봇입니다: {bot_id}")
        elif mf_config.remove_bot_id(bot_id):
            print(f"봇이 제거되었습니다: {bot_id}")
        else:
            print(f"봇 제거 실패: {bot_id}")

    elif command == "-list":
        bot_ids = mf_config.get_allowed_bot_ids()
        if bot_ids:
            print("허용된 봇 목록:")
            for bot_id in bot_ids:
                print(f"  - {bot_id}")
        else:
            print("허용된 봇이 없습니다.")

    else:
        print(f"알 수 없는 명령어: {command}")
        print_usage()


if __name__ == "__main__":
    main()
