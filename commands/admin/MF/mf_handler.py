# commands/admin/MF/mf_handler.py
# &MF 메시지 핸들러 - 채널 이름 변경 및 대기열 추가

import discord
import re
import aiohttp
from datetime import datetime
from log_manager import get_logger

logger = get_logger("mf_handler")

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


# 국가 이름을 특수 대문자로 변환 (Mathematical Bold Sans-Serif)
def convert_to_bold_sans_serif(text):
    """영어 대문자를 특수 폰트로 변환"""
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


async def message_handler(bot, message):
    """
    &MF 메시지 핸들러

    지원하는 형식:
    - &MF {연동} 디스코드ID MC닉네임 - Mojang API로 UUID 조회 후 DB 저장
    - &MF {대기열} 디스코드ID - 대기열에 추가
    - &MF 디스코드ID - 채널 이름 변경 (대사관 형식)
    - &MF @유저멘션 - 채널 이름 변경 (대사관 형식)
    - &MF {채널_이름} [형식] 디스코드ID - 사용자 정의 채널 이름 변경
      - {CC} : 콜사인
      - {NN} : 국가 이름 (특수 폰트)
      - {TT} : 마을 이름
      - {MC} : 마인크래프트 닉네임
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

        if bot_logger:
            bot_logger.log_command("MF", message.author.id, message.author.name, source="mf_handler", category=LogCategory.ADMIN, details={"content": message.content[:200]})

        # &MF 제거하고 나머지 텍스트 추출
        content = mf_line[3:].strip()

        logger.info(f"명령어 감지 (봇: {message.author.name})")
        logger.debug(f"원본: {mf_line}")

        # {연동} 키워드 확인
        is_link_command = '{연동}' in content

        # {대기열} 키워드 확인
        is_queue_command = '{대기열}' in content or '{큐}' in content

        # {채널_이름} 키워드 확인 - 사용자 정의 채널 이름 형식
        is_channel_name_command = '{채널_이름}' in content

        # {연동} 명령어는 별도 파싱 (디스코드ID + MC닉네임)
        if is_link_command:
            return await _handle_link_command(bot, message, content)

        # 디스코드 ID 추출
        user_mention_match = re.search(r'<@!?(\d{15,20})>', content)
        if user_mention_match:
            discord_id = int(user_mention_match.group(1))
        else:
            discord_id_match = re.search(r'(\d{15,20})', content)
            if not discord_id_match:
                await message.channel.send(
                    "디스코드 ID를 찾을 수 없습니다.\n"
                    "사용법:\n"
                    "- `&MF 디스코드ID` - 대사관 형식\n"
                    "- `&MF {채널_이름} [형식] 디스코드ID` - 사용자 정의\n"
                    "- `&MF {대기열} 디스코드ID` - 대기열 추가\n"
                    "- `&MF {연동} 디스코드ID MC닉네임` - MC 계정 연동"
                )
                return True
            discord_id = int(discord_id_match.group(1))

        logger.info(f"Discord ID: {discord_id}")

        # {대기열} 명령어 처리 (모든 봇에서 동작)
        if is_queue_command:
            logger.info(f"대기열 추가: {discord_id}")
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
                        logger.debug(f"중복 요청 무시: {discord_id}")
                        return True

                if queue_manager.add_user(discord_id):
                    bot._last_queue_request[discord_id] = current_time
                    current_queue_size = queue_manager.get_queue_size()
                    if bot_logger:
                        bot_logger.log_queue(
                            f"MF 핸들러 대기열 추가: {discord_id}",
                            user_id=message.author.id, user_name=message.author.name,
                            target_user_id=discord_id,
                            source="mf_handler", action="queue_add",
                            command="&MF {대기열}", details={"triggered_by": message.author.name}
                        )
                    await message.channel.send(
                        f"대기열에 추가되었습니다!\n"
                        f"Discord ID: `{discord_id}`\n"
                        f"현재 대기열: **{current_queue_size}명**"
                    )
                else:
                    await message.channel.send(f"이미 대기열에 있습니다. (ID: `{discord_id}`)")
            except Exception as queue_error:
                await message.channel.send(f"대기열 추가 오류: {queue_error}")
            return True

        # 허용된 봇 확인 (채널 이름 변경 기능)
        from mf_config import is_allowed_bot
        if not is_allowed_bot(message.author.id):
            return False

        # database_manager 로드
        try:
            from database_manager import db_manager
        except ImportError:
            await message.channel.send("데이터베이스 모듈을 로드할 수 없습니다.")
            return True

        # DB에서 유저 정보 조회
        user_info = db_manager.get_user_info(discord_id)

        if not user_info:
            await message.channel.send(f"디스코드 ID `{discord_id}`에 해당하는 사용자를 찾을 수 없습니다.")
            return True

        minecraft_name = user_info.get('current_minecraft_name')

        if not minecraft_name:
            await message.channel.send(f"사용자 `{discord_id}`의 마인크래프트 닉네임이 등록되지 않았습니다.")
            return True

        # 국가 정보 조회
        nation_info = db_manager.get_current_nation(discord_id)

        if not nation_info or not nation_info.get('nation_name'):
            await message.channel.send(f"사용자 `{minecraft_name}`의 국가 정보를 찾을 수 없습니다.")
            return True

        nation_name = nation_info['nation_name']
        town_name = nation_info.get('town_name', '')

        # 콜사인 조회
        callsign = db_manager.get_callsign(discord_id) or ''

        # {채널_이름} 형식 처리
        if is_channel_name_command:
            # [형식] 추출 - 대괄호 안의 내용
            format_match = re.search(r'\[([^\]]+)\]', content)
            if not format_match:
                await message.channel.send(
                    "형식이 올바르지 않습니다.\n"
                    "사용법: `&MF {채널_이름} [형식] 디스코드ID`\n"
                    "예시: `&MF {채널_이름} [{NN} 대사관] 123456789`\n"
                    "- {CC}: 콜사인\n"
                    "- {NN}: 국가 이름\n"
                    "- {TT}: 마을 이름\n"
                    "- {MC}: 마인크래프트 닉네임"
                )
                return True

            format_string = format_match.group(1)

            # 플레이스홀더 치환
            new_channel_name = format_string
            new_channel_name = new_channel_name.replace('{CC}', callsign)
            new_channel_name = new_channel_name.replace('{NN}', convert_to_bold_sans_serif(nation_name))
            new_channel_name = new_channel_name.replace('{TT}', town_name)
            new_channel_name = new_channel_name.replace('{MC}', minecraft_name)

            logger.info(f"채널 이름 형식: {format_string} -> {new_channel_name}")

        else:
            # 기본 대사관 형식
            nation_name_styled = convert_to_bold_sans_serif(nation_name)
            new_channel_name = f"{nation_name_styled} 대사관"

        # nationRanks, townRanks 정보
        nation_ranks = nation_info.get('nation_ranks', '')
        town_ranks = nation_info.get('town_ranks', '')

        # 채널 이름 변경
        try:
            old_name = message.channel.name
            await message.channel.edit(name=new_channel_name)

            # 결과 메시지
            info_lines = [
                f"채널 이름이 변경되었습니다!",
                f"사용자: `{minecraft_name}` (`{discord_id}`)",
                f"국가: `{nation_name}`"
            ]
            if town_name:
                info_lines.append(f"마을: `{town_name}`")
            if callsign:
                info_lines.append(f"콜사인: `{callsign}`")
            if nation_ranks:
                info_lines.append(f"국가 계급: `{nation_ranks}`")
            if town_ranks:
                info_lines.append(f"마을 계급: `{town_ranks}`")
            info_lines.append(f"변경: `{old_name}` -> `{new_channel_name}`")

            await message.channel.send("\n".join(info_lines))
            logger.info(f"채널 이름 변경: {old_name} -> {new_channel_name}")

        except discord.Forbidden:
            await message.channel.send("채널 이름을 변경할 권한이 없습니다.")
        except Exception as e:
            await message.channel.send(f"채널 이름 변경 오류: {e}")
            logger.error(f"채널 이름 변경 오류: {e}", exc_info=True)

        return True

    except Exception as e:
        logger.error(f"핸들러 오류: {e}", exc_info=True)
        return False


async def _handle_link_command(bot, message, content):
    """
    {연동} 명령어 처리
    Mojang API로 MC 닉네임 → UUID 조회 후 DB에 저장

    사용법: &MF {연동} <디스코드ID> <MC닉네임>
    """
    try:
        # {연동} 제거 후 파싱
        after_keyword = content.split('{연동}', 1)[1].strip()

        # 멘션 또는 숫자 ID + MC닉네임 파싱
        mention_match = re.search(r'<@!?(\d{15,20})>', after_keyword)
        if mention_match:
            discord_id = int(mention_match.group(1))
            # 멘션 뒤의 텍스트에서 MC닉네임 추출
            remaining = after_keyword[mention_match.end():].strip()
        else:
            parts = after_keyword.split()
            if len(parts) < 2:
                await message.channel.send(
                    "사용법: `&MF {연동} <디스코드ID> <MC닉네임>`\n"
                    "예시: `&MF {연동} 123456789012345678 Steve`"
                )
                return True
            try:
                discord_id = int(parts[0])
            except ValueError:
                await message.channel.send(f"잘못된 디스코드 ID: `{parts[0]}`")
                return True
            remaining = parts[1]

        mc_nick = remaining.split()[0] if remaining else None

        if not mc_nick:
            await message.channel.send(
                "MC 닉네임을 입력해주세요.\n"
                "사용법: `&MF {연동} <디스코드ID> <MC닉네임>`"
            )
            return True

        logger.info(f"연동 요청: Discord {discord_id} <- MC {mc_nick}")

        # 1. Mojang API로 UUID 조회
        uuid = None
        async with aiohttp.ClientSession() as session:
            mojang_url = f"https://api.mojang.com/users/profiles/minecraft/{mc_nick}"
            try:
                async with session.get(mojang_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        mojang_data = await resp.json()
                        raw_uuid = mojang_data.get('id', '')
                        mc_nick = mojang_data.get('name', mc_nick)  # 정확한 대소문자로 갱신

                        # UUID에 하이픈 추가 (Mojang은 대시 없이 반환)
                        if len(raw_uuid) == 32:
                            uuid = f"{raw_uuid[:8]}-{raw_uuid[8:12]}-{raw_uuid[12:16]}-{raw_uuid[16:20]}-{raw_uuid[20:]}"
                        else:
                            uuid = raw_uuid

                    elif resp.status == 404:
                        await message.channel.send(f"Mojang에서 `{mc_nick}`을(를) 찾을 수 없습니다. 닉네임을 확인해주세요.")
                        return True
                    else:
                        await message.channel.send(f"Mojang API 오류 (HTTP {resp.status})")
                        return True
            except aiohttp.ClientError as e:
                await message.channel.send(f"Mojang API 연결 실패: {e}")
                return True

        if not uuid:
            await message.channel.send(f"`{mc_nick}`의 UUID를 가져올 수 없습니다.")
            return True

        logger.info(f"Mojang UUID 조회 성공: {mc_nick} -> {uuid}")

        # 2. DB에 저장
        try:
            from database_manager import db_manager

            # 기존 정보 확인
            existing = db_manager.get_user_info(discord_id)
            old_name = existing.get('current_minecraft_name') if existing else None

            db_manager.add_or_update_user(
                discord_id=discord_id,
                minecraft_uuid=uuid,
                minecraft_name=mc_nick
            )
        except ImportError:
            await message.channel.send("데이터베이스 모듈을 로드할 수 없습니다.")
            return True
        except Exception as db_error:
            await message.channel.send(f"DB 저장 실패: {db_error}")
            return True

        # 3. 결과 메시지
        embed = discord.Embed(
            title="MC 계정 연동 완료",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=f"https://mc-heads.net/avatar/{mc_nick}/128.png")
        embed.add_field(name="Discord ID", value=f"`{discord_id}`", inline=True)
        embed.add_field(name="MC 닉네임", value=f"`{mc_nick}`", inline=True)
        embed.add_field(name="UUID", value=f"`{uuid}`", inline=False)

        if old_name and old_name != mc_nick:
            embed.add_field(name="이전 닉네임", value=f"`{old_name}`", inline=True)

        embed.set_footer(text="대기열 처리 시 PlanetEarth API 조회를 건너뜁니다")

        await message.channel.send(embed=embed)
        logger.info(f"연동 완료: {discord_id} <- {mc_nick} ({uuid[:8]}...)")
        return True

    except Exception as e:
        logger.error(f"연동 명령어 오류: {e}", exc_info=True)
        await message.channel.send(f"연동 처리 중 오류: {e}")
        return True
