# commands/admin/MF/mf_handler.py
# &MF 메시지 핸들러 - 채널 이름 변경 및 대기열 추가

import discord
import re
from datetime import datetime


async def message_handler(bot, message):
    """
    &MF 메시지 핸들러

    지원하는 형식:
    - &MF {대기열} 디스코드ID - 대기열에 추가
    - &MF 디스코드ID - 채널 이름 변경 (허용된 봇만)
    - &MF @유저멘션 - 채널 이름 변경 (허용된 봇만)
    """
    try:
        # &MF 명령어 확인 (메시지 내 모든 줄 검사)
        if '&MF' not in message.content:
            return False

        # 메시지에서 &MF 명령어가 있는 줄 찾기
        lines = message.content.split('\n')
        mf_line = None
        for line in lines:
            if line.strip().startswith('&MF'):
                mf_line = line.strip()
                break

        if not mf_line:
            return False

        # &MF 제거하고 나머지 텍스트 추출
        content = mf_line[3:].strip()

        print(f"🔍 &MF 명령어 감지! (봇: {message.author.name})")
        print(f"📝 원본 메시지: {message.content}")
        print(f"📝 처리된 내용: {content}")

        # {대기열} 키워드 확인
        is_queue_command = '{대기열}' in content or '{큐}' in content

        # 디스코드 ID 추출
        # 1. 유저 멘션 형태 (<@123456789> 또는 <@!123456789>)
        user_mention_match = re.search(r'<@!?(\d{15,20})>', content)
        if user_mention_match:
            discord_id = int(user_mention_match.group(1))
            print(f"✅ 유저 멘션에서 ID 추출: {discord_id}")
        else:
            # 2. 숫자만 있는 경우
            discord_id_match = re.search(r'(\d{15,20})', content)
            if not discord_id_match:
                await message.channel.send("디스코드 ID를 찾을 수 없습니다. 사용법: `&MF 디스코드ID` 또는 `&MF @유저멘션` 또는 `&MF {대기열} 디스코드ID`")
                return True
            discord_id = int(discord_id_match.group(1))
            print(f"✅ 숫자에서 ID 추출: {discord_id}")

        print(f"🎯 최종 Discord ID: {discord_id}")

        # {대기열} 명령어 처리 (모든 봇에서 동작)
        if is_queue_command:
            print(f"📋 대기열 추가 명령어 감지: {discord_id}")
            try:
                from queue_manager import queue_manager

                # 5초 이내 중복 요청 방지
                if not hasattr(bot, '_last_queue_request'):
                    bot._last_queue_request = {}

                current_time = datetime.now()
                last_request_time = bot._last_queue_request.get(discord_id)

                if last_request_time:
                    time_diff = (current_time - last_request_time).total_seconds()
                    if time_diff < 5:
                        print(f"⏱️ 5초 이내 중복 요청 무시: {discord_id} (경과: {time_diff:.1f}초)")
                        return True

                # 대기열에 추가
                if queue_manager.add_user(discord_id):
                    bot._last_queue_request[discord_id] = current_time
                    current_queue_size = queue_manager.get_queue_size()
                    await message.channel.send(
                        f"✅ 대기열에 추가되었습니다!\n"
                        f"Discord ID: `{discord_id}`\n"
                        f"현재 대기열: **{current_queue_size}명**\n"
                        f"대기열이 자동으로 처리됩니다."
                    )
                    print(f"✅ 대기열 추가 성공: {discord_id} (현재 {current_queue_size}명)")
                else:
                    await message.channel.send(
                        f"ℹ️ 이미 대기열에 있습니다.\n"
                        f"Discord ID: `{discord_id}`"
                    )
                    print(f"ℹ️ 이미 대기열에 있음: {discord_id}")
            except Exception as queue_error:
                await message.channel.send(f"❌ 대기열 추가 중 오류가 발생했습니다: {queue_error}")
                print(f"❌ 대기열 추가 오류: {queue_error}")
            return True  # 처리 완료

        # 허용된 봇 ID 목록 (채널 이름 변경 기능에만 적용)
        ALLOWED_BOT_IDS = [557628352828014614, 1325579039888511056]

        # 허용된 봇이 아니면 무시
        if message.author.id not in ALLOWED_BOT_IDS:
            return False

        # database_manager 로드
        try:
            from database_manager import db_manager
        except ImportError:
            await message.channel.send("데이터베이스 모듈을 로드할 수 없습니다.")
            print("❌ database_manager 로드 실패")
            return True

        # DB에서 유저 정보 조회
        user_info = db_manager.get_user_info(discord_id)

        if not user_info:
            await message.channel.send(f"디스코드 ID `{discord_id}`에 해당하는 사용자를 찾을 수 없습니다.")
            print(f"❌ DB에서 사용자 정보 없음: {discord_id}")
            return True

        minecraft_name = user_info.get('current_minecraft_name')

        if not minecraft_name:
            await message.channel.send(f"사용자 `{discord_id}`의 마인크래프트 닉네임이 등록되지 않았습니다.")
            print(f"❌ 마인크래프트 닉네임 없음: {discord_id}")
            return True

        # 국가 정보 조회
        nation_info = db_manager.get_current_nation(discord_id)

        if not nation_info or not nation_info.get('nation_name'):
            await message.channel.send(f"사용자 `{minecraft_name}`의 국가 정보를 찾을 수 없습니다.")
            print(f"❌ 국가 정보 없음: {discord_id} ({minecraft_name})")
            return True

        nation_name = nation_info['nation_name']

        # 국가 이름을 특수 대문자로 변환 (Mathematical Bold Sans-Serif)
        def convert_to_bold_sans_serif(text):
            # 일반 알파벳 대문자 -> Mathematical Bold Sans-Serif
            normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            bold_sans = "𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹"

            result = []
            for char in text.upper():
                if char in normal:
                    idx = normal.index(char)
                    result.append(bold_sans[idx])
                else:
                    result.append(char)
            return ''.join(result)

        nation_name_styled = convert_to_bold_sans_serif(nation_name)
        new_channel_name = f"{nation_name_styled} 대사관"

        # nationRanks, townRanks 정보 가져오기
        nation_ranks = nation_info.get('nation_ranks', '정보 없음')
        town_ranks = nation_info.get('town_ranks', '정보 없음')

        # 현재 채널 이름 변경
        try:
            old_name = message.channel.name
            await message.channel.edit(name=new_channel_name)

            # 직위 정보 구성
            rank_info = []
            if nation_ranks and nation_ranks != '정보 없음':
                rank_info.append(f"국가 계급: `{nation_ranks}`")
            if town_ranks and town_ranks != '정보 없음':
                rank_info.append(f"마을 계급: `{town_ranks}`")

            rank_display = "\n".join(rank_info) if rank_info else "직위: `정보 없음`"

            await message.channel.send(
                f"✅ 채널 이름이 변경되었습니다!\n"
                f"사용자: `{minecraft_name}` (Discord ID: `{discord_id}`)\n"
                f"국가: `{nation_name}`\n"
                f"{rank_display}\n"
                f"변경: `{old_name}` → `{new_channel_name}`"
            )
            print(f"✅ 채널 이름 변경 성공: {old_name} -> {new_channel_name} (국가 계급: {nation_ranks}, 마을 계급: {town_ranks})")
        except discord.Forbidden:
            await message.channel.send("❌ 채널 이름을 변경할 권한이 없습니다.")
            print(f"❌ 채널 이름 변경 권한 없음: {message.channel.name}")
        except Exception as e:
            await message.channel.send(f"❌ 채널 이름 변경 중 오류가 발생했습니다: {e}")
            print(f"❌ 채널 이름 변경 오류: {e}")
            import traceback
            traceback.print_exc()

        return True  # 처리 완료

    except Exception as e:
        print(f"❌ &MF 메시지 핸들러 오류: {e}")
        import traceback
        traceback.print_exc()
        return False
