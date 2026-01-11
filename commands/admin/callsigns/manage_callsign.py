# commands/admin/callsigns/manage_callsign.py
# /콜사인관리 명령어 - 사용자 콜사인 관리 (관리자 전용)

import discord
from discord import app_commands
from typing import Literal
import aiohttp
import os
import json
import datetime
import asyncio
import re

# 안전한 import 처리
try:
    from callsign_manager import callsign_manager, validate_callsign
    CALLSIGN_ENABLED = True
except ImportError:
    callsign_manager = None
    CALLSIGN_ENABLED = False
    def validate_callsign(callsign: str):
        return False, "콜사인 기능이 비활성화됨"

try:
    from database_manager import db_manager
    DATABASE_ENABLED = True
except ImportError:
    db_manager = None
    DATABASE_ENABLED = False

# 환경 변수
MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")
BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")

# 관리자 권한 체크 함수
def is_admin(interaction: discord.Interaction) -> bool:
    """관리자 권한이 있거나 특정 역할을 가진 경우 허용"""
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359

    # 관리자 권한 체크
    if interaction.user.guild_permissions.administrator:
        return True

    # 콜사인 관리자 역할 체크
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True

    return False


def setup(bot):
    """봇에 /콜사인관리 명령어 등록"""

    @bot.tree.command(name="콜사인관리", description="사용자 콜사인을 관리합니다")
    @app_commands.describe(
        기능="실행할 기능 선택",
        유저="대상 사용자 (쿨타임_초기화: 비어있으면 전체, 멘션하면 해당 유저만)",
        역할="역할 양식 설정 대상 역할",
        텍스트="콜사인 텍스트 또는 사유 또는 양식"
    )
    @app_commands.check(is_admin)
    async def 콜사인관리(
        interaction: discord.Interaction,
        기능: Literal["사용자_조회", "콜사인_변경", "전체_목록", "권한박탈", "권한복구", "권한박탈_목록", "쿨타임_초기화", "데이터_백업", "백업_목록", "데이터_복구", "백업파일_업로드", "역할_양식", "역할_양식_목록", "역할_양식_제거"],
        유저: discord.Member = None,
        역할: discord.Role = None,
        텍스트: str = None
    ):
        """사용자 콜사인 관리 - 관리자 전용"""
        # ======================================
        #
        #             기본 사유 지정
        #
        # ======================================

        COLLSIGN_BASE_REASON = "사유 없음"
        COLLSIGN_BASE_BAN_REASON = "관리자가 박탈"

        # ======================================
        if not CALLSIGN_ENABLED:
            embed = discord.Embed(
                title="⌛ 기능 비활성화",
                description="콜사인 기능이 비활성화되어 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed)
            return

        # 기능별 처리
        if 기능 == "사용자_조회":  # 기존: 콜사인_조회
            if not 유저:
                await interaction.response.send_message("조회할 사용자를 지정해주세요.")
                return

            callsign = callsign_manager.get_callsign(유저.id)
            is_banned = callsign_manager.is_banned(유저.id)

            embed = discord.Embed(
                title="🔍 콜사인 조회",
                color=0x00ff00 if not is_banned else 0xff0000
            )

            if is_banned:
                ban_info = callsign_manager.get_ban_info(유저.id)
                embed.add_field(
                    name="⛔ 상태",
                    value="콜사인 사용 권한 없음",
                    inline=False
                )
                embed.add_field(
                    name="📅 권한 박탈 일시",
                    value=ban_info.get("banned_at", "알 수 없음")[:19],
                    inline=True
                )
                embed.add_field(
                    name="📝 사유",
                    value=ban_info.get("reason", COLLSIGN_BASE_REASON ),
                    inline=True
                )
            elif callsign:
                embed.add_field(
                    name="✅ 현재 콜사인",
                    value=f"`{callsign}`",
                    inline=False
                )
                callsign_info = callsign_manager.get_callsign_info(유저.id)
                if callsign_info and "set_at" in callsign_info:
                    embed.add_field(
                        name="📅 설정 일시",
                        value=callsign_info["set_at"][:19],
                        inline=False
                    )
            else:
                embed.add_field(
                    name="ℹ️ 상태",
                    value="설정된 콜사인 없음",
                    inline=False
                )

            embed.set_footer(text=f"대상: {유저.name} ({유저.id})")
            await interaction.response.send_message(embed=embed)

        elif 기능 == "콜사인_변경":  # 기존: 콜사인_설정
            if not 유저 or not 텍스트:
                await interaction.response.send_message("사용자와 콜사인 텍스트를 모두 입력해주세요.", ephemeral=True)
                return

            # 콜사인 유효성 검증
            is_valid, error_msg = validate_callsign(텍스트)
            if not is_valid:
                embed = discord.Embed(
                    title="❌ 콜사인 유효성 검증 실패",
                    description=f"**오류:** {error_msg}",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # defer 호출 먼저 (DB 작업 및 API 조회 시간이 필요)
            await interaction.response.defer(ephemeral=True)

            # 기존 콜사인 확인
            old_callsign = callsign_manager.get_callsign(유저.id)

            # 권한 박탈 상태 확인
            is_banned = callsign_manager.is_banned(유저.id)
            ban_info = None
            if is_banned:
                ban_info = callsign_manager.get_ban_info(유저.id)

            # 관리자 권한으로 콜사인 설정 (모든 제약 무시)
            success, message = callsign_manager.admin_set_callsign(
                user_id=유저.id,
                callsign=텍스트,
                admin_id=interaction.user.id
            )

            if success:

                # 닉네임 업데이트 시도
                nick_changed = False
                new_nick = ""
                nick_error = None
                mc_id = None

                try:
                    # DB에서 마인크래프트 ID, 국가, 마을 정보 조회
                    nation_name = ""
                    town_name = ""

                    # DB에서 사용자 정보 가져오기
                    if db_manager:
                        user_info = db_manager.get_user_info(유저.id)
                        if user_info:
                            mc_id = user_info.get('current_minecraft_name', '') or user_info.get('minecraft_name', '')

                        # 국가/마을 정보는 nation_history에서 조회
                        nation_info = db_manager.get_current_nation(유저.id)
                        if nation_info:
                            nation_name = nation_info.get('nation_name', '')
                            town_name = nation_info.get('town_name', '')

                    # DB에서 가져오지 못한 경우 API로 조회
                    if not mc_id:
                        async with aiohttp.ClientSession() as session:
                            url1 = f"{MC_API_BASE}/discord?discord={유저.id}"
                            async with session.get(url1, timeout=aiohttp.ClientTimeout(total=10)) as r1:
                                if r1.status == 200:
                                    data1 = await r1.json()
                                    if data1.get('data') and data1['data']:
                                        mc_id = data1['data'][0].get('name')

                    # 상위 역할 중 콜사인 양식이 있는 역할 찾기
                    cc_pattern = r'\{CC\}'
                    role_format = None
                    selected_role = None

                    # 사용자의 역할을 우선순위 순으로 정렬 (위치가 높을수록 우선)
                    sorted_roles = sorted(유저.roles, key=lambda r: r.position, reverse=True)

                    # 역할 양식 조회
                    all_role_formats = callsign_manager.get_all_role_formats()

                    # 가장 높은 우선순위의 역할 양식 찾기
                    for role in sorted_roles:
                        if str(role.id) in all_role_formats:
                            format_data = all_role_formats[str(role.id)]
                            format_string = format_data.get("format", "")
                            if re.search(cc_pattern, format_string):
                                role_format = format_string
                                selected_role = role
                                break

                    # 닉네임 생성
                    if role_format:
                        # callsign_manager의 apply_format_to_nickname 사용
                        new_nick = callsign_manager.apply_format_to_nickname(
                            format_string=role_format,
                            mc_id=mc_id,
                            nation=nation_name,
                            town=town_name,
                            callsign=텍스트
                        )
                    else:
                        # 역할 양식이 없으면 현재 닉네임에서 {CC} 찾기
                        current_nick = 유저.display_name

                        if re.search(cc_pattern, current_nick):
                            # {CC}를 새 콜사인으로 교체
                            new_nick = re.sub(cc_pattern, 텍스트, current_nick)
                        else:
                            # {CC}도 없으면 {MC} | {CC} 형식으로 강제 설정
                            if mc_id:
                                base_name = mc_id
                            else:
                                # 마크 ID를 가져올 수 없으면 현재 닉네임에서 추출
                                if 'ㅣ' in current_nick:
                                    base_name = current_nick.split('ㅣ')[0].strip()
                                elif '|' in current_nick:
                                    base_name = current_nick.split('|')[0].strip()
                                else:
                                    base_name = current_nick

                            # 새 닉네임 생성 (| 구분자 사용)
                            new_nick = f"{base_name} | {텍스트}"

                    # 닉네임 길이 제한 (32자)
                    if len(new_nick) > 32:
                        # {CC} 패턴이 있었다면 경고만 하고 변경 안 함
                        if re.search(r'\{CC\}', current_nick):
                            nick_error = "닉네임이 32자를 초과합니다"
                            new_nick = current_nick  # 원래 닉네임 유지
                        else:
                            # 콜사인을 우선 보존하고 이름 부분을 줄임 (| 구분자 사용)
                            max_name_len = 32 - len(f" | {텍스트}")
                            if max_name_len > 0:
                                truncated_name = base_name[:max_name_len]
                                new_nick = f"{truncated_name} | {텍스트}"
                            else:
                                # 콜사인이 너무 길어서 이름을 넣을 공간이 없는 경우
                                new_nick = f"User | {텍스트[:27]}"  # 강제로 줄임

                    # 닉네임 변경 시도
                    await 유저.edit(nick=new_nick, reason=f"관리자 콜사인 설정: {interaction.user.name}")
                    nick_changed = True

                except discord.Forbidden:
                    nick_changed = False
                    nick_error = "권한 없음 (관리자 역할보다 높음)"
                except discord.HTTPException as e:
                    nick_changed = False
                    nick_error = f"Discord API 오류: {str(e)}"
                except Exception as e:
                    nick_changed = False
                    nick_error = f"알 수 없는 오류: {str(e)}"

                # 성공 임베드 생성
                embed = discord.Embed(
                    title="✅ 관리자 콜사인 설정 완료",
                    description=f"**대상:** {유저.mention}\n"
                            f"**설정된 콜사인:** `{텍스트}`",
                    color=0x00ff00
                )

                # 이전 콜사인 정보
                if old_callsign and old_callsign != 텍스트:
                    embed.add_field(
                        name="📋 이전 콜사인",
                        value=f"`{old_callsign}` → `{텍스트}`",
                        inline=True
                    )

                # 닉네임 변경 결과
                if nick_changed:
                    embed.add_field(
                        name="👤 닉네임 변경",
                        value=f"✅ `{new_nick}`로 자동 변경됨",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="⚠️ 닉네임 변경 실패",
                        value=f"❌ {nick_error}\n💡 수동으로 닉네임을 `{new_nick}`로 변경해주세요.",
                        inline=False
                    )

                # 권한 박탈 상태 경고
                if is_banned:
                    embed.add_field(
                        name="⚠️ 중요 안내",
                        value=f"🚫 **이 사용자는 콜사인 사용이 금지된 상태입니다.**\n"
                            f"**금지 사유:** {ban_info.get('reason', '사유 없음')}\n"
                            f"**금지 일시:** {ban_info.get('banned_at', '알 수 없음')[:19] if ban_info.get('banned_at') else '알 수 없음'}\n"
                            f"✅ 관리자 권한으로 설정되었습니다.",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📌 안내",
                        value="• 관리자 권한으로 설정되어 쿨타임이 적용되지 않습니다.\n"
                            "• 콜사인이 즉시 적용되었습니다.",
                        inline=False
                    )

                embed.set_footer(text=f"처리자: {interaction.user.name}")
                embed.timestamp = datetime.datetime.now()

                # followup으로 응답 전송
                await interaction.followup.send(embed=embed, ephemeral=True)

            else:
                # 실패 임베드
                embed = discord.Embed(
                    title="❌ 콜사인 설정 실패",
                    description=f"**대상:** {유저.mention}\n"
                            f"**시도한 콜사인:** `{텍스트}`\n"
                            f"**실패 사유:** {message}",
                    color=0xff0000
                )
                embed.set_footer(text=f"처리자: {interaction.user.name}")
                embed.timestamp = datetime.datetime.now()

                # response로 응답 전송
                await interaction.response.send_message(embed=embed, ephemeral=True)

            # 로그 채널에 기록 (성공한 경우만)
            if success:
                try:
                    from config import config
                    if hasattr(config, 'LOG_CHANNEL_ID') and config.LOG_CHANNEL_ID:
                        log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                        if log_channel:
                            log_embed = discord.Embed(
                                title="🔧 관리자 콜사인 변경",
                                description=f"**대상:** {유저.mention} ({유저.id})\n"
                                        f"**이전 콜사인:** `{old_callsign or '없음'}`\n"
                                        f"**새 콜사인:** `{텍스트}`\n"
                                        f"**처리자:** {interaction.user.mention}\n"
                                        f"**닉네임 변경:** {'성공' if nick_changed else '실패'}\n"
                                        f"**권한 박탈 상태:** {'예' if is_banned else '아니오'}",
                                color=0xffa500 if is_banned else 0x00ff00,
                                timestamp=datetime.datetime.now()
                            )

                            if is_banned and ban_info:
                                log_embed.add_field(
                                    name="⚠️ 금지 정보",
                                    value=f"**사유:** {ban_info.get('reason', '사유 없음')}\n"
                                        f"**금지 일시:** {ban_info.get('banned_at', '알 수 없음')[:19] if ban_info.get('banned_at') else '알 수 없음'}",
                                    inline=False
                                )

                            await log_channel.send(embed=log_embed)
                except Exception as e:
                    print(f"로그 채널 기록 실패: {e}")

        elif 기능 == "권한박탈":
            # 관리자 권한 체크
            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ 권한 없음",
                    description="이 기능은 서버 관리자만 사용할 수 있습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if not 유저:
                await interaction.response.send_message("대상 사용자를 지정해주세요.", ephemeral=True)
                return

            reason = 텍스트 or COLLSIGN_BASE_BAN_REASON

            success, message = callsign_manager.ban_user(
                user_id=유저.id,
                banned_by=interaction.user.id,
                reason=reason
            )

            embed = discord.Embed(
                title="⛔ 콜사인 권한 박탈" if success else "⚠️ 권한 박탈 실패",
                description=f"**대상:** {유저.mention}\n**결과:** {message}",
                color=0xff0000 if success else 0xffa500
            )

            if success:
                embed.add_field(
                    name="📝 사유",
                    value=reason,
                    inline=False
                )

                # 현재 콜사인 확인
                current_callsign = callsign_manager.get_callsign(유저.id)
                if current_callsign:
                    embed.add_field(
                        name="ℹ️ 참고",
                        value=f"• 현재 콜사인 `{current_callsign}`은 유지됩니다.\n"
                              f"• 대상 사용자는 더 이상 `/콜사인` 명령어로 콜사인을 변경할 수 없습니다.\n"
                              f"• 관리자는 `/콜사인관리 기능:콜사인_변경`으로 강제 변경할 수 있습니다.",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="ℹ️ 참고",
                        value=f"• 대상 사용자는 `/콜사인` 명령어를 사용할 수 없습니다.\n"
                              f"• 관리자는 `/콜사인관리 기능:콜사인_변경`으로 강제 설정할 수 있습니다.",
                        inline=False
                    )

            embed.set_footer(text=f"처리자: {interaction.user.name}")

            await interaction.response.send_message(embed=embed)

            # 로그 채널에 기록
            try:
                from config import config
                if success and hasattr(config, 'LOG_CHANNEL_ID') and config.LOG_CHANNEL_ID:
                    log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                    if log_channel:
                        current_callsign = callsign_manager.get_callsign(유저.id)
                        log_embed = discord.Embed(
                            title="⛔ 콜사인 권한 박탈",
                            description=f"**대상:** {유저.mention} ({유저.id})\n"
                                       f"**처리자:** {interaction.user.mention}\n"
                                       f"**사유:** {reason}",
                            color=0xff0000,
                            timestamp=datetime.datetime.now()
                        )

                        if current_callsign:
                            log_embed.add_field(
                                name="현재 콜사인",
                                value=f"`{current_callsign}` (유지됨)",
                                inline=False
                            )

                        await log_channel.send(embed=log_embed)
            except:
                pass

        elif 기능 == "권한복구":  # 기존: 권한복구
            # 관리자 권한 체크
            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ 권한 없음",
                    description="이 기능은 서버 관리자만 사용할 수 있습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if not 유저:
                await interaction.response.send_message("대상 사용자를 지정해주세요.", ephemeral=True)
                return

            success, message = callsign_manager.unban_user(유저.id)

            embed = discord.Embed(
                title="✅ 콜사인 권한 복구" if success else "⚠️ 권한 복구 실패",
                description=f"**대상:** {유저.mention}\n**결과:** {message}",
                color=0x00ff00 if success else 0xff0000
            )
            embed.set_footer(text=f"처리자: {interaction.user.name}")

            await interaction.response.send_message(embed=embed)

            # 로그 채널에 기록
            try:
                from config import config
                if success and hasattr(config, 'LOG_CHANNEL_ID') and config.LOG_CHANNEL_ID:
                    log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="✅ 콜사인 권한 복구",
                            description=f"**대상:** {유저.mention} ({유저.id})\n"
                                       f"**처리자:** {interaction.user.mention}",
                            color=0x00ff00,
                            timestamp=datetime.datetime.now()
                        )
                        await log_channel.send(embed=log_embed)
            except:
                pass

        elif 기능 == "권한박탈_목록":  # 기존: 권한박탈_목록
            banned_users = callsign_manager.get_banned_users_list()

            if not banned_users:
                embed = discord.Embed(
                    title="📋 콜사인 사용 금지 목록",
                    description="현재 금지된 사용자가 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📋 콜사인 사용 금지 목록",
                    description=f"총 {len(banned_users)}명의 사용자가 금지되어 있습니다.",
                    color=0xff6600
                )

                for i, ban_info in enumerate(banned_users[:10], 1):
                    try:
                        user = interaction.guild.get_member(int(ban_info["user_id"]))
                        user_name = user.name if user else f"Unknown ({ban_info['user_id']})"
                    except:
                        user_name = f"Unknown ({ban_info['user_id']})"

                    embed.add_field(
                        name=f"{i}. {user_name}",
                        value=f"**사유:** {ban_info['reason']}\n"
                              f"**일시:** {ban_info['banned_at'][:10] if ban_info.get('banned_at') else '알 수 없음'}",
                        inline=False
                    )

                if len(banned_users) > 10:
                    embed.set_footer(text=f"... 외 {len(banned_users) - 10}명")

            await interaction.response.send_message(embed=embed)

        elif 기능 == "쿨타임_초기화":
            # 쿨타임 초기화
            if 유저:
                # 특정 유저의 쿨타임만 초기화
                success, message = callsign_manager.reset_cooldown(유저.id)

                embed = discord.Embed(
                    title="⏰ 쿨타임 초기화" if success else "⚠️ 쿨타임 초기화 실패",
                    description=f"**대상:** {유저.mention}\n\n{message}",
                    color=0x00ff00 if success else 0xff9900
                )

                if success:
                    embed.add_field(
                        name="✅ 안내",
                        value=f"{유저.name}님은 이제 즉시 콜사인을 변경할 수 있습니다.",
                        inline=False
                    )
            else:
                # 모든 유저의 쿨타임 초기화
                count = callsign_manager.reset_all_cooldowns()

                embed = discord.Embed(
                    title="⏰ 전체 쿨타임 초기화",
                    description=f"총 **{count}명**의 쿨타임이 초기화되었습니다.",
                    color=0x00ff00
                )

                embed.add_field(
                    name="✅ 안내",
                    value="모든 사용자가 즉시 콜사인을 변경할 수 있습니다.",
                    inline=False
                )

                embed.set_footer(text=f"관리자: {interaction.user.name}")

            await interaction.response.send_message(embed=embed)

        elif 기능 == "전체_목록":  # 기존: 목록
            # 전체 콜사인 목록 표시 - callsigns 속성을 직접 사용
            all_callsigns = {}
            for user_id, info in callsign_manager.callsigns.items():
                if isinstance(info, dict) and "callsign" in info:
                    all_callsigns[user_id] = info["callsign"]

            if not all_callsigns:
                embed = discord.Embed(
                    title="📋 전체 콜사인 목록",
                    description="설정된 콜사인이 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📋 전체 콜사인 목록",
                    description=f"총 {len(all_callsigns)}명이 콜사인을 설정했습니다.",
                    color=0x00bfff
                )

                # 페이지네이션을 위해 20개까지만 표시
                display_count = min(20, len(all_callsigns))
                for i, (user_id, callsign) in enumerate(list(all_callsigns.items())[:display_count], 1):
                    try:
                        user = interaction.guild.get_member(int(user_id))
                        user_name = user.name if user else f"Unknown"
                    except:
                        user_name = "Unknown"

                    # 콜사인 정보 가져오기
                    callsign_info = callsign_manager.get_callsign_info(user_id)
                    set_date = "알 수 없음"
                    if callsign_info and "set_at" in callsign_info:
                        set_date = callsign_info["set_at"][:10]  # YYYY-MM-DD만 표시

                    embed.add_field(
                        name=f"{i}. {user_name}",
                        value=f"**콜사인:** `{callsign}`\n**설정일:** {set_date}",
                        inline=True
                    )

                if len(all_callsigns) > display_count:
                    embed.set_footer(text=f"... 외 {len(all_callsigns) - display_count}명")

            await interaction.response.send_message(embed=embed)

        # 백업 관련 기능들
        elif 기능 == "데이터_백업":  # 기존: 백업생성
            await interaction.response.defer()

            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.followup.send(embed=embed)
                    return

            success, result = backup_manager.create_backup("manual")

            embed = discord.Embed(
                title="💾 수동 백업" if success else "❌ 백업 실패",
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                backup_file = os.path.basename(result)
                file_size = os.path.getsize(result) / 1024

                embed.add_field(
                    name="✅ 백업 완료",
                    value=f"**파일명:** `{backup_file}`\n"
                          f"**크기:** {file_size:.2f} KB\n"
                          f"**경로:** `{result}`",
                    inline=False
                )

                with open(result, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    callsign_count = len(data.get("data", data))

                embed.add_field(
                    name="📊 백업 통계",
                    value=f"**저장된 콜사인:** {callsign_count}개\n"
                          f"**백업 시간:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )

                # 백업 파일을 Discord 파일로 업로드
                try:
                    discord_file = discord.File(result, filename=backup_file)
                    embed.add_field(
                        name="📎 첨부 파일",
                        value="백업 파일이 이 메시지에 첨부되었습니다.",
                        inline=False
                    )
                    embed.set_footer(text=f"처리자: {interaction.user.name}")
                    await interaction.followup.send(embed=embed, file=discord_file)
                    return
                except Exception as e:
                    print(f"⚠️ 백업 파일 업로드 실패: {e}")
                    embed.add_field(
                        name="⚠️ 파일 업로드 실패",
                        value=f"파일은 서버에 저장되었으나 Discord 업로드에 실패했습니다.\n오류: {str(e)[:100]}",
                        inline=False
                    )
            else:
                embed.description = result

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.followup.send(embed=embed)

        elif 기능 == "백업_목록":  # 기존: 백업목록
            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed)
                    return

            backups = backup_manager.list_backups(15)

            if not backups:
                embed = discord.Embed(
                    title="📁 백업 목록",
                    description="저장된 백업이 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📁 백업 목록",
                    description=f"총 {len(backups)}개의 백업이 있습니다.",
                    color=0x00bfff
                )

                for i, backup in enumerate(backups[:10], 1):
                    backup_type = "🔄 자동" if backup["type"] == "auto" else "👤 수동" if backup["type"] == "manual" else "📤 업로드"

                    embed.add_field(
                        name=f"{i}. {backup_type} 백업",
                        value=f"**파일:** `{backup['filename']}`\n"
                              f"**시간:** {backup['created'].strftime('%Y-%m-%d %H:%M')}\n"
                              f"**크기:** {backup['size_kb']} KB | **콜사인:** {backup['callsign_count']}개",
                        inline=False
                    )

                if len(backups) > 10:
                    embed.set_footer(text=f"... 외 {len(backups) - 10}개 백업")

            await interaction.response.send_message(embed=embed)

        elif 기능 == "데이터_복구":  # 기존: 백업복구
            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed)
                    return

            if not 텍스트:
                backups = backup_manager.list_backups(5)

                if not backups:
                    await interaction.response.send_message("저장된 백업이 없습니다.")
                    return

                embed = discord.Embed(
                    title="🔄 백업 복구",
                    description="복구할 백업 파일명을 `텍스트` 매개변수에 입력해주세요.\n\n**최근 백업 목록:**",
                    color=0xffff00
                )

                for backup in backups:
                    embed.add_field(
                        name=backup['filename'],
                        value=f"생성: {backup['created'].strftime('%Y-%m-%d %H:%M')} | 콜사인: {backup['callsign_count']}개",
                        inline=False
                    )

                await interaction.response.send_message(embed=embed)
                return

            await interaction.response.defer()

            backup_path = os.path.join(backup_manager.backup_dir, 텍스트)
            success, message = backup_manager.restore_backup(backup_path)

            embed = discord.Embed(
                title="✅ 복구 완료" if success else "❌ 복구 실패",
                description=message,
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                embed.add_field(
                    name="⚠️ 주의사항",
                    value="기존 데이터는 `.pre_restore_` 파일로 백업되었습니다.\n"
                          "복구 후 문제가 있다면 해당 파일로 재복구 가능합니다.",
                    inline=False
                )

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.followup.send(embed=embed)

        elif 기능 == "역할_양식":
            # 역할별 닉네임 양식 설정
            if not 역할:
                await interaction.response.send_message("역할을 지정해주세요.", ephemeral=True)
                return

            if not 텍스트:
                await interaction.response.send_message("양식 텍스트를 입력해주세요.", ephemeral=True)
                return

            # 양식 설정
            success, message = callsign_manager.set_role_format(역할.id, 텍스트)

            embed = discord.Embed(
                title="🎭 역할 닉네임 양식 설정" if success else "❌ 양식 설정 실패",
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                embed.add_field(
                    name="🎯 대상 역할",
                    value=f"{역할.mention} (`{역할.name}`)",
                    inline=False
                )
                embed.add_field(
                    name="📝 설정된 양식",
                    value=f"`{텍스트}`",
                    inline=False
                )
                embed.add_field(
                    name="📚 사용 가능한 변수",
                    value="• `{MF}` 또는 `{MC}` - 마인크래프트 닉네임 (없으면 ❌)\n"
                          "• `{NN}` - PlanetEarth 국가 이름 (없으면 ❌)\n"
                          "• `{TT}` - PlanetEarth 마을 이름 (없으면 ❌)\n"
                          "• `{CC}` - 콜사인 (없으면 빈 값)\n"
                          "• `{NN/TT}` - 국가가 있으면 국가, 없으면 `[ T ] 마을` (둘 다 없으면 ❌)",
                    inline=False
                )

                # 예시 생성
                example = callsign_manager.apply_format_to_nickname(
                    텍스트,
                    mc_id="Steve",
                    nation="Korea",
                    town="Seoul",
                    callsign="Leader"
                )
                embed.add_field(
                    name="💡 예시",
                    value=f"`{example}`",
                    inline=False
                )

                embed.add_field(
                    name="ℹ️ 안내",
                    value=f"• 이 역할을 가진 사용자가 콜사인을 설정하면 자동으로 이 양식이 적용됩니다.\n"
                          f"• 여러 역할을 가진 경우 **가장 우선순위가 높은 역할**의 양식이 적용됩니다.\n"
                          f"• 역할 우선순위는 Discord 서버 설정에서 확인할 수 있습니다.",
                    inline=False
                )
            else:
                embed.description = message

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)

        elif 기능 == "역할_양식_목록":
            # 모든 역할 양식 조회
            all_formats = callsign_manager.get_all_role_formats()

            if not all_formats:
                embed = discord.Embed(
                    title="📋 역할 닉네임 양식 목록",
                    description="설정된 역할 양식이 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📋 역할 닉네임 양식 목록",
                    description=f"총 {len(all_formats)}개의 역할 양식이 설정되어 있습니다.",
                    color=0x00bfff
                )

                for i, (role_id, format_data) in enumerate(list(all_formats.items())[:15], 1):
                    try:
                        role = interaction.guild.get_role(int(role_id))
                        role_name = role.name if role else f"Unknown Role ({role_id})"
                        role_mention = role.mention if role else f"<삭제된 역할>"
                    except:
                        role_name = f"Unknown ({role_id})"
                        role_mention = f"<삭제된 역할>"

                    format_string = format_data.get("format", "알 수 없음")
                    set_date = "알 수 없음"
                    if "set_at" in format_data:
                        set_date = format_data["set_at"][:10]

                    embed.add_field(
                        name=f"{i}. {role_name}",
                        value=f"**역할:** {role_mention}\n"
                              f"**양식:** `{format_string}`\n"
                              f"**설정일:** {set_date}",
                        inline=False
                    )

                if len(all_formats) > 15:
                    embed.set_footer(text=f"... 외 {len(all_formats) - 15}개")

            await interaction.response.send_message(embed=embed)

        elif 기능 == "역할_양식_제거":
            # 역할 양식 제거
            if not 역할:
                await interaction.response.send_message("제거할 역할을 지정해주세요.", ephemeral=True)
                return

            success, message = callsign_manager.remove_role_format(역할.id)

            embed = discord.Embed(
                title="🗑️ 역할 양식 제거" if success else "⚠️ 양식 제거 실패",
                description=f"**대상 역할:** {역할.mention}\n\n{message}",
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                embed.add_field(
                    name="ℹ️ 안내",
                    value=f"• 이제 이 역할을 가진 사용자는 기본 양식으로 닉네임이 설정됩니다.\n"
                          f"• 기존 사용자의 닉네임은 변경되지 않습니다.",
                    inline=False
                )

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)

        elif 기능 == "백업파일_업로드":  # 기존: 백업백업파일_업로드
            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed)
                    return

            embed = discord.Embed(
                title="📤 백업 파일 업로드",
                description="백업 파일을 업로드하려면 다음 단계를 따라주세요:\n\n"
                           "1. 이 메시지에 답장으로 백업 JSON 파일을 첨부\n"
                           "2. 10초 이내에 파일을 업로드해주세요\n"
                           "3. 업로드된 파일로 자동 복구됩니다\n\n"
                           "⚠️ **주의:** 현재 데이터가 모두 교체됩니다!",
                color=0xffff00
            )

            await interaction.response.send_message(embed=embed)

            # 파일 업로드 대기
            def check(m):
                return m.author == interaction.user and m.attachments and m.channel == interaction.channel

            try:
                message = await bot.wait_for('message', timeout=10.0, check=check)

                if message.attachments:
                    attachment = message.attachments[0]

                    if not attachment.filename.endswith('.json'):
                        await interaction.followup.send("❌ JSON 파일만 업로드 가능합니다.")
                        return

                    # 파일 다운로드
                    file_content = await attachment.read()

                    # 복구 실행
                    success, result = backup_manager.restore_from_upload(file_content)

                    embed = discord.Embed(
                        title="✅ 업로드 복구 완료" if success else "❌ 업로드 복구 실패",
                        description=result,
                        color=0x00ff00 if success else 0xff0000
                    )

                    if success:
                        embed.add_field(
                            name="📁 백업 저장",
                            value="업로드된 파일은 백업 디렉토리에 저장되었습니다.",
                            inline=False
                        )

                    await interaction.followup.send(embed=embed)

                    # 업로드된 메시지 삭제
                    try:
                        await message.delete()
                    except:
                        pass

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ 시간 초과: 10초 내에 파일을 업로드해주세요.")
