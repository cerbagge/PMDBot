# commands/admin/scheduler/exception.py
# /예외설정 명령어 - 자동실행 예외 대상 관리

import discord
from discord import app_commands
from typing import Literal

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def setup(bot):
    """봇에 /예외설정 명령어 등록"""

    @bot.tree.command(name="예외설정", description="자동실행 예외 대상을 관리합니다")
    @app_commands.describe(
        기능="추가: 예외 추가 | 제거: 예외 제거 | 목록: 예외 목록 확인",
        유저="예외 대상 사용자"
    )
    @app_commands.check(is_admin)
    async def 예외설정(
        interaction: discord.Interaction,
        기능: Literal["추가", "제거", "목록"],
        유저: discord.Member = None
    ):
        """자동실행 예외 대상 관리"""
        try:
            from exception_manager import exception_manager
        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="exception_manager 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if 기능 == "추가":
            if not 유저:
                embed = discord.Embed(
                    title="❌ 오류",
                    description="예외로 추가할 사용자를 선택해주세요.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # 예외 추가
            success = exception_manager.add_exception(유저.id)
            if success:
                embed = discord.Embed(
                    title="✅ 예외 추가 완료",
                    description=f"{유저.mention}님을 자동실행 예외 대상으로 추가했습니다.",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="⚠️ 알림",
                    description=f"{유저.mention}님은 이미 예외 대상입니다.",
                    color=0xff9900
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif 기능 == "제거":
            if not 유저:
                embed = discord.Embed(
                    title="❌ 오류",
                    description="예외에서 제거할 사용자를 선택해주세요.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # 예외 제거
            success = exception_manager.remove_exception(유저.id)
            if success:
                embed = discord.Embed(
                    title="✅ 예외 제거 완료",
                    description=f"{유저.mention}님을 자동실행 예외 대상에서 제거했습니다.",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="⚠️ 알림",
                    description=f"{유저.mention}님은 예외 대상이 아닙니다.",
                    color=0xff9900
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif 기능 == "목록":
            # 예외 목록 조회
            exceptions = exception_manager.get_exceptions()

            embed = discord.Embed(
                title="📋 자동실행 예외 목록",
                color=0x3498db
            )

            if exceptions:
                # 각 예외 사용자 정보 표시
                exception_list = []
                for discord_id in exceptions:
                    member = interaction.guild.get_member(discord_id)
                    if member:
                        exception_list.append(f"• {member.mention} (`{member.name}`)")
                    else:
                        exception_list.append(f"• <@{discord_id}> (서버에 없음)")

                embed.description = "\n".join(exception_list)
                embed.set_footer(text=f"총 {len(exceptions)}명")
            else:
                embed.description = "예외 대상이 없습니다."

            await interaction.response.send_message(embed=embed, ephemeral=True)

    # 에러 핸들러
    @예외설정.error
    async def 예외설정_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
