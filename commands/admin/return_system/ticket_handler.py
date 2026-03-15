import discord
import asyncio
import os
import re
from datetime import datetime


class ReturnTicketView(discord.ui.View):
    """복귀 신청 버튼 (영구 View)"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="복귀 신청",
        style=discord.ButtonStyle.primary,
        custom_id="return_ticket_open",
        emoji="📋"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        try:
            from return_config_manager import return_config_manager
            from database_manager import db_manager

            member = interaction.user
            guild = interaction.guild

            # 카테고리 확인
            category_id = return_config_manager.get_ticket_category()
            if not category_id:
                await interaction.followup.send(
                    "❌ 티켓 카테고리가 설정되지 않았습니다. 관리자에게 문의해주세요.",
                    ephemeral=True
                )
                return

            category = guild.get_channel(category_id)
            if not category:
                await interaction.followup.send("❌ 티켓 카테고리를 찾을 수 없습니다.", ephemeral=True)
                return

            # 이미 열린 티켓이 있는지 확인
            for ch in category.channels:
                if hasattr(ch, 'topic') and ch.topic == f"return_user:{member.id}":
                    await interaction.followup.send(
                        f"❌ 이미 열린 티켓이 있습니다: {ch.mention}",
                        ephemeral=True
                    )
                    return

            # DB에서 MC 이름 가져오기
            user_info = db_manager.get_user_info(member.id)
            mc_name = (user_info.get('current_minecraft_name') if user_info else None) or member.display_name

            # 콜사인 가져오기
            callsign = None
            try:
                from callsign_manager import callsign_manager
                callsign = callsign_manager.get_callsign(member.id)
            except Exception:
                pass

            # 마지막 접속 이후 일수 계산 (채널명 DC 파트에 사용)
            last_online_days = 0
            bulk_data_manager = getattr(interaction.client, 'bulk_data_manager', None)
            if user_info and user_info.get('current_minecraft_name') and bulk_data_manager:
                resident = bulk_data_manager.get_resident_by_name(user_info['current_minecraft_name'])
                if resident and resident.get('lastOnline'):
                    try:
                        last_dt = datetime.fromtimestamp(resident['lastOnline'] / 1000)
                        last_online_days = (datetime.now() - last_dt).days
                    except Exception:
                        pass

            # 채널 이름 생성: {MC}--{CC}--{DC}
            # CC: ASCII 콜사인만 허용 (Discord 채널명 제한), 한글 콜사인은 제외
            mc_part = re.sub(r'[^a-z0-9\-]', '', mc_name.lower().replace(" ", "-").replace("_", "-"))
            cc_part = re.sub(r'[^a-z0-9\-]', '', callsign.lower()) if callsign else ""
            dc_part = f"{last_online_days}d"

            if cc_part:
                channel_name = f"{mc_part}--{cc_part}--{dc_part}"
            else:
                channel_name = f"{mc_part}--{dc_part}"
            channel_name = channel_name[:100] or f"return-{member.id}"

            # 채널 권한 설정
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, manage_channels=True
                ),
            }
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            # 채널 생성
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                topic=f"return_user:{member.id}",
                overwrites=overwrites,
                reason=f"복귀 신청: {member.display_name}"
            )

            # 복귀 역할 부여
            return_role_id = return_config_manager.get_return_role()
            if return_role_id:
                return_role = guild.get_role(return_role_id)
                if return_role:
                    try:
                        await member.add_roles(return_role, reason="복귀 신청 티켓 오픈")
                    except Exception:
                        pass

            # 마지막 접속 정보 (embed 표시용)
            last_online_str = f"알 수 없음 ({last_online_days}일 전)" if last_online_days else "알 수 없음"
            if user_info and user_info.get('current_minecraft_name') and bulk_data_manager:
                resident = bulk_data_manager.get_resident_by_name(user_info['current_minecraft_name'])
                if resident and resident.get('lastOnline'):
                    try:
                        last_dt = datetime.fromtimestamp(resident['lastOnline'] / 1000)
                        last_online_str = f"{last_dt.strftime('%Y.%m.%d')} ({last_online_days}일 전)"
                    except Exception:
                        pass

            # 티켓 채널에 안내 메시지 전송
            embed = discord.Embed(
                title="📋 복귀 신청",
                description=(
                    f"**신청자:** {member.mention}\n"
                    f"**MC 닉네임:** {mc_name}\n"
                    f"**콜사인:** {callsign or '없음'}\n"
                    f"**마지막 접속:** {last_online_str}\n\n"
                    f"관리자가 확인 후 `/복귀확인` 명령어로 복귀 처리합니다."
                ),
                color=0x3498db
            )
            await ticket_channel.send(content=member.mention, embed=embed, view=CloseTicketView())

            # 관리자 역할 핑 (복귀 관리자 역할 우선, 없으면 핑 역할)
            ping_role_id = return_config_manager.get_manager_role() or return_config_manager.get_daily_ping_role()
            if ping_role_id:
                await ticket_channel.send(content=f"<@&{ping_role_id}>")

            await interaction.followup.send(
                f"✅ 티켓이 생성되었습니다: {ticket_channel.mention}",
                ephemeral=True
            )
            print(f"[TICKET] 티켓 생성: {channel_name} (유저: {member.display_name})")

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 티켓 생성 실패: {e}", ephemeral=True)


class CloseTicketView(discord.ui.View):
    """채널 닫기 버튼 (영구 View)"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="채널 닫기",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket_channel",
        emoji="🔒"
    )
    async def close_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 관리자 또는 복귀 관리자 역할 체크
        has_permission = interaction.user.guild_permissions.administrator
        if not has_permission:
            try:
                from return_config_manager import return_config_manager
                role_id = return_config_manager.get_manager_role()
                if role_id and any(r.id == role_id for r in interaction.user.roles):
                    has_permission = True
            except Exception:
                pass
        if not has_permission:
            await interaction.response.send_message("❌ 복귀 관리자 역할 또는 관리자만 채널을 닫을 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 대화 내용을 저장하고 3초 후 채널이 삭제됩니다...")

        # 채널 토픽에서 유저 ID 추출
        user_id = None
        topic = interaction.channel.topic or ""
        if topic.startswith("return_user:"):
            try:
                user_id = int(topic.split(":", 1)[1].strip())
            except ValueError:
                pass

        # 메시지 수집 (오래된 순)
        messages = []
        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            messages.append(msg)

        # 로그 파일 저장
        if messages:
            try:
                log_dir = os.path.join("data", "logs", "return", str(user_id) if user_id else "unknown")
                os.makedirs(log_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_path = os.path.join(log_dir, f"{timestamp}.txt")

                lines = [
                    f"채널: #{interaction.channel.name}",
                    f"닫기 처리자: {interaction.user.display_name} ({interaction.user.id})",
                    f"저장 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"유저 ID: {user_id or '알 수 없음'}",
                    "=" * 60,
                    ""
                ]

                for msg in messages:
                    ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    author = f"{msg.author.display_name} ({msg.author.id})"
                    content = msg.content or ""

                    for embed in msg.embeds:
                        embed_lines = []
                        if embed.title:
                            embed_lines.append(f"[임베드 제목] {embed.title}")
                        if embed.description:
                            embed_lines.append(f"[임베드 내용] {embed.description}")
                        for field in embed.fields:
                            embed_lines.append(f"[{field.name}] {field.value}")
                        if embed_lines:
                            content += ("\n" if content else "") + "\n".join(embed_lines)

                    if content:
                        lines.append(f"[{ts}] {author}")
                        lines.append(content)
                        lines.append("")

                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

                print(f"[TICKET] 대화 로그 저장 완료: {log_path}")

            except Exception as e:
                print(f"[WARN] 대화 로그 저장 실패: {e}")

        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"복귀 티켓 닫기: {interaction.user.display_name}")
        except Exception:
            pass


def setup(bot):
    bot.add_view(ReturnTicketView())
    bot.add_view(CloseTicketView())
    print("[OK] ReturnTicketView / CloseTicketView 영구 등록 완료")
