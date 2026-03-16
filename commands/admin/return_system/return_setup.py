# /복귀설정 명령어 (관리자 전용) - 잠수 예외 유저 관리

import discord
from discord import app_commands
from typing import Literal

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


def is_return_manager(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    try:
        from return_config_manager import return_config_manager
        role_id = return_config_manager.get_manager_role()
        if role_id:
            return any(r.id == role_id for r in interaction.user.roles)
    except Exception:
        pass
    return False


def setup(bot):

    @bot.tree.command(name="복귀설정", description="잠수 예외 유저를 관리합니다")
    @app_commands.describe(
        기능="실행할 기능",
        유저="대상 유저 (예외추가/예외삭제 시 필수)"
    )
    @app_commands.check(is_return_manager)
    async def 복귀설정(
        interaction: discord.Interaction,
        기능: Literal["예외추가", "예외삭제", "예외목록"],
        유저: discord.Member = None
    ):
        await interaction.response.defer(ephemeral=True)

        if bot_logger:
            bot_logger.log_command("복귀설정", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.RETURN,
                                   details={"기능": 기능})

        try:
            from return_config_manager import return_config_manager

            # ── 예외 추가 ───────────────────────────────────────
            if 기능 == "예외추가":
                if not 유저:
                    await interaction.followup.send("❌ 유저를 지정해주세요.", ephemeral=True)
                    return

                if return_config_manager.is_exception(유저.id):
                    await interaction.followup.send(
                        f"⚠️ {유저.mention}은 이미 예외 목록에 있습니다.",
                        ephemeral=True
                    )
                    return

                return_config_manager.add_exception(유저.id)
                embed = discord.Embed(
                    title="✅ 예외 유저 추가됨",
                    description=f"**유저:** {유저.mention}\n\n이 유저는 잠수 체크에서 제외됩니다.",
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 예외 삭제 ───────────────────────────────────────
            elif 기능 == "예외삭제":
                if not 유저:
                    await interaction.followup.send("❌ 유저를 지정해주세요.", ephemeral=True)
                    return

                if not return_config_manager.is_exception(유저.id):
                    await interaction.followup.send(
                        f"⚠️ {유저.mention}은 예외 목록에 없습니다.",
                        ephemeral=True
                    )
                    return

                return_config_manager.remove_exception(유저.id)
                embed = discord.Embed(
                    title="✅ 예외 유저 제거됨",
                    description=f"**유저:** {유저.mention}\n\n이 유저는 이제 잠수 체크 대상입니다.",
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 예외 목록 ───────────────────────────────────────
            elif 기능 == "예외목록":
                exceptions = return_config_manager.get_exceptions()

                embed = discord.Embed(title="🚫 잠수 예외 유저 목록", color=0x3498db)

                if not exceptions:
                    embed.description = "예외 유저가 없습니다."
                else:
                    lines = []
                    for uid in exceptions:
                        m = interaction.guild.get_member(uid)
                        lines.append(f"• {m.mention if m else f'<@{uid}>'} (`{uid}`)")
                    embed.description = "\n".join(lines)
                    embed.set_footer(text=f"총 {len(exceptions)}명")

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)

    @복귀설정.error
    async def 복귀설정_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ 권한 없음", description="복귀 관리자 역할 또는 관리자만 사용 가능합니다.", color=0xff0000),
                ephemeral=True
            )
