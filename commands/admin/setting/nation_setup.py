# commands/admin/setting/nation_setup.py
# /국가설정 명령어 - 서버 BASE_NATION 설정

import discord
from discord import app_commands
import datetime

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None

# 서버 소유자 권한 체크 함수
def is_owner(interaction: discord.Interaction) -> bool:
    """서버 소유자인지 체크"""
    return interaction.guild.owner_id == interaction.user.id


def setup(bot):
    """봇에 /국가설정 명령어 등록"""

    @bot.tree.command(name="국가설정", description="국가를 설정하는 명령어")
    @app_commands.describe(국가="설정할 국가 이름")
    @app_commands.check(is_owner)
    async def 국가설정(interaction: discord.Interaction, 국가: str):
        """[관리자] 서버 BASE_NATION 설정"""
        await interaction.response.defer()

        if bot_logger:
            bot_logger.log_command("국가설정", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.ADMIN,
                                   details={"국가": 국가})

        try:
            from config import config

            # config의 set_base_nation 메소드 사용
            success, message, uuid = await config.set_base_nation(국가)

            if success:
                embed = discord.Embed(
                    title="✅ 서버 국가 설정 완료",
                    description=message,
                    color=0x00ff00,
                    timestamp=datetime.datetime.now()
                )

                embed.add_field(
                    name="📍 설정된 국가",
                    value=f"**{config.BASE_NATION}**",
                    inline=True
                )

                embed.add_field(
                    name="🆔 UUID",
                    value=f"`{uuid}`",
                    inline=False
                )

                embed.set_footer(text=f"관리자: {interaction.user.name}")

            else:
                embed = discord.Embed(
                    title="❌ 국가 설정 실패",
                    description=message,
                    color=0xff0000,
                    timestamp=datetime.datetime.now()
                )
                embed.set_footer(text="정확한 국가명을 입력해주세요")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            error_embed = discord.Embed(
                title="❌ 오류 발생",
                description=f"국가 설정 중 오류가 발생했습니다:\n```{str(e)}```",
                color=0xff0000
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
