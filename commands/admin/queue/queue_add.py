# commands/admin/queue/queue_add.py
# /대기열추가 명령어 - 유저 또는 역할의 멤버들을 대기열에 추가

import discord
from discord import app_commands
from log_manager import get_logger

logger = get_logger("queue_add")

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
    """봇에 /대기열추가 명령어 등록"""

    @bot.tree.command(name="대기열추가", description="유저 또는 역할의 멤버들을 대기열에 추가합니다")
    @app_commands.describe(
        선택="추가할 대상 유형",
        유저="추가할 유저 (선택이 '유저'일 때 사용)",
        역할="추가할 역할의 모든 멤버 (선택이 '역할'일 때 사용)"
    )
    @app_commands.choices(선택=[
        app_commands.Choice(name="유저", value="user"),
        app_commands.Choice(name="역할", value="role")
    ])
    @app_commands.check(is_admin)
    async def 대기열추가(
        interaction: discord.Interaction,
        선택: app_commands.Choice[str],
        유저: discord.Member = None,
        역할: discord.Role = None
    ):
        """유저 또는 역할의 멤버들을 대기열에 추가"""
        members = []
        target_name = None
        target_type = None

        # 선택에 따라 처리
        if 선택.value == "user":
            if not 유저:
                await interaction.response.send_message(
                    "❌ **유저**를 선택했지만 유저를 멘션하지 않았습니다.\n"
                    "**사용법**: `/대기열추가 선택:유저 유저:@유저멘션`",
                    ephemeral=True
                )
                return

            members.append(유저)
            target_name = 유저.display_name
            target_type = "유저"
            logger.info(f"유저 감지: {유저.display_name} ({유저.id})")

        elif 선택.value == "role":
            if not 역할:
                await interaction.response.send_message(
                    "❌ **역할**을 선택했지만 역할을 멘션하지 않았습니다.\n"
                    "**사용법**: `/대기열추가 선택:역할 역할:@역할멘션`",
                    ephemeral=True
                )
                return

            members.extend(역할.members)
            target_name = 역할.name
            target_type = "역할"
            logger.info(f"역할 감지: {역할.name} ({len(members)}명)")

            if not members:
                await interaction.response.send_message(
                    f"❌ **{역할.name}** 역할에 멤버가 없습니다.",
                    ephemeral=True
                )
                return

        logger.info(f"처리할 멤버 수: {len(members)}")

        # 대기열 추가 처리
        await interaction.response.defer(thinking=True)

        if bot_logger:
            bot_logger.log_command("대기열추가", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.QUEUE_ADD,
                                   details={"선택": 선택.value})

        added_count = 0
        already_in_queue = 0

        # 대기열에 사용자 추가
        for member in members:
            try:
                if queue_manager.add_user(member.id):
                    added_count += 1
                    logger.info(f"대기열 추가: {member.display_name} ({member.id})")
                    if bot_logger:
                        bot_logger.log_queue(
                            f"대기열 추가: {member.display_name}",
                            user_id=interaction.user.id, user_name=interaction.user.name,
                            target_user_id=member.id, target_user_name=member.display_name,
                            source="admin_command", action="queue_add",
                            command="대기열추가", details={"선택": 선택.value}
                        )
                else:
                    already_in_queue += 1
                    logger.info(f"이미 대기 중: {member.display_name} ({member.id})")
            except Exception as e:
                logger.error(f"대기열 추가 실패 ({member.display_name}): {e}")
                already_in_queue += 1

        # 결과 메시지 생성
        embed = discord.Embed(
            title="🔄 대기열 추가 완료",
            color=0x00ff00
        )

        if target_type == "유저":
            embed.description = f"**{target_name}** 사용자 처리"
        else:
            embed.description = f"**{target_name}** 역할 멤버 {len(members)}명 처리"

        embed.add_field(
            name="📋 처리 현황",
            value=f"• 새로 추가: **{added_count}명**\n• 이미 대기 중: **{already_in_queue}명**",
            inline=False
        )

        current_queue_size = queue_manager.get_queue_size()
        processing_status = "처리 중" if queue_manager.is_processing() else "대기 중"

        embed.add_field(
            name="🎯 대기열 상태",
            value=f"• 총 대기 인원: **{current_queue_size}명**\n• 현재 상태: **{processing_status}**",
            inline=False
        )

        if added_count > 0:
            # 예상 시간 계산
            time_str = format_estimated_time(current_queue_size)
            embed.add_field(
                name="⏰ 예상 처리 시간",
                value=f"{time_str}\n대기열이 10명 이상이면 자동으로 처리가 시작됩니다.",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)
