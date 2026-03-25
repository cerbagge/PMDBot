# commands/admin/travel/travel_setting.py
# /여행설정 명령어 - 여행 시스템 설정 (채널, 역할, 패널 등)

import discord
from discord import app_commands
from typing import Literal
from datetime import datetime

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    # 여행 관리 역할 체크
    try:
        from travel_manager import travel_config_manager
        return travel_config_manager.is_manager(interaction.user)
    except:
        return False


def setup(bot):
    """봇에 /여행설정 명령어 등록"""

    @bot.tree.command(name="여행설정", description="여행 시스템을 설정합니다 (채널, 역할, 패널 등)")
    @app_commands.describe(
        기능="설정할 기능을 선택하세요",
        채널="채널 (채널/로그_채널 설정 시)",
        역할="역할 (역할 설정/제거 시)"
    )
    @app_commands.choices(기능=[
        app_commands.Choice(name="여행신청패널", value="여행신청패널"),
        app_commands.Choice(name="채널", value="채널"),
        app_commands.Choice(name="로그_채널", value="로그_채널"),
        app_commands.Choice(name="역할", value="역할"),
        app_commands.Choice(name="역할목록", value="역할목록"),
        app_commands.Choice(name="역할제거", value="역할제거"),
        app_commands.Choice(name="현황", value="현황"),
    ])
    @app_commands.check(is_admin)
    async def 여행설정(
        interaction: discord.Interaction,
        기능: app_commands.Choice[str],
        채널: discord.TextChannel = None,
        역할: discord.Role = None
    ):
        """여행 시스템 설정"""
        if bot_logger:
            bot_logger.log_command("여행설정", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.TRAVEL,
                                   details={"기능": 기능.value})

        from travel_manager import travel_manager, travel_config_manager

        # 여행신청패널 기능
        if 기능.value == "여행신청패널":
            await interaction.response.defer(ephemeral=True)

            try:
                from commands.user.travel.travel_request import TravelPanelView
                from config import config as bot_config

                target_channel = 채널 or interaction.channel

                # 기존 패널이 있으면 삭제 시도
                old_panel = travel_config_manager.get_panel_info()
                if old_panel:
                    try:
                        old_ch = interaction.guild.get_channel(old_panel["channel_id"])
                        if old_ch:
                            try:
                                old_msg = await old_ch.fetch_message(old_panel["message_id"])
                                await old_msg.delete()
                            except discord.NotFound:
                                pass
                    except Exception:
                        pass

                # 패널 임베드 생성
                base_nation = getattr(bot_config, 'BASE_NATION', 'Red_Mafia')

                panel_embed = discord.Embed(
                    title="✈️ 여행 신청",
                    description=(
                        "아래 버튼을 클릭하여 여행을 신청할 수 있습니다.\n\n"
                        f"**{base_nation}** 국민은 목적지 국가와 기간을 입력합니다.\n"
                        f"외국인은 기간만 입력하면 목적지가 **{base_nation}**으로 자동 설정됩니다.\n\n"
                        "**신청 절차:**\n"
                        "1. 아래 `여행 신청하기` 버튼 클릭\n"
                        "2. 여행 정보 입력 (목적지, 시작일, 종료일)\n"
                        "3. 관리진 승인 대기\n"
                        "4. 승인 완료 시 DM으로 알림"
                    ),
                    color=0x3498db
                )
                panel_embed.set_footer(text="여행 기간 동안 역할/닉네임 변동이 유예됩니다.")

                # 패널 전송
                view = TravelPanelView()
                panel_msg = await target_channel.send(embed=panel_embed, view=view)

                # 패널 정보 저장
                travel_config_manager.set_panel_info(target_channel.id, panel_msg.id)

                embed = discord.Embed(
                    title="✅ 여행 신청 패널 설정 완료",
                    description=f"**채널:** {target_channel.mention}\n\n"
                               f"해당 채널에 여행 신청 패널이 생성되었습니다.\n"
                               f"봇이 재시작되어도 패널이 유지됩니다.",
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                import traceback
                traceback.print_exc()
                await interaction.followup.send(f"❌ 패널 생성에 실패했습니다: {str(e)}", ephemeral=True)

            return

        # 나머지 기능들은 defer 사용
        await interaction.response.defer(ephemeral=True)

        try:
            if 기능.value == "채널":
                # 여행 신청 알림 채널 설정
                if not 채널:
                    # 현재 채널로 설정
                    채널 = interaction.channel

                success = travel_config_manager.set_request_channel(채널.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 여행 신청 채널 설정 완료",
                        description=f"**채널:** {채널.mention}\n\n"
                                   f"새로운 여행 신청이 이 채널에 표시됩니다.\n"
                                   f"관리자가 수락/기각 버튼을 눌러 처리할 수 있습니다.",
                        color=0x00ff00
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 채널 설정에 실패했습니다.", ephemeral=True)

            elif 기능.value == "로그_채널":
                # 로그 채널 설정
                if not 채널:
                    채널 = interaction.channel

                success = travel_config_manager.set_log_channel(채널.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 여행 로그 채널 설정 완료",
                        description=f"**채널:** {채널.mention}\n\n"
                                   f"여행 승인/기각 로그와 만료 알림이 이 채널에 표시됩니다.\n"
                                   f"여행 종료 1일 전과 당일에 알림이 전송됩니다.",
                        color=0x00ff00
                    )

                    # 핑 역할 표시
                    manager_roles = travel_config_manager.get_manager_roles()
                    if manager_roles:
                        role_mentions = []
                        for role_id in manager_roles:
                            r = interaction.guild.get_role(role_id)
                            if r:
                                role_mentions.append(r.mention)
                        if role_mentions:
                            embed.add_field(
                                name="🔔 알림 시 멘션되는 역할",
                                value=", ".join(role_mentions),
                                inline=False
                            )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 로그 채널 설정에 실패했습니다.", ephemeral=True)

            elif 기능.value == "역할":
                # 관리 역할 추가
                if not 역할:
                    await interaction.followup.send("❌ 역할을 지정해주세요.", ephemeral=True)
                    return

                # 이미 등록된 역할인지 확인
                if travel_config_manager.has_manager_role(역할.id):
                    await interaction.followup.send(
                        f"⚠️ {역할.mention}은(는) 이미 여행 관리 역할입니다.",
                        ephemeral=True
                    )
                    return

                success = travel_config_manager.add_manager_role(역할.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 여행 관리 역할 추가 완료",
                        description=f"**역할:** {역할.mention}\n\n"
                                   f"이 역할을 가진 멤버는:\n"
                                   f"• 여행 신청을 수락/기각할 수 있습니다\n"
                                   f"• 여행 종료 시 멘션됩니다",
                        color=0x00ff00
                    )

                    # 현재 역할 목록 표시
                    manager_roles = travel_config_manager.get_manager_roles()
                    role_mentions = []
                    for role_id in manager_roles:
                        r = interaction.guild.get_role(role_id)
                        if r:
                            role_mentions.append(r.mention)
                    if role_mentions:
                        embed.add_field(
                            name="🔔 현재 관리 역할 목록",
                            value=", ".join(role_mentions),
                            inline=False
                        )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 역할 추가에 실패했습니다.", ephemeral=True)

            elif 기능.value == "역할목록":
                # 역할 목록 조회
                settings = travel_config_manager.get_all_settings()

                embed = discord.Embed(
                    title="📋 여행 시스템 설정 현황",
                    color=0x3498db
                )

                # 신청 채널
                request_channel_id = settings.get("request_channel_id")
                if request_channel_id:
                    channel = interaction.guild.get_channel(request_channel_id)
                    channel_text = channel.mention if channel else f"❌ 알 수 없는 채널 (ID: {request_channel_id})"
                else:
                    channel_text = "❌ 설정되지 않음"
                embed.add_field(name="📢 신청 알림 채널", value=channel_text, inline=False)

                # 로그 채널
                log_channel_id = settings.get("log_channel_id")
                if log_channel_id:
                    channel = interaction.guild.get_channel(log_channel_id)
                    channel_text = channel.mention if channel else f"❌ 알 수 없는 채널 (ID: {log_channel_id})"
                else:
                    channel_text = "❌ 설정되지 않음"
                embed.add_field(name="📝 로그 채널", value=channel_text, inline=False)

                # 관리 역할 목록
                manager_roles = settings.get("manager_role_ids", [])
                if manager_roles:
                    role_mentions = []
                    for role_id in manager_roles:
                        r = interaction.guild.get_role(role_id)
                        if r:
                            role_mentions.append(f"• {r.mention} (`{role_id}`)")
                        else:
                            role_mentions.append(f"• ❌ 알 수 없는 역할 (`{role_id}`)")
                    embed.add_field(
                        name=f"🔔 관리 역할 ({len(manager_roles)}개)",
                        value="\n".join(role_mentions),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🔔 관리 역할",
                        value="설정된 역할이 없습니다.\n(관리자만 수락/기각 가능)",
                        inline=False
                    )

                # 시스템 상태
                is_enabled = settings.get("enabled", True)
                embed.add_field(
                    name="⚙️ 시스템 상태",
                    value="✅ 활성화" if is_enabled else "❌ 비활성화",
                    inline=False
                )

                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "역할제거":
                # 역할 제거
                if not 역할:
                    await interaction.followup.send("❌ 제거할 역할을 지정해주세요.", ephemeral=True)
                    return

                # 등록된 역할인지 확인
                if not travel_config_manager.has_manager_role(역할.id):
                    await interaction.followup.send(
                        f"⚠️ {역할.mention}은(는) 여행 관리 역할이 아닙니다.",
                        ephemeral=True
                    )
                    return

                success = travel_config_manager.remove_manager_role(역할.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 여행 관리 역할 제거 완료",
                        description=f"**역할:** {역할.mention}\n\n"
                                   f"이 역할은 더 이상 여행 관리 권한이 없습니다.",
                        color=0x00ff00
                    )

                    # 남은 역할 목록 표시
                    manager_roles = travel_config_manager.get_manager_roles()
                    if manager_roles:
                        role_mentions = []
                        for role_id in manager_roles:
                            r = interaction.guild.get_role(role_id)
                            if r:
                                role_mentions.append(r.mention)
                        if role_mentions:
                            embed.add_field(
                                name="🔔 남은 관리 역할",
                                value=", ".join(role_mentions),
                                inline=False
                            )
                    else:
                        embed.add_field(
                            name="🔔 관리 역할",
                            value="모든 관리 역할이 제거되었습니다.\n(관리자만 수락/기각 가능)",
                            inline=False
                        )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 역할 제거에 실패했습니다.", ephemeral=True)

            elif 기능.value == "현황":
                # 여행 시스템 현황
                pending = travel_manager.get_pending_travels()
                active = travel_manager.get_active_travels()
                ending_soon = travel_manager.get_travels_ending_soon(days=3)

                embed = discord.Embed(
                    title="✈️ 여행 시스템 현황",
                    color=0x3498db
                )

                embed.add_field(
                    name="📋 대기 중인 신청",
                    value=f"{len(pending)}건",
                    inline=True
                )
                embed.add_field(
                    name="🛫 진행 중인 여행",
                    value=f"{len(active)}건",
                    inline=True
                )
                embed.add_field(
                    name="⏰ 3일 내 종료",
                    value=f"{len(ending_soon)}건",
                    inline=True
                )

                # 곧 종료되는 여행 목록
                if ending_soon:
                    ending_text = []
                    for travel in ending_soon[:5]:
                        days_until = travel.get('days_until_end', 0)
                        if days_until == 0:
                            time_text = "**오늘 종료**"
                        elif days_until == 1:
                            time_text = "내일 종료"
                        else:
                            time_text = f"{days_until}일 후 종료"

                        ending_text.append(
                            f"• `{travel['id']}` - <@{travel['discord_id']}> ({time_text})"
                        )

                    embed.add_field(
                        name="⏰ 곧 종료되는 여행",
                        value="\n".join(ending_text),
                        inline=False
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)

    # 에러 핸들러
    @여행설정.error
    async def 여행설정_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자 또는 여행 관리 역할만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
