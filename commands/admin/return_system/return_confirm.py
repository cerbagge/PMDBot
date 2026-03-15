# /복귀확인 명령어 (관리자 전용)
# 복귀 신청 중인 유저의 복귀를 최종 확인:
#   - 복귀 역할 제거
#   - 잠수 역할 제거
#   - 복귀완료 역할 지급 (설정된 경우)
#   - DM 발송 기록 초기화 (재잠수 시 다시 DM 받을 수 있도록)

import discord
from discord import app_commands


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

    @bot.tree.command(name="복귀확인", description="유저의 복귀를 확인하고 복귀 처리합니다")
    @app_commands.describe(유저="복귀 처리할 유저")
    @app_commands.check(is_return_manager)
    async def 복귀확인(interaction: discord.Interaction, 유저: discord.Member):
        await interaction.response.defer(ephemeral=True)

        try:
            from return_config_manager import return_config_manager

            inactive_role_id    = return_config_manager.get_inactive_role()
            return_role_id      = return_config_manager.get_return_role()
            return_chat_role_id = return_config_manager.get_return_chat_role()

            changes = []

            # 잠수 역할 제거
            if inactive_role_id:
                inactive_role = interaction.guild.get_role(inactive_role_id)
                if inactive_role and inactive_role in 유저.roles:
                    try:
                        await 유저.remove_roles(inactive_role, reason=f"복귀확인: {interaction.user.name}")
                        changes.append(f"✅ 잠수 역할 제거: {inactive_role.mention}")
                    except discord.Forbidden:
                        changes.append(f"❌ 잠수 역할 제거 실패 (권한 없음): {inactive_role.mention}")

            # 복귀 역할 제거 (신청 중 상태 해제)
            if return_role_id:
                return_role = interaction.guild.get_role(return_role_id)
                if return_role and return_role in 유저.roles:
                    try:
                        await 유저.remove_roles(return_role, reason=f"복귀확인: {interaction.user.name}")
                        changes.append(f"✅ 복귀 역할 제거: {return_role.mention}")
                    except discord.Forbidden:
                        changes.append(f"❌ 복귀 역할 제거 실패 (권한 없음): {return_role.mention}")

            # 복귀채팅 역할 제거
            if return_chat_role_id:
                return_chat_role = interaction.guild.get_role(return_chat_role_id)
                if return_chat_role and return_chat_role in 유저.roles:
                    try:
                        await 유저.remove_roles(return_chat_role, reason=f"복귀확인: {interaction.user.name}")
                        changes.append(f"✅ 복귀채팅 역할 제거: {return_chat_role.mention}")
                    except discord.Forbidden:
                        changes.append(f"❌ 복귀채팅 역할 제거 실패: {return_chat_role.mention}")

            # 잠수 추가 역할 제거
            extra_role_ids = return_config_manager.get_extra_inactive_roles()
            for rid in extra_role_ids:
                extra_role = interaction.guild.get_role(rid)
                if extra_role and extra_role in 유저.roles:
                    try:
                        await 유저.remove_roles(extra_role, reason=f"복귀확인: {interaction.user.name}")
                        changes.append(f"✅ 추가 역할 제거: {extra_role.mention}")
                    except discord.Forbidden:
                        changes.append(f"❌ 추가 역할 제거 실패: {extra_role.mention}")

            # 뉴비 역할 지급 (복귀 후 뉴비로 처리)
            try:
                from newbie_config_manager import newbie_config_manager
                newbie_role_id = newbie_config_manager.get_newbie_role()
                if newbie_role_id:
                    newbie_role = interaction.guild.get_role(newbie_role_id)
                    if newbie_role:
                        if newbie_role not in 유저.roles:
                            await 유저.add_roles(newbie_role, reason=f"복귀확인: {interaction.user.name}")
                            changes.append(f"✅ 뉴비 역할 지급: {newbie_role.mention}")
                        else:
                            changes.append(f"ℹ️ 뉴비 역할 이미 보유: {newbie_role.mention}")
            except Exception:
                pass

            # DM 기록 초기화 (재잠수 시 다시 DM 받을 수 있도록, 부계정 포함)
            return_config_manager.clear_dm_sent(유저.id)
            try:
                from commands.admin.alt_account.alt_account import _get_linked_ids
                for linked_id in _get_linked_ids(유저.id):
                    return_config_manager.clear_dm_sent(linked_id)
            except Exception:
                pass

            # 결과 embed
            if not changes:
                embed = discord.Embed(
                    title="⚠️ 변경 사항 없음",
                    description=(
                        f"{유저.mention}에게 제거할 잠수/복귀 역할이 없습니다.\n"
                        f"이미 복귀 처리되었거나 잠수 상태가 아닐 수 있습니다."
                    ),
                    color=0xff9900
                )
            else:
                embed = discord.Embed(
                    title="✅ 복귀 확인 완료",
                    description=f"**대상:** {유저.mention}\n\n" + "\n".join(changes),
                    color=0x00ff00
                )
                embed.set_footer(text=f"처리자: {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

            # 복귀 완료 시 닫기 버튼 패널 전송
            if changes:
                try:
                    from commands.admin.return_system.ticket_handler import CloseTicketView
                    # 채널 토픽에 유저 ID 저장 (닫기 시 로그 저장에 사용)
                    try:
                        await interaction.channel.edit(topic=f"return_user:{유저.id}")
                    except Exception:
                        pass
                    close_embed = discord.Embed(
                        title="✅ 복귀 처리 완료",
                        description=f"{유저.mention}의 복귀가 확인되었습니다.\n준비가 되면 아래 버튼으로 채널을 닫아주세요.",
                        color=0x00ff00
                    )
                    await interaction.channel.send(embed=close_embed, view=CloseTicketView())
                except Exception:
                    pass

            # 로그 채널에도 전송 (설정된 경우)
            try:
                from config import config
                if config.LOG_CHANNEL_ID:
                    log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="📋 복귀 확인 로그",
                            description=f"**대상:** {유저.mention} (`{유저.id}`)\n**처리자:** {interaction.user.mention}\n\n" + "\n".join(changes),
                            color=0x00ff00
                        )
                        await log_channel.send(embed=log_embed)
            except Exception:
                pass

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)

    @복귀확인.error
    async def 복귀확인_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ 권한 없음", description="복귀 관리자 역할 또는 관리자만 사용 가능합니다.", color=0xff0000),
                ephemeral=True
            )
