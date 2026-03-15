# commands/admin/scheduler/auto_start.py
# /자동실행시작 명령어 - 자동 역할 부여를 수동으로 시작

import discord
from discord import app_commands

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def setup(bot):
    """봇에 /자동실행시작 명령어 등록"""

    @bot.tree.command(name="자동실행시작", description="자동 역할 부여를 수동으로 시작합니다")
    @app_commands.check(is_admin)
    async def 자동실행시작(interaction: discord.Interaction):
        """자동 실행을 수동으로 시작"""
        try:
            from scheduler import manual_execute_auto_roles

            embed = discord.Embed(
                title="🔄 자동 실행 시작",
                description="자동 역할 부여를 시작합니다...",
                color=0x00ff00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

            # 자동 실행 함수 호출
            await manual_execute_auto_roles(bot)

            # 완료 메시지
            complete_embed = discord.Embed(
                title="✅ 자동 실행 완료",
                description="자동 역할 부여가 완료되었습니다.",
                color=0x00ff00
            )
            await interaction.followup.send(embed=complete_embed, ephemeral=True)

        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="scheduler 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 오류 발생",
                description=f"자동 실행 중 오류가 발생했습니다.\n{str(e)}",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
