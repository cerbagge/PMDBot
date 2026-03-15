# commands/admin/scheduler/newbie_check.py
# /뉴비확인 명령어 - 뉴비 목록을 실시간으로 표시하는 메시지 생성

import discord
from discord import app_commands
from datetime import datetime

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


async def build_newbie_list_embed(guild: discord.Guild) -> discord.Embed:
    """뉴비 목록 임베드 생성"""
    from newbie_config_manager import newbie_config_manager
    from database_manager import db_manager

    embed = discord.Embed(
        title="🆕 현재 뉴비 목록",
        color=0x00ff00,
        timestamp=datetime.now()
    )

    # 뉴비 역할 가져오기
    newbie_role_id = newbie_config_manager.get_newbie_role()
    if not newbie_role_id:
        embed.description = "❌ 뉴비 역할이 설정되지 않았습니다.\n`/뉴비설정 기능:뉴비역할`로 설정해주세요."
        return embed

    newbie_role = guild.get_role(newbie_role_id)
    if not newbie_role:
        embed.description = f"❌ 뉴비 역할을 찾을 수 없습니다. (ID: {newbie_role_id})"
        return embed

    # 뉴비 역할을 가진 멤버 목록
    newbie_members = newbie_role.members

    if not newbie_members:
        embed.description = "현재 뉴비가 없습니다."
        embed.add_field(
            name="📊 통계",
            value=f"**뉴비 역할:** {newbie_role.mention}\n**현재 뉴비 수:** 0명",
            inline=False
        )
        return embed

    # 뉴비 목록 생성 (가입일 기준 정렬)
    newbie_list = []
    for member in newbie_members:
        # DB에서 가입일 조회
        joined_date = None
        mc_name = None
        try:
            user_info = db_manager.get_user_info(member.id)
            if user_info:
                joined_date = user_info.get('red_mafia_joined')
                mc_name = user_info.get('current_minecraft_name')
        except:
            pass

        newbie_list.append({
            'member': member,
            'mc_name': mc_name or '?',
            'joined_date': joined_date
        })

    # 가입일 기준 정렬 (최신 먼저)
    newbie_list.sort(key=lambda x: x['joined_date'] or datetime.min, reverse=True)

    # 목록 텍스트 생성
    list_text = []
    for i, newbie in enumerate(newbie_list, 1):
        member = newbie['member']
        mc_name = newbie['mc_name']
        joined_date = newbie['joined_date']

        # 가입일 포맷
        if joined_date:
            days_ago = (datetime.now() - joined_date).days
            days_left = 14 - days_ago
            if days_ago == 0:
                date_text = "오늘"
            elif days_ago == 1:
                date_text = "어제"
            else:
                date_text = f"{days_ago}일 전"

            # 남은 일수 표시
            if days_left > 0:
                date_text += f" (D-{days_left})"
            else:
                date_text += " (만료 예정)"
        else:
            date_text = "?"

        list_text.append(f"`{i}.` {member.mention} | `{mc_name}` | {date_text}")

    # 10명씩 나눠서 필드에 추가
    chunk_size = 10
    for i in range(0, len(list_text), chunk_size):
        chunk = list_text[i:i + chunk_size]
        field_name = f"📋 뉴비 목록 ({i + 1}-{min(i + chunk_size, len(list_text))})"
        embed.add_field(
            name=field_name,
            value="\n".join(chunk),
            inline=False
        )

    # 통계
    embed.add_field(
        name="📊 통계",
        value=f"**뉴비 역할:** {newbie_role.mention}\n**현재 뉴비 수:** {len(newbie_members)}명",
        inline=False
    )

    embed.set_footer(text="이 메시지는 뉴비 가입/탈퇴 시 자동으로 업데이트됩니다")

    return embed


async def update_newbie_list_message(bot):
    """저장된 뉴비 목록 메시지 업데이트"""
    try:
        from newbie_config_manager import newbie_config_manager
        from config import config

        channel_id, message_id = newbie_config_manager.get_list_message()
        if not channel_id or not message_id:
            return False

        guild = bot.get_guild(config.GUILD_ID)
        if not guild:
            return False

        channel = guild.get_channel(channel_id)
        if not channel:
            print(f"  ⚠️ 뉴비 목록 채널을 찾을 수 없음: {channel_id}")
            newbie_config_manager.clear_list_message()
            return False

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            print(f"  ⚠️ 뉴비 목록 메시지를 찾을 수 없음: {message_id}")
            newbie_config_manager.clear_list_message()
            return False

        # 새 임베드 생성
        embed = await build_newbie_list_embed(guild)

        # 메시지 수정
        await message.edit(embed=embed)
        print(f"  📝 뉴비 목록 메시지 업데이트됨")
        return True

    except Exception as e:
        print(f"  ⚠️ 뉴비 목록 메시지 업데이트 실패: {e}")
        return False


def setup(bot):
    """봇에 /뉴비확인 명령어 등록"""

    @bot.tree.command(name="뉴비확인", description="현재 뉴비 목록을 표시하고 실시간으로 업데이트되는 메시지를 생성합니다")
    @app_commands.check(is_admin)
    async def 뉴비확인(interaction: discord.Interaction):
        """뉴비 목록 확인"""
        await interaction.response.defer()

        try:
            from newbie_config_manager import newbie_config_manager

            # 임베드 생성
            embed = await build_newbie_list_embed(interaction.guild)

            # 메시지 전송
            message = await interaction.followup.send(embed=embed, wait=True)

            # 메시지 ID 저장
            newbie_config_manager.set_list_message(interaction.channel.id, message.id)

            # 확인 메시지 (ephemeral)
            await interaction.followup.send(
                f"✅ 뉴비 목록 메시지가 생성되었습니다.\n"
                f"이 메시지는 뉴비 가입/탈퇴 시 자동으로 업데이트됩니다.\n"
                f"메시지 ID: `{message.id}`",
                ephemeral=True
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)

    # 에러 핸들러
    @뉴비확인.error
    async def 뉴비확인_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
