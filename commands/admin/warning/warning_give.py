# commands/admin/warning/warning_give.py
# /경고 명령어 - 경고 부여 전용 (관리자 전용)

import discord
from discord import app_commands
import datetime

from commands.admin.warning.warning_manage import (
    is_admin,
    send_warning_log,
    check_and_apply_punishment,
)

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


def setup(bot):
    """봇에 /경고 명령어 등록"""

    @bot.tree.command(name="경고", description="유저에게 경고를 부여합니다")
    @app_commands.describe(
        유저="경고할 대상 사용자",
        사유="경고 사유",
        횟수="한 번에 부여할 경고 수 (기본: 1)"
    )
    @app_commands.check(is_admin)
    async def 경고(
        interaction: discord.Interaction,
        유저: discord.Member,
        사유: str = None,
        횟수: int = 1
    ):
        """경고 부여 명령어 - 관리자 전용"""
        from database_manager import db_manager

        await interaction.response.defer(ephemeral=False)

        if bot_logger:
            bot_logger.log_command("경고", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.WARNING_SYS,
                                   details={"대상": 유저.name, "사유": 사유 or "사유 없음"},
                                   target_user_id=유저.id, target_user_name=유저.name)

        guild_id = interaction.guild.id
        reason = 사유 or "사유 없음"

        # 횟수 검증 (0 이상 정수)
        if 횟수 < 0:
            await interaction.followup.send("❌ 횟수는 0 이상의 정수를 입력해주세요.", ephemeral=True)
            return

        if 횟수 == 0:
            await interaction.followup.send("❌ 횟수가 0이므로 경고가 부여되지 않았습니다.", ephemeral=True)
            return

        # 경고 부여 (1개의 레코드에 count로 횟수 저장)
        warning = db_manager.add_warning(guild_id, 유저.id, interaction.user.id, reason, count=횟수)

        if not warning:
            await interaction.followup.send("❌ 경고 추가에 실패했습니다.", ephemeral=True)
            return

        active_count = db_manager.get_active_warning_count(guild_id, 유저.id)

        # 로그 채널에 1건 전송
        await send_warning_log(interaction.guild, db_manager, guild_id, warning, 유저)

        # 처리자 정보
        user_info = db_manager.get_user_info(interaction.user.id)
        if user_info and user_info.get('current_minecraft_name'):
            handler_mc = user_info['current_minecraft_name']
            handler_text = f"{interaction.user.mention} - `{handler_mc}@{interaction.user.name}({interaction.user.id})`"
        else:
            handler_text = f"{interaction.user.mention} - `{interaction.user.display_name}@{interaction.user.name}({interaction.user.id})`"

        # 대상 정보
        target_info = db_manager.get_user_info(유저.id)
        if target_info and target_info.get('current_minecraft_name'):
            target_mc = target_info['current_minecraft_name']
            target_text = f"{유저.mention} - `{target_mc}@{유저.name}({유저.id})`"
        else:
            target_text = f"{유저.mention} - `{유저.display_name}@{유저.name}({유저.id})`"

        # 공개 응답 임베드
        embed = discord.Embed(
            title=f"경고 #{warning['id']}",
            color=0xff9900,
            timestamp=datetime.datetime.now()
        )

        embed.add_field(name="👮처리자", value=handler_text, inline=False)
        embed.add_field(name="👤대상", value=target_text, inline=False)
        embed.add_field(name="📝사유", value=reason, inline=True)
        embed.add_field(
            name="⚠️누적 경고 개수",
            value=f"{active_count} (+{횟수})",
            inline=True
        )

        await interaction.followup.send(embed=embed)

        # 최종 활성 경고 수 기준으로 자동 처벌 체크
        await check_and_apply_punishment(interaction.guild, 유저, active_count, db_manager, guild_id)

        # 부계정에도 동일 경고 동기화
        try:
            from commands.admin.alt_account.alt_account import _get_linked_ids
            linked_ids = _get_linked_ids(유저.id)
            for uid in linked_ids:
                alt_warning = db_manager.add_warning(guild_id, uid, interaction.user.id, f"[부계동기화] {reason}", count=횟수)
                if alt_warning:
                    alt_active = db_manager.get_active_warning_count(guild_id, uid)
                    alt_member = interaction.guild.get_member(uid)
                    if alt_member:
                        await check_and_apply_punishment(interaction.guild, alt_member, alt_active, db_manager, guild_id)
        except Exception:
            pass

    @경고.error
    async def 경고_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
