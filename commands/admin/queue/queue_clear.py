# commands/admin/queue/queue_clear.py
# /대기열초기화 명령어 - 대기열을 모두 비움

import discord
from discord import app_commands

# 안전한 import 처리
try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None

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
    """봇에 /대기열초기화 명령어 등록"""

    @bot.tree.command(name="대기열초기화", description="대기열을 모두 비웁니다")
    @app_commands.check(is_admin)
    async def 대기열초기화(interaction: discord.Interaction):
        """대기열 초기화 명령어"""
        if bot_logger:
            bot_logger.log_command("대기열초기화", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.QUEUE)

        cleared_count = queue_manager.clear_queue()

        embed = discord.Embed(
            title="🧹 대기열 초기화 완료",
            description=f"**{cleared_count}명**이 대기열에서 제거되었습니다.",
            color=0xff6600
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
