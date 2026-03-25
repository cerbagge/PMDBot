# /복귀유저리스트 명령어 (관리자 전용)
#   잠수 유저 목록 (지속 메시지, 봇 재시작 후에도 수정)

import discord
from discord import app_commands
from datetime import datetime

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator


def setup(bot):

    @bot.tree.command(name="복귀유저리스트", description="잠수 유저 목록을 조회합니다")
    @app_commands.check(is_admin)
    async def 복귀유저리스트(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if bot_logger:
            bot_logger.log_command("복귀유저리스트", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.RETURN)

        try:
            from return_config_manager import return_config_manager

            inactive_role_id = return_config_manager.get_inactive_role()
            if not inactive_role_id:
                await interaction.followup.send(
                    "❌ 잠수 역할이 설정되지 않았습니다.\n`/복귀설정 기능:잠수역할`로 설정해주세요.",
                    ephemeral=True
                )
                return

            inactive_role = interaction.guild.get_role(inactive_role_id)
            if not inactive_role:
                await interaction.followup.send("❌ 잠수 역할을 찾을 수 없습니다.", ephemeral=True)
                return

            inactive_members = [m for m in interaction.guild.members if inactive_role in m.roles]

            from database_manager import db_manager
            bulk_data_manager = getattr(interaction.client, 'bulk_data_manager', None)
            now = datetime.now()

            rows = []
            for member in inactive_members:
                user_info = db_manager.get_user_info(member.id)
                mc_name = user_info.get('current_minecraft_name') if user_info else None

                last_online_str = "알 수 없음"
                days_elapsed = "?"

                if mc_name and bulk_data_manager:
                    resident = bulk_data_manager.get_resident_by_name(mc_name)
                    if resident and resident.get('lastOnline'):
                        try:
                            last_dt = datetime.fromtimestamp(resident['lastOnline'] / 1000)
                            last_online_str = last_dt.strftime("%Y.%m.%d")
                            days_elapsed = str((now - last_dt).days)
                        except Exception:
                            pass

                rows.append(f"{member.mention} | {last_online_str} | {days_elapsed}일")

            updated_at = now.strftime("%Y-%m-%d %H:%M")
            if not inactive_members:
                content = f"**잠수 유저 목록** (0명) — 업데이트: {updated_at}\n현재 잠수 상태인 유저가 없습니다."
            else:
                header = f"**잠수 유저 목록** (총 {len(rows)}명) — 업데이트: {updated_at}\n`@유저 | 마지막 접속일 | 경과일수`\n\n"
                content = header + "\n".join(rows)
                if len(content) > 2000:
                    content = content[:1997] + "..."

            # 기존 저장된 메시지 수정 시도
            list_msg_info = return_config_manager.get_list_message()
            existing_msg = None
            if list_msg_info:
                try:
                    ch = interaction.guild.get_channel(list_msg_info["channel_id"])
                    if ch:
                        existing_msg = await ch.fetch_message(list_msg_info["message_id"])
                except Exception:
                    return_config_manager.clear_list_message()

            if existing_msg:
                await existing_msg.edit(content=content)
                await interaction.followup.send(
                    f"✅ 리스트 메시지를 업데이트했습니다. → {existing_msg.jump_url}",
                    ephemeral=True
                )
            else:
                new_msg = await interaction.channel.send(content=content)
                return_config_manager.set_list_message(interaction.channel.id, new_msg.id)
                await interaction.followup.send("✅ 잠수 유저 리스트를 전송했습니다.", ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)

    @복귀유저리스트.error
    async def 복귀유저리스트_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ 권한 없음", description="관리자만 사용 가능합니다.", color=0xff0000),
                ephemeral=True
            )
