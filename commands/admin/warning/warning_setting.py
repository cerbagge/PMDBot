# commands/admin/warning/warning_setting.py
# /경고설정 명령어 - 경고 시스템 설정 (관리자 전용)

import discord
from discord import app_commands
from typing import Literal
import datetime
import json
import re

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


# 관리자 권한 체크 함수
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def is_valid_punishment(action: str) -> bool:
    """처벌 액션 유효성 검증"""
    if action in ('kick', 'ban'):
        return True
    if re.match(r'^mute_\d+[hm]$', action):
        return True
    return False


def setup(bot):
    """봇에 /경고설정 명령어 등록"""

    @bot.tree.command(name="경고설정", description="경고 시스템 설정을 관리합니다")
    @app_commands.describe(
        기능="실행할 기능 선택",
        채널="로그 채널 (채널 설정 시)",
        텍스트="설정 값 (처벌설정 시)"
    )
    @app_commands.check(is_admin)
    async def 경고설정(
        interaction: discord.Interaction,
        기능: Literal["채널", "처벌설정", "설정조회"],
        채널: discord.TextChannel = None,
        텍스트: str = None
    ):
        """경고 시스템 설정 - 관리자 전용"""
        if bot_logger:
            bot_logger.log_command("경고설정", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.WARNING_SYS,
                                   details={"기능": 기능})

        from database_manager import db_manager

        guild_id = interaction.guild.id

        # ===== 채널 설정 =====
        if 기능 == "채널":
            target_channel = 채널 or interaction.channel

            success = db_manager.set_warning_log_channel(guild_id, target_channel.id)

            embed = discord.Embed(
                title="✅ 경고 로그 채널 설정" if success else "❌ 설정 실패",
                description=f"**채널:** {target_channel.mention}\n\n경고 추가/제거 시 이 채널에 로그가 전송됩니다.",
                color=0x00ff00 if success else 0xff0000,
                timestamp=datetime.datetime.now()
            )
            embed.set_footer(text=f"처리자: {interaction.user.name}")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ===== 처벌 설정 =====
        elif 기능 == "처벌설정":
            if not 텍스트:
                await interaction.response.send_message(
                    "처벌 설정 형식을 입력해주세요.\n\n"
                    "**형식:** `경고횟수:처벌, 경고횟수:처벌, ...`\n"
                    "**예시:** `3:mute_1h, 5:kick, 7:ban`\n\n"
                    "**사용 가능한 처벌:**\n"
                    "- `mute_Xh` : X시간 타임아웃 (예: mute_1h, mute_24h)\n"
                    "- `mute_Xm` : X분 타임아웃 (예: mute_30m)\n"
                    "- `kick` : 서버 추방\n"
                    "- `ban` : 서버 차단\n\n"
                    "**초기화:** `없음` 또는 `reset` 입력",
                    ephemeral=True
                )
                return

            punishments = {}
            if 텍스트.lower() in ('없음', 'reset', 'none', '초기화'):
                punishments = {}
            else:
                try:
                    punishments = json.loads(텍스트)
                except json.JSONDecodeError:
                    for item in 텍스트.split(','):
                        item = item.strip()
                        if ':' in item:
                            count_str, action = item.split(':', 1)
                            count_str = count_str.strip()
                            action = action.strip().lower()
                            if count_str.isdigit() and is_valid_punishment(action):
                                punishments[count_str] = action
                            else:
                                await interaction.response.send_message(
                                    f"❌ 잘못된 형식: `{item}`\n"
                                    f"사용 가능: `mute_Xh`, `mute_Xm`, `kick`, `ban`",
                                    ephemeral=True
                                )
                                return
                        else:
                            await interaction.response.send_message(
                                f"❌ 잘못된 형식: `{item}`\n형식: `경고횟수:처벌`",
                                ephemeral=True
                            )
                            return

            punishments_json = json.dumps(punishments, ensure_ascii=False)
            success = db_manager.set_warning_punishments(guild_id, punishments_json)

            if punishments:
                display_lines = []
                for count, action in sorted(punishments.items(), key=lambda x: int(x[0])):
                    display_lines.append(f"**{count}회** -> `{action}`")
                display_text = "\n".join(display_lines)
            else:
                display_text = "자동 처벌 없음"

            embed = discord.Embed(
                title="✅ 처벌 설정 완료" if success else "❌ 설정 실패",
                description=f"**자동 처벌 규칙:**\n{display_text}",
                color=0x00ff00 if success else 0xff0000,
                timestamp=datetime.datetime.now()
            )
            embed.set_footer(text=f"처리자: {interaction.user.name}")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ===== 설정 조회 =====
        elif 기능 == "설정조회":
            config_data = db_manager.get_warning_config(guild_id)

            embed = discord.Embed(
                title="⚙️ 경고 시스템 설정",
                color=0x3498db
            )

            # 로그 채널
            log_ch_id = config_data.get('log_channel_id')
            if log_ch_id:
                channel = interaction.guild.get_channel(log_ch_id)
                ch_text = channel.mention if channel else f"❌ 알 수 없는 채널 ({log_ch_id})"
            else:
                ch_text = "❌ 설정되지 않음"
            embed.add_field(name="📢 로그 채널", value=ch_text, inline=False)

            # 처벌 규칙
            punishments_str = config_data.get('punishments', '{}')
            try:
                punishments = json.loads(punishments_str) if isinstance(punishments_str, str) else punishments_str
            except:
                punishments = {}

            if punishments:
                punishment_lines = []
                for count, action in sorted(punishments.items(), key=lambda x: int(x[0])):
                    punishment_lines.append(f"**{count}회** -> `{action}`")
                embed.add_field(name="🔨 자동 처벌 규칙", value="\n".join(punishment_lines), inline=False)
            else:
                embed.add_field(name="🔨 자동 처벌 규칙", value="설정되지 않음", inline=False)

            # 마지막 변경
            updated = config_data.get('updated_at')
            if updated:
                if isinstance(updated, datetime.datetime):
                    embed.set_footer(text=f"마지막 설정 변경: {updated.strftime('%Y-%m-%d %H:%M')}")
                else:
                    embed.set_footer(text=f"마지막 설정 변경: {str(updated)[:16]}")

            await interaction.response.send_message(embed=embed, ephemeral=True)

    # 에러 핸들러
    @경고설정.error
    async def 경고설정_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
