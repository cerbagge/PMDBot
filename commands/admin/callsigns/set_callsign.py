# commands/admin/callsigns/set_callsign.py
# /콜사인 명령어 - 개인 콜사인(별명) 설정 (15일 쿨타임)

import discord
from discord import app_commands
import aiohttp
import time
import os

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


def setup(bot):
    """봇에 /콜사인 명령어 등록"""

    @bot.tree.command(name="콜사인", description="개인 콜사인(별명)을 설정합니다 (15일 쿨타임)")
    @app_commands.describe(텍스트="설정할 콜사인 (최대 20자)")
    async def 콜사인(interaction: discord.Interaction, 텍스트: str):
        """사용자 콜사인 설정 - 15일 쿨타임 적용"""

        if not CALLSIGN_ENABLED:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⌛ 기능 비활성화",
                    description="콜사인 기능이 비활성화되어 있습니다.\n"
                              "`callsign_manager.py` 파일이 필요합니다.",
                    color=0xff0000
                ),
                ephemeral=True
            )
            return

        # 권한 체크 추가 - 금지된 사용자인지 확인
        if callsign_manager.is_banned(interaction.user.id):
            ban_info = callsign_manager.get_ban_info(interaction.user.id)
            embed = discord.Embed(
                title="🚫 콜사인 사용 금지",
                description=f"콜사인 기능을 사용할 수 없습니다.\n\n"
                           f"**사유:** {ban_info.get('reason', '관리자 결정')}\n"
                           f"**금지 일시:** {ban_info.get('banned_at', '알 수 없음')[:19] if ban_info.get('banned_at') else '알 수 없음'}",
                color=0xff0000
            )
            embed.set_footer(text="문의사항은 관리자에게 연락해주세요.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 콜사인 유효성 검증
        is_valid, error_msg = validate_callsign(텍스트)
        if not is_valid:
            await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
            return

        # defer를 먼저 호출 (API 조회 및 닉네임 변경에 시간이 걸릴 수 있음)
        await interaction.response.defer(ephemeral=True)

        # 콜사인 설정
        success, message = callsign_manager.set_callsign(interaction.user.id, 텍스트)

        if not success:
            # 쿨타임 등으로 실패한 경우
            embed = discord.Embed(
                title="⏰ 쿨타임 중",
                description=message,
                color=0xff6600
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 콜사인 설정 성공 시 즉시 닉네임 적용
        member = interaction.user
        discord_id = member.id
        nickname_updated = False
        nickname_error = None
        mc_id = None
        nation = None
        town = None
        applied_format = None

        try:
            # API를 통해 마크 ID와 국가 정보 조회
            async with aiohttp.ClientSession() as session:
                # 1단계: 디스코드 ID → 마크 ID
                url1 = f"{MC_API_BASE}/discord?discord={discord_id}"
                async with session.get(url1, timeout=aiohttp.ClientTimeout(total=10)) as r1:
                    if r1.status == 200:
                        data1 = await r1.json()
                        if data1.get('data') and data1['data']:
                            mc_id = data1['data'][0].get('name')
                            mc_uuid = data1['data'][0].get('uuid')

                            # 데이터베이스에 저장 (UUID와 Minecraft 닉네임)
                            if DATABASE_ENABLED and db_manager and mc_id and mc_uuid:
                                try:
                                    db_manager.add_or_update_user(
                                        discord_id=discord_id,
                                        minecraft_uuid=mc_uuid,
                                        minecraft_name=mc_id
                                    )
                                    print(f"  💾 데이터베이스 저장: {mc_id} (UUID: {mc_uuid[:8]}...)")
                                except Exception as db_error:
                                    print(f"  ⚠️ 데이터베이스 저장 실패: {db_error}")

                            if mc_id:
                                time.sleep(2)

                                # 2단계: 마크 ID → 마을
                                url2 = f"{MC_API_BASE}/resident?name={mc_id}"
                                async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                                    if r2.status == 200:
                                        data2 = await r2.json()
                                        if data2.get('data') and data2['data']:
                                            town = data2['data'][0].get('town')
                                            if town:
                                                time.sleep(2)

                                                # 3단계: 마을 → 국가
                                                url3 = f"{MC_API_BASE}/town?name={town}"
                                                async with session.get(url3, timeout=aiohttp.ClientTimeout(total=10)) as r3:
                                                    if r3.status == 200:
                                                        data3 = await r3.json()
                                                        if data3.get('data') and data3['data']:
                                                            nation = data3['data'][0].get('nation')

                                                            # BASE_NATION 국민인 경우에만 콜사인 적용
                                                            if nation == BASE_NATION:
                                                                # 역할별 양식 확인 (가장 높은 우선순위 역할)
                                                                role_format = None
                                                                if isinstance(member, discord.Member):
                                                                    # 역할 우선순위 순으로 정렬 (position이 높을수록 우선순위가 높음)
                                                                    sorted_roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
                                                                    for role in sorted_roles:
                                                                        format_str = callsign_manager.get_role_format(role.id)
                                                                        if format_str:
                                                                            role_format = format_str
                                                                            applied_format = f"{role.name} 역할 양식"
                                                                            print(f"  🎭 역할 양식 적용: {role.name} - {format_str}")
                                                                            break

                                                                # 닉네임 생성
                                                                if role_format:
                                                                    # 역할 양식이 있으면 양식 적용
                                                                    new_nickname = callsign_manager.apply_format_to_nickname(
                                                                        role_format,
                                                                        mc_id=mc_id,
                                                                        nation=nation,
                                                                        town=town,
                                                                        callsign=텍스트
                                                                    )
                                                                else:
                                                                    # 기본 양식 사용
                                                                    new_nickname = f"{mc_id} ㅣ {텍스트}"

                                                                # 닉네임 변경 시도
                                                                try:
                                                                    await member.edit(nick=new_nickname)
                                                                    nickname_updated = True
                                                                    print(f"✅ 콜사인 적용으로 닉네임 변경: {new_nickname}")
                                                                except discord.Forbidden:
                                                                    nickname_error = "닉네임 변경 권한이 없습니다."
                                                                    print(f"⚠️ 닉네임 변경 권한 없음")
                                                                except Exception as e:
                                                                    nickname_error = f"닉네임 변경 실패: {str(e)[:50]}"
                                                                    print(f"⚠️ 닉네임 변경 실패: {e}")
                                                            else:
                                                                nickname_error = f"{BASE_NATION} 국민만 콜사인을 사용할 수 있습니다."
        except Exception as e:
            print(f"⚠️ 콜사인 즉시 적용 중 오류: {e}")
            nickname_error = "마인크래프트 계정 정보를 확인할 수 없습니다."

        # {CC} 포함 역할 찾기
        cc_role = None
        if isinstance(member, discord.Member):
            for role in member.roles:
                format_str = callsign_manager.get_role_format(role.id)
                if format_str and '{CC}' in format_str:
                    cc_role = role
                    break

        # 결과 메시지 생성
        if cc_role:
            # {CC} 역할이 있는 경우
            embed = discord.Embed(
                title="✅ 콜사인 적용 완료",
                description=f"{cc_role.mention} 콜사인 적용 완료",
                color=0x00ff00
            )
        else:
            # {CC} 역할이 없는 경우
            embed = discord.Embed(
                title="✅ 콜사인 설정 완료",
                description=f"콜사인이 **{텍스트}**로 설정되었습니다.",
                color=0x00ff00
            )

        # 쿨타임 정보
        embed.add_field(
            name="⏰ 쿨타임 적용",
            value="15일 후에 다시 변경할 수 있습니다.",
            inline=False
        )

        # 닉네임 변경 결과
        if nickname_updated:
            if mc_id:
                # 실제 적용된 닉네임 가져오기
                actual_nickname = member.display_name
                embed.add_field(
                    name="🔄 닉네임 변경",
                    value=f"• 닉네임이 **``{actual_nickname}``**로 즉시 변경됨",
                    inline=False
                )
                embed.add_field(
                    name="💡 안내",
                    value=f"• {BASE_NATION} 국민이므로 콜사인이 즉시 적용되었습니다.\n• 마인크래프트 정보가 변경되면 `/확인` 명령어를 사용하세요.",
                    inline=False
                )

                # 역할 양식이 적용되었는지 표시
                if applied_format:
                    embed.add_field(
                        name="🎭 적용된 양식",
                        value=f"**{applied_format}**이 적용되었습니다.",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🏷️ 적용된 닉네임 형식",
                        value=f"**성공:** `{mc_id} | {{{텍스트}}}`",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="🔄 닉네임 변경",
                    value=f"• 닉네임이 **``{텍스트}``** 콜사인으로 즉시 변경됨",
                    inline=False
                )
                embed.add_field(
                    name="💡 안내",
                    value=f"• {BASE_NATION} 국민이므로 콜사인이 즉시 적용되었습니다.\n• 마인크래프트 정보가 변경되면 `/확인` 명령어를 사용하세요.",
                    inline=False
                )
        elif nickname_error:
            embed.add_field(
                name="⚠️ 닉네임 변경 실패",
                value=f"{nickname_error}\n`/확인` 명령어를 사용하여 수동으로 적용해주세요.",
                inline=False
            )
            # mc_id가 있으면 실패 형식 표시
            if mc_id:
                embed.add_field(
                    name="🏷️ 권장 닉네임 형식",
                    value=f"**실패:** `{mc_id} | {{NN/TT}}`\n(NN은 국가명, TT는 마을명)",
                    inline=False
                )
            embed.add_field(
                name="ℹ️ 안내",
                value="다음 변경은 15일 후에 가능합니다.",
                inline=False
            )
        else:
            embed.add_field(
                name="ℹ️ 안내",
                value="다음 변경은 15일 후에 가능합니다.",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)
