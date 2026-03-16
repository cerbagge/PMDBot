# commands/admin/scheduler/auto_role.py
# /자동실행 명령어 - 자동 등록할 역할을 설정

import discord
from discord import app_commands

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def setup(bot):
    """봇에 /자동실행 명령어 등록"""

    @bot.tree.command(name="자동실행", description="자동 등록할 역할을 설정")
    @app_commands.describe(역할id="역할 ID")
    @app_commands.check(is_admin)
    async def 자동실행(interaction: discord.Interaction, 역할id: str):
        """자동실행 역할 추가"""
        if bot_logger:
            bot_logger.log_command("자동실행", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.SCHEDULER,
                                   details={"역할id": 역할id})
        try:
            # 역할 ID 검증
            try:
                role_id_int = int(역할id)
            except ValueError:
                await interaction.response.send_message("❌ 유효하지 않은 역할 ID입니다. 숫자를 입력해주세요.", ephemeral=True)
                return

            # 역할 존재 확인
            role = interaction.guild.get_role(role_id_int)
            if not role:
                await interaction.response.send_message(f"❌ 역할을 찾을 수 없습니다 (ID: {역할id})", ephemeral=True)
                return

            # auto_role_manager를 통해 추가
            from role_manager import auto_role_manager

            # 이미 추가되어 있는지 확인
            if auto_role_manager.has_role(role_id_int):
                await interaction.response.send_message(
                    f"⚠️ {role.mention}은(는) 이미 자동실행 목록에 있습니다.",
                    ephemeral=True
                )
                return

            # 역할 추가
            success = auto_role_manager.add_role(role_id_int)

            if success:
                embed = discord.Embed(
                    title="✅ 자동실행 역할 추가 완료",
                    description=f"**역할:** {role.mention}\n"
                               f"**역할 ID:** `{역할id}`\n"
                               f"**멤버 수:** {len(role.members)}명",
                    color=0x00ff00
                )
                embed.add_field(
                    name="📊 자동실행 목록 현황",
                    value=f"총 {auto_role_manager.get_count()}개 역할이 자동실행 목록에 있습니다.",
                    inline=False
                )
                embed.add_field(
                    name="💡 안내",
                    value="• 역할이 즉시 적용되었습니다. 재시작이 필요 없습니다.\n"
                         "• 다음 자동 스케줄 실행 시 이 역할의 멤버들이 자동으로 처리됩니다.\n"
                         "• `/자동실행시작` 명령어로 즉시 실행할 수 있습니다.",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ 역할 추가에 실패했습니다.", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {str(e)}", ephemeral=True)

    # 에러 핸들러
    @자동실행.error
    async def 자동실행_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
