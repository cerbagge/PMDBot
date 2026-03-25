# /복귀설정 명령어 (관리자 전용) - 잠수/복귀 시스템 설정 및 예외 유저 관리
#   기능:잠수역할     - 잠수 역할 설정
#   기능:복귀역할     - 복귀 역할 설정 (티켓 오픈 시 지급)
#   기능:관리자역할   - 복귀채팅 + 관리자 권한 역할 설정 (겸용)
#   기능:복귀핑채널   - 복귀 핑 채널 설정
#   기능:티켓카테고리 - 티켓 생성 카테고리 설정
#   기능:복귀신청패널 - 복귀신청 패널 전송
#   기능:설정확인    - 전체 설정 현황 확인
#   기능:예외추가    - 예외 유저 추가
#   기능:예외삭제    - 예외 유저 삭제
#   기능:예외목록    - 예외 유저 목록

import discord
from discord import app_commands

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

    @bot.tree.command(name="복귀설정", description="잠수/복귀 시스템을 설정하고 관리합니다")
    @app_commands.describe(
        기능="실행할 기능",
        유저="대상 유저 (예외추가/예외삭제 시 필수)",
        역할="역할 (역할 설정 항목에서 필수)",
        채널="채널 또는 카테고리 (채널/티켓카테고리/패널 시 사용)"
    )
    @app_commands.choices(기능=[
        app_commands.Choice(name="잠수역할",     value="잠수역할"),
        app_commands.Choice(name="복귀역할",     value="복귀역할"),
        app_commands.Choice(name="관리자역할",   value="관리자역할"),
        app_commands.Choice(name="복귀핑채널",   value="복귀핑채널"),
        app_commands.Choice(name="티켓카테고리", value="티켓카테고리"),
        app_commands.Choice(name="복귀신청패널",   value="복귀신청패널"),
        app_commands.Choice(name="설정확인",     value="설정확인"),
        app_commands.Choice(name="예외추가",     value="예외추가"),
        app_commands.Choice(name="예외삭제",     value="예외삭제"),
        app_commands.Choice(name="예외목록",     value="예외목록"),
    ])
    @app_commands.check(is_return_manager)
    async def 복귀설정(
        interaction: discord.Interaction,
        기능: app_commands.Choice[str],
        유저: discord.Member = None,
        역할: discord.Role = None,
        채널: discord.abc.GuildChannel = None
    ):
        await interaction.response.defer(ephemeral=True)

        if bot_logger:
            bot_logger.log_command("복귀설정", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.RETURN,
                                   details={"기능": 기능.value})

        try:
            from return_config_manager import return_config_manager

            val = 기능.value

            # ── 잠수 역할 ──────────────────────────────────────
            if val == "잠수역할":
                if not 역할:
                    await interaction.followup.send("❌ 역할을 지정해주세요.", ephemeral=True)
                    return
                return_config_manager.set_inactive_role(역할.id)
                embed = discord.Embed(
                    title="✅ 잠수 역할 설정 완료",
                    description=f"**역할:** {역할.mention}\n\n60일 이상 미접속 시 이 역할이 부여됩니다.",
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 복귀 역할 (티켓 신청 중) ────────────────────────
            elif val == "복귀역할":
                if not 역할:
                    await interaction.followup.send("❌ 역할을 지정해주세요.", ephemeral=True)
                    return
                return_config_manager.set_return_role(역할.id)
                embed = discord.Embed(
                    title="✅ 복귀 역할 설정 완료",
                    description=f"**역할:** {역할.mention}\n\n티켓 오픈 시 이 역할이 부여됩니다.",
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 관리자역할 (복귀채팅 + 관리자 권한 겸용) ────────
            elif val == "관리자역할":
                if not 역할:
                    await interaction.followup.send("❌ 역할을 지정해주세요.", ephemeral=True)
                    return
                return_config_manager.set_return_chat_role(역할.id)
                return_config_manager.set_manager_role(역할.id)
                embed = discord.Embed(
                    title="✅ 관리자 역할 설정 완료",
                    description=(
                        f"**역할:** {역할.mention}\n\n"
                        f"• 잠수 처리 시 이 역할이 함께 부여됩니다 (복귀채팅 접근)\n"
                        f"• `/복귀설정`, `/복귀확인` 명령어와 티켓 닫기 버튼 사용 가능\n"
                        f"• 티켓 생성 시 이 역할이 멘션됩니다"
                    ),
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 복귀 핑 채널 설정 ────────────────────────────────
            elif val == "복귀핑채널":
                if not 채널:
                    채널 = interaction.channel
                if not isinstance(채널, discord.TextChannel):
                    await interaction.followup.send("❌ 텍스트 채널을 지정해주세요.", ephemeral=True)
                    return
                return_config_manager.set_daily_channel(채널.id)
                embed = discord.Embed(
                    title="✅ 복귀 핑 채널 설정 완료",
                    description=f"**채널:** {채널.mention}",
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 티켓 카테고리 설정 ──────────────────────────────
            elif val == "티켓카테고리":
                if not 채널:
                    await interaction.followup.send("❌ 카테고리 채널을 지정해주세요.", ephemeral=True)
                    return
                if not isinstance(채널, discord.CategoryChannel):
                    await interaction.followup.send("❌ 카테고리를 지정해주세요 (텍스트 채널 아님).", ephemeral=True)
                    return
                return_config_manager.set_ticket_category(채널.id)
                embed = discord.Embed(
                    title="✅ 티켓 카테고리 설정 완료",
                    description=f"**카테고리:** {채널.mention}\n\n복귀 신청 티켓이 이 카테고리에 생성됩니다.",
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 복귀신청 패널 전송 ──────────────────────────────
            elif val == "복귀신청패널":
                from commands.admin.return_system.ticket_handler import ReturnTicketView
                embed = discord.Embed(
                    title="📋 복귀 신청",
                    description="아래 버튼을 눌러 복귀 신청 티켓을 열어주세요.",
                    color=0x3498db
                )
                target = 채널 if 채널 and isinstance(채널, discord.TextChannel) else interaction.channel
                await target.send(embed=embed, view=ReturnTicketView())
                await interaction.followup.send(f"✅ 복귀신청 패널을 {target.mention}에 전송했습니다.", ephemeral=True)

            # ── 설정 확인 ───────────────────────────────────────
            elif val == "설정확인":
                settings = return_config_manager.get_all_settings()
                embed = discord.Embed(title="📋 복귀 시스템 설정 현황", color=0x3498db)

                def role_text(role_id):
                    if not role_id:
                        return "❌ 미설정"
                    r = interaction.guild.get_role(role_id)
                    return r.mention if r else f"❌ 알 수 없는 역할 (`{role_id}`)"

                def ch_text(ch_id):
                    if not ch_id:
                        return "❌ 미설정"
                    c = interaction.guild.get_channel(ch_id)
                    return c.mention if c else f"❌ 알 수 없는 채널 (`{ch_id}`)"

                embed.add_field(name="⚠️ 잠수 역할",         value=role_text(settings.get("inactive_role_id")),    inline=True)
                embed.add_field(name="🔄 복귀 역할",         value=role_text(settings.get("return_role_id")),      inline=True)
                embed.add_field(name="🛡️ 관리자/복귀채팅 역할", value=role_text(settings.get("manager_role_id")), inline=True)
                embed.add_field(name="📣 복귀 핑 채널",       value=ch_text(settings.get("daily_channel_id")),     inline=True)
                embed.add_field(name="🎫 티켓 카테고리",      value=ch_text(settings.get("ticket_category_id")),   inline=True)
                embed.add_field(name="\u200b",               value="\u200b",                                       inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)

            # ── 예외 추가 ───────────────────────────────────────
            elif val == "예외추가":
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
            elif val == "예외삭제":
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
            elif val == "예외목록":
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
