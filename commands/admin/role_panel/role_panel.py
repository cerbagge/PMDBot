# commands/admin/role_panel/role_panel.py
# /역할신청, /역할신청관리 명령어 - 역할 신청 패널 시스템
# 유저가 "신청" 클릭 → 리뷰 채널에 수락/기각 버튼 전송 → 관리자 승인

import discord
from discord import app_commands, ui
import io
from datetime import datetime

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator


class RolePanelCreateModal(ui.Modal, title="역할 신청 패널 생성"):
    """패널 제목/설명 입력 모달"""

    panel_title = ui.TextInput(
        label="임베드 제목",
        placeholder="예: 이벤트 참가 신청",
        required=True,
        max_length=256
    )

    panel_description = ui.TextInput(
        label="임베드 설명",
        placeholder="패널에 표시될 설명을 입력하세요",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=4000
    )

    def __init__(self, role: discord.Role, channel):
        super().__init__()
        self.role = role
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            from database_manager import db_manager

            panel_id = db_manager.create_role_panel(
                guild_id=interaction.guild.id,
                role_id=self.role.id,
                title=self.panel_title.value,
                description=self.panel_description.value,
                created_by=interaction.user.id
            )

            if not panel_id:
                await interaction.followup.send(
                    embed=discord.Embed(title="❌ 패널 생성 실패", description="데이터베이스 오류가 발생했습니다.", color=0xff0000),
                    ephemeral=True
                )
                return

            # 패널 임베드 + 신청 버튼을 현재 채널에 전송
            embed = discord.Embed(
                title=self.panel_title.value,
                description=self.panel_description.value,
                color=0x3498db
            )
            embed.set_footer(text=f"패널 ID: {panel_id} | 역할: {self.role.name}")

            view = RolePanelApplyView(panel_id, self.role.id)
            msg = await self.channel.send(embed=embed, view=view)

            db_manager.update_role_panel_message(panel_id, self.channel.id, msg.id)
            interaction.client.add_view(view)

            await interaction.followup.send(
                embed=discord.Embed(
                    title="✅ 패널 생성 완료",
                    description=(
                        f"**패널 ID:** `{panel_id}`\n"
                        f"**역할:** {self.role.mention}\n"
                        f"**채널:** {self.channel.mention}\n\n"
                        f"`/역할신청관리 패널id:{panel_id}` 으로 신청 기록 채널을 설정하세요."
                    ),
                    color=0x00ff00
                ),
                ephemeral=True
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류: {e}", ephemeral=True)


class RolePanelApplyView(ui.View):
    """역할 신청 버튼 (영구 View)"""

    def __init__(self, panel_id: str, role_id: int):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        self.role_id = role_id

        apply_btn = ui.Button(
            label="신청",
            style=discord.ButtonStyle.primary,
            emoji="📋",
            custom_id=f"role_panel_apply:{panel_id}"
        )
        apply_btn.callback = self.apply_callback
        self.add_item(apply_btn)

    async def apply_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            from database_manager import db_manager

            guild = interaction.guild
            member = interaction.user
            role = guild.get_role(self.role_id)
            panel = db_manager.get_role_panel(self.panel_id)

            if not role:
                await interaction.followup.send(
                    embed=discord.Embed(title="❌ 오류", description="역할을 찾을 수 없습니다.", color=0xff0000),
                    ephemeral=True
                )
                return

            if role.position >= guild.me.top_role.position:
                await interaction.followup.send(
                    embed=discord.Embed(title="❌ 오류", description="봇의 역할보다 높은 역할은 부여할 수 없습니다.", color=0xff0000),
                    ephemeral=True
                )
                return

            # 이미 신청했는지 확인
            existing = db_manager.check_role_panel_user(self.panel_id, member.id)
            if existing:
                status = existing.get('status', 'pending')
                if status == 'pending':
                    await interaction.followup.send(
                        embed=discord.Embed(title="⏳ 대기 중", description="이미 신청했습니다. 관리자 수락을 기다려주세요.", color=0xffa500),
                        ephemeral=True
                    )
                    return
                elif status == 'approved':
                    await interaction.followup.send(
                        embed=discord.Embed(title="✅ 이미 수락됨", description="이미 수락된 신청입니다.", color=0x00ff00),
                        ephemeral=True
                    )
                    return
                # status == 'denied' → 재신청 허용, 아래로 계속

            # 리뷰 채널 확인
            review_channel_id = panel.get('review_channel_id') if panel else None
            if not review_channel_id:
                await interaction.followup.send(
                    embed=discord.Embed(title="❌ 오류", description="신청 기록 채널이 설정되지 않았습니다. 관리자에게 문의하세요.", color=0xff0000),
                    ephemeral=True
                )
                return

            review_channel = guild.get_channel(review_channel_id)
            if not review_channel:
                await interaction.followup.send(
                    embed=discord.Embed(title="❌ 오류", description="신청 기록 채널을 찾을 수 없습니다.", color=0xff0000),
                    ephemeral=True
                )
                return

            # DB에 pending 기록 추가
            db_manager.add_role_panel_user(self.panel_id, member.id)

            # 리뷰 채널에 수락/기각 임베드 전송
            review_embed = discord.Embed(
                title="📋 역할 신청",
                description=(
                    f"**신청자:** {member.mention} (`{member.display_name}`)\n"
                    f"**역할:** {role.mention}\n"
                    f"**패널 ID:** `{self.panel_id}`"
                ),
                color=0x3498db,
                timestamp=datetime.now()
            )

            review_view = ui.View(timeout=None)
            approve_btn = ui.Button(
                label="수락", style=discord.ButtonStyle.success, emoji="✅",
                custom_id=f"rp_approve:{self.panel_id}:{member.id}"
            )
            deny_btn = ui.Button(
                label="기각", style=discord.ButtonStyle.danger, emoji="❌",
                custom_id=f"rp_deny:{self.panel_id}:{member.id}"
            )
            review_view.add_item(approve_btn)
            review_view.add_item(deny_btn)

            await review_channel.send(embed=review_embed, view=review_view)

            await interaction.followup.send(
                embed=discord.Embed(title="✅ 신청 완료", description="관리자 수락을 기다려주세요.", color=0x00ff00),
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(title="❌ 오류", description="권한이 부족합니다.", color=0xff0000),
                ephemeral=True
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류: {e}", ephemeral=True)


def setup(bot):
    # ===== /역할신청 =====
    @bot.tree.command(name="역할신청", description="역할 신청 패널을 생성합니다")
    @app_commands.describe(역할="신청 대상 역할")
    @app_commands.check(is_admin)
    async def role_panel_create(interaction: discord.Interaction, 역할: discord.Role):
        await interaction.response.send_modal(RolePanelCreateModal(역할, interaction.channel))

    @role_panel_create.error
    async def role_panel_create_error(interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)

    # ===== /역할신청관리 =====
    @bot.tree.command(name="역할신청관리", description="역할 신청 패널을 관리합니다")
    @app_commands.describe(
        패널id="관리할 패널 ID (예: RP0001)",
        채널="신청 기록을 받을 채널 (미지정 시 현재 채널)",
        기능="실행할 기능"
    )
    @app_commands.choices(기능=[
        app_commands.Choice(name="유저리스트", value="유저리스트"),
        app_commands.Choice(name="유저삭제", value="유저삭제"),
        app_commands.Choice(name="삭제", value="삭제"),
    ])
    @app_commands.check(is_admin)
    async def role_panel_manage(
        interaction: discord.Interaction,
        패널id: str,
        채널: discord.TextChannel = None,
        기능: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            from database_manager import db_manager

            panel = db_manager.get_role_panel(패널id)
            if not panel:
                await interaction.followup.send(
                    embed=discord.Embed(title="❌ 오류", description=f"패널 `{패널id}`을(를) 찾을 수 없습니다.", color=0xff0000),
                    ephemeral=True
                )
                return

            if 기능 is None:
                # === 신청 기록 채널 설정 ===
                target = 채널 or interaction.channel
                db_manager.set_role_panel_review_channel(패널id, target.id)

                role = interaction.guild.get_role(panel['role_id'])
                embed = discord.Embed(
                    title="✅ 신청 기록 채널 설정 완료",
                    description=(
                        f"**패널 ID:** `{패널id}`\n"
                        f"**역할:** {role.mention if role else '알 수 없음'}\n"
                        f"**신청 기록 채널:** {target.mention}\n\n"
                        f"유저가 신청 버튼을 누르면 이 채널에서 수락/기각할 수 있습니다."
                    ),
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "유저리스트":
                # === 수락된 유저 리스트 txt ===
                users = db_manager.get_role_panel_users(패널id, status='approved')

                if not users:
                    await interaction.followup.send(
                        embed=discord.Embed(title="📋 유저 리스트", description="수락된 유저가 없습니다.", color=0x3498db),
                        ephemeral=True
                    )
                    return

                lines = [f"패널 ID: {패널id}", f"총 {len(users)}명", "=" * 30, ""]
                for u in users:
                    member = interaction.guild.get_member(u['discord_id'])
                    name = f" ({member.display_name})" if member else ""
                    lines.append(f"{u['discord_id']}{name}")

                content = "\n".join(lines)
                file = discord.File(io.BytesIO(content.encode('utf-8')), filename=f"{패널id}_users.txt")

                await interaction.followup.send(
                    embed=discord.Embed(title="📋 유저 리스트", description=f"수락된 유저 총 **{len(users)}**명", color=0x3498db),
                    file=file, ephemeral=True
                )

            elif 기능.value == "유저삭제":
                # === 수락된 유저에게서 역할 일괄 제거 ===
                users = db_manager.get_role_panel_users(패널id, status='approved')
                role = interaction.guild.get_role(panel['role_id'])

                removed = 0
                failed = 0

                if role:
                    for u in users:
                        member = interaction.guild.get_member(u['discord_id'])
                        if member:
                            try:
                                await member.remove_roles(role, reason=f"역할 신청 패널 일괄 제거: {패널id}")
                                removed += 1
                            except Exception:
                                failed += 1
                        else:
                            failed += 1

                count = db_manager.clear_role_panel_users(패널id)

                embed = discord.Embed(
                    title="✅ 유저 삭제 완료",
                    description=(
                        f"**역할 제거:** {removed}명 성공"
                        + (f", {failed}명 실패 (서버 퇴장 등)" if failed else "")
                        + f"\n**DB 삭제:** {count}명"
                    ),
                    color=0x00ff00
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "삭제":
                # === 패널 삭제 (메시지 + DB) ===
                if panel.get('message_id') and panel.get('channel_id'):
                    try:
                        ch = interaction.guild.get_channel(panel['channel_id'])
                        if ch:
                            msg = await ch.fetch_message(panel['message_id'])
                            await msg.delete()
                    except Exception:
                        pass

                db_manager.delete_role_panel(패널id)
                await interaction.followup.send(
                    embed=discord.Embed(title="✅ 패널 삭제 완료", description=f"패널 `{패널id}`이(가) 삭제되었습니다.", color=0x00ff00),
                    ephemeral=True
                )

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류: {e}", ephemeral=True)

    @role_panel_manage.error
    async def role_panel_manage_error(interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)

    # ===== 수락/기각 버튼 처리 (on_interaction) =====
    @bot.listen('on_interaction')
    async def handle_role_panel_review(interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get('custom_id', '')

        if not (custom_id.startswith('rp_approve:') or custom_id.startswith('rp_deny:')):
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 관리자만 수락/기각할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            from database_manager import db_manager

            parts = custom_id.split(':')
            action = parts[0]
            panel_id = parts[1]
            target_id = int(parts[2])

            panel = db_manager.get_role_panel(panel_id)
            if not panel:
                await interaction.followup.send("❌ 패널을 찾을 수 없습니다.", ephemeral=True)
                return

            guild = interaction.guild
            member = guild.get_member(target_id)
            role = guild.get_role(panel['role_id'])

            if action == 'rp_approve':
                # 수락: 역할 부여 + 상태 업데이트
                if member and role:
                    try:
                        await member.add_roles(role, reason=f"역할 신청 수락: {panel_id}")
                    except discord.Forbidden:
                        await interaction.followup.send("❌ 역할을 부여할 권한이 없습니다.", ephemeral=True)
                        return

                db_manager.update_role_panel_user_status(panel_id, target_id, 'approved', interaction.user.id)

                # 리뷰 임베드 업데이트
                embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
                embed.color = 0x00ff00
                embed.set_footer(text=f"✅ 수락 by {interaction.user.display_name}")
                await interaction.message.edit(embed=embed, view=None)
                await interaction.followup.send(f"✅ <@{target_id}>에게 역할을 부여했습니다.", ephemeral=True)

            elif action == 'rp_deny':
                # 기각: 상태만 업데이트
                db_manager.update_role_panel_user_status(panel_id, target_id, 'denied', interaction.user.id)

                embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
                embed.color = 0xff0000
                embed.set_footer(text=f"❌ 기각 by {interaction.user.display_name}")
                await interaction.message.edit(embed=embed, view=None)
                await interaction.followup.send(f"❌ <@{target_id}>의 신청을 기각했습니다.", ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"❌ 오류: {e}", ephemeral=True)
            except Exception:
                pass
