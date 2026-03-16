# commands/admin/scheduler/newbie_config.py
# /뉴비설정 명령어 - 뉴비 알림 채널 및 핑 역할 설정

import discord
from discord import app_commands
from typing import Literal

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
    """봇에 /뉴비설정 명령어 등록"""

    @bot.tree.command(name="뉴비설정", description="뉴비 알림 채널 및 역할을 설정합니다")
    @app_commands.describe(
        기능="설정할 기능을 선택하세요",
        채널="알림을 받을 채널 (채널설정 시 필수)",
        역할="역할 (뉴비역할/핑역할설정/핑역할제거 시 필수)"
    )
    @app_commands.choices(기능=[
        app_commands.Choice(name="채널설정", value="채널설정"),
        app_commands.Choice(name="뉴비역할", value="뉴비역할"),
        app_commands.Choice(name="핑역할설정", value="핑역할설정"),
        app_commands.Choice(name="핑역할제거", value="핑역할제거"),
        app_commands.Choice(name="설정확인", value="설정확인"),
    ])
    @app_commands.check(is_admin)
    async def 뉴비설정(
        interaction: discord.Interaction,
        기능: app_commands.Choice[str],
        채널: discord.TextChannel = None,
        역할: discord.Role = None
    ):
        """뉴비 알림 설정"""
        await interaction.response.defer(ephemeral=True)

        if bot_logger:
            bot_logger.log_command("뉴비설정", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.SCHEDULER,
                                   details={"기능": 기능.value})

        try:
            from newbie_config_manager import newbie_config_manager

            if 기능.value == "채널설정":
                # 채널 설정
                if not 채널:
                    await interaction.followup.send("❌ 채널을 지정해주세요.", ephemeral=True)
                    return

                success = newbie_config_manager.set_notification_channel(채널.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 뉴비 알림 채널 설정 완료",
                        description=f"**채널:** {채널.mention}\n\n"
                                   f"이제 새로운 뉴비가 가입하면\n"
                                   f"이 채널에 알림이 전송됩니다.",
                        color=0x00ff00
                    )

                    # 현재 핑 역할 목록도 표시
                    ping_roles = newbie_config_manager.get_ping_roles()
                    if ping_roles:
                        role_mentions = []
                        for role_id in ping_roles:
                            role = interaction.guild.get_role(role_id)
                            if role:
                                role_mentions.append(role.mention)
                        if role_mentions:
                            embed.add_field(
                                name="🔔 핑 역할",
                                value=", ".join(role_mentions),
                                inline=False
                            )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 채널 설정에 실패했습니다.", ephemeral=True)

            elif 기능.value == "뉴비역할":
                # 뉴비 역할 설정
                if not 역할:
                    await interaction.followup.send("❌ 역할을 지정해주세요.", ephemeral=True)
                    return

                success = newbie_config_manager.set_newbie_role(역할.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 뉴비 역할 설정 완료",
                        description=f"**역할:** {역할.mention}\n\n"
                                   f"새로운 멤버가 BASE_NATION에 가입하면\n"
                                   f"이 역할이 자동으로 부여됩니다.\n"
                                   f"(2주 후 자동 제거)",
                        color=0x00ff00
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 뉴비 역할 설정에 실패했습니다.", ephemeral=True)

            elif 기능.value == "핑역할설정":
                # 핑 역할 추가
                if not 역할:
                    await interaction.followup.send("❌ 역할을 지정해주세요.", ephemeral=True)
                    return

                # 채널이 설정되어 있는지 확인
                if not newbie_config_manager.is_configured():
                    await interaction.followup.send(
                        "❌ 먼저 `/뉴비설정 기능:채널설정`으로 알림 채널을 설정해주세요.",
                        ephemeral=True
                    )
                    return

                # 이미 등록된 역할인지 확인
                if newbie_config_manager.has_ping_role(역할.id):
                    await interaction.followup.send(
                        f"⚠️ {역할.mention}은(는) 이미 핑 역할 목록에 있습니다.",
                        ephemeral=True
                    )
                    return

                success = newbie_config_manager.add_ping_role(역할.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 핑 역할 추가 완료",
                        description=f"**역할:** {역할.mention}\n\n"
                                   f"뉴비 알림 전송 시 이 역할이 멘션됩니다.",
                        color=0x00ff00
                    )

                    # 현재 핑 역할 목록 표시
                    ping_roles = newbie_config_manager.get_ping_roles()
                    role_mentions = []
                    for role_id in ping_roles:
                        r = interaction.guild.get_role(role_id)
                        if r:
                            role_mentions.append(r.mention)
                    if role_mentions:
                        embed.add_field(
                            name="🔔 현재 핑 역할 목록",
                            value=", ".join(role_mentions),
                            inline=False
                        )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 역할 추가에 실패했습니다.", ephemeral=True)

            elif 기능.value == "설정확인":
                # 설정 현황 조회
                settings = newbie_config_manager.get_all_settings()

                embed = discord.Embed(
                    title="📋 뉴비 시스템 설정 현황",
                    color=0x3498db
                )

                # 뉴비 역할 정보
                newbie_role_id = settings.get("newbie_role_id")
                if newbie_role_id:
                    newbie_role = interaction.guild.get_role(newbie_role_id)
                    newbie_role_text = newbie_role.mention if newbie_role else f"❌ 알 수 없는 역할 (ID: {newbie_role_id})"
                else:
                    newbie_role_text = "❌ 설정되지 않음"

                embed.add_field(
                    name="🆕 뉴비 역할",
                    value=newbie_role_text,
                    inline=False
                )

                # 채널 정보
                channel_id = settings.get("notification_channel_id")
                if channel_id:
                    channel = interaction.guild.get_channel(channel_id)
                    channel_text = channel.mention if channel else f"❌ 알 수 없는 채널 (ID: {channel_id})"
                else:
                    channel_text = "❌ 설정되지 않음"

                embed.add_field(
                    name="📢 알림 채널",
                    value=channel_text,
                    inline=False
                )

                # 핑 역할 목록
                ping_roles = settings.get("ping_role_ids", [])
                if ping_roles:
                    role_mentions = []
                    for role_id in ping_roles:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            role_mentions.append(f"• {role.mention} (`{role_id}`)")
                        else:
                            role_mentions.append(f"• ❌ 알 수 없는 역할 (`{role_id}`)")
                    embed.add_field(
                        name=f"🔔 핑 역할 ({len(ping_roles)}개)",
                        value="\n".join(role_mentions),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🔔 핑 역할",
                        value="설정된 역할이 없습니다.",
                        inline=False
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "핑역할제거":
                # 핑 역할 제거
                if not 역할:
                    await interaction.followup.send("❌ 제거할 역할을 지정해주세요.", ephemeral=True)
                    return

                # 등록된 역할인지 확인
                if not newbie_config_manager.has_ping_role(역할.id):
                    await interaction.followup.send(
                        f"⚠️ {역할.mention}은(는) 핑 역할 목록에 없습니다.",
                        ephemeral=True
                    )
                    return

                success = newbie_config_manager.remove_ping_role(역할.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 핑 역할 제거 완료",
                        description=f"**역할:** {역할.mention}\n\n"
                                   f"이 역할은 더 이상 뉴비 알림에 멘션되지 않습니다.",
                        color=0x00ff00
                    )

                    # 남은 핑 역할 목록 표시
                    ping_roles = newbie_config_manager.get_ping_roles()
                    if ping_roles:
                        role_mentions = []
                        for role_id in ping_roles:
                            r = interaction.guild.get_role(role_id)
                            if r:
                                role_mentions.append(r.mention)
                        if role_mentions:
                            embed.add_field(
                                name="🔔 남은 핑 역할",
                                value=", ".join(role_mentions),
                                inline=False
                            )
                    else:
                        embed.add_field(
                            name="🔔 핑 역할",
                            value="모든 핑 역할이 제거되었습니다.",
                            inline=False
                        )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 역할 제거에 실패했습니다.", ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)

    # 에러 핸들러
    @뉴비설정.error
    async def 뉴비설정_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
