# commands/admin/queue/queue_status.py
# /대기열상태 명령어 - 현재 대기열 상태를 확인

import discord
from discord import app_commands

# 안전한 import 처리
try:
    from queue_manager import queue_manager
except ImportError:
    # 더미 queue_manager 클래스 생성
    class DummyQueueManager:
        def get_queue_size(self): return 0
        def is_processing(self): return False
        def add_user(self, user_id): return True
        def clear_queue(self): return 0
    queue_manager = DummyQueueManager()

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None

try:
    from utils import format_estimated_time
except ImportError:
    def format_estimated_time(count, seconds_per_user=20):
        total_seconds = count * seconds_per_user
        if total_seconds < 60:
            return f"약 {total_seconds}초"
        minutes = total_seconds // 60
        return f"약 {minutes}분"

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
    """봇에 /대기열상태 명령어 등록"""

    @bot.tree.command(name="대기열상태", description="현재 대기열 상태를 확인합니다")
    @app_commands.check(is_admin)
    async def 대기열상태(interaction: discord.Interaction):
        """대기열 상태 확인 명령어"""
        if bot_logger:
            bot_logger.log_command("대기열상태", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.COMMAND)

        queue_size = queue_manager.get_queue_size()
        is_processing = queue_manager.is_processing()

        embed = discord.Embed(
            title="📋 대기열 상태",
            color=0x00ff00 if queue_size == 0 else 0xffaa00
        )

        embed.add_field(
            name="🎯 현재 대기열",
            value=f"**{queue_size}명** 대기 중",
            inline=True
        )

        status_text = "🔄 처리 중" if is_processing else "⏸️ 대기 중"
        embed.add_field(
            name="📊 처리 상태",
            value=status_text,
            inline=True
        )

        if queue_size > 0:
            # utils.py의 format_estimated_time 함수 사용 (20초/명)
            time_str = format_estimated_time(queue_size, 20)
            embed.add_field(
                name="⏰ 예상 완료 시간",
                value=time_str,
                inline=True
            )
        else:
            embed.add_field(
                name="⏰ 예상 완료 시간",
                value="대기열이 비어있습니다",
                inline=True
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
