# commands/admin/announcement/announcement.py
# /공지 명령어 - 공지 전송 및 예약 (관리자 전용)
# /공지관리 명령어 - 예약된 공지 목록 확인 및 취소 (관리자 전용)

import discord
from discord import app_commands
from datetime import datetime
import re

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


def parse_scheduled_time(time_str: str):
    """
    예약 시간 문자열 파싱

    형식: YYYY.MM.DD HH:MM
    Returns: (datetime, error_message)
    """
    pattern = r'^\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}$'
    if not re.match(pattern, time_str.strip()):
        return None, "예약 시간 형식이 올바르지 않습니다.\n올바른 형식: `YYYY.MM.DD HH:MM` (예: `2026.03.15 14:30`)"

    try:
        dt = datetime.strptime(time_str.strip(), "%Y.%m.%d %H:%M")
    except ValueError:
        return None, "유효하지 않은 날짜/시간입니다. 올바른 날짜와 시간을 입력해주세요."

    if dt <= datetime.now():
        return None, "예약 시간이 현재보다 과거입니다. 미래 시간을 입력해주세요."

    return dt, None


# ===== 공지 입력 Modal =====
class AnnouncementModal(discord.ui.Modal, title="📢 공지 작성"):
    """여러 줄 입력이 가능한 공지 작성 Modal"""

    텍스트 = discord.ui.TextInput(
        label="공지 내용",
        style=discord.TextStyle.paragraph,
        placeholder="공지 내용을 입력하세요...\n여러 줄로 작성할 수 있습니다.",
        required=True,
        max_length=2000
    )

    def __init__(self, scheduled_time: str = None, is_silent: bool = False, channel: discord.TextChannel = None, mention_role: discord.Role = None):
        super().__init__()
        self.scheduled_time = scheduled_time
        self.is_silent = is_silent
        self.target_channel = channel
        self.mention_role = mention_role

    async def on_submit(self, interaction: discord.Interaction):
        text = self.텍스트.value.replace("\\n", "\n")

        # --- 즉시 전송 (예약 없음) ---
        if self.scheduled_time is None:
            try:
                # 멘션대상이 있으면 텍스트 앞에 멘션 추가
                send_text = text
                if self.mention_role:
                    send_text = f"{self.mention_role.mention}\n{text}"

                await self.target_channel.send(
                    content=send_text,
                    silent=self.is_silent
                )

                mode_text = "무음" if self.is_silent else "일반"
                embed = discord.Embed(
                    title="✅ 공지 전송 완료",
                    description="공지가 전송되었습니다.",
                    color=0x00ff00
                )
                embed.add_field(name="📢 모드", value=mode_text, inline=True)
                embed.add_field(name="📍 채널", value=self.target_channel.mention, inline=True)
                if self.mention_role:
                    embed.add_field(name="📣 멘션", value=self.mention_role.mention, inline=True)
                embed.add_field(
                    name="📝 내용 미리보기",
                    value=text[:100] + ("..." if len(text) > 100 else ""),
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ 전송 실패",
                    description="이 채널에 메시지를 보낼 권한이 없습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                embed = discord.Embed(
                    title="❌ 오류 발생",
                    description=f"공지 전송 중 오류가 발생했습니다.\n{str(e)[:100]}",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # --- 예약 전송 ---
        scheduled_dt, error_msg = parse_scheduled_time(self.scheduled_time)
        if error_msg:
            embed = discord.Embed(
                title="❌ 예약 시간 오류",
                description=error_msg,
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            from announcement_scheduler import announcement_schedule_manager

            internal_time = scheduled_dt.strftime("%Y-%m-%d %H:%M")

            # 멘션대상이 있으면 텍스트 앞에 멘션 추가
            schedule_text = text
            if self.mention_role:
                schedule_text = f"<@&{self.mention_role.id}>\n{text}"

            entry = announcement_schedule_manager.add_schedule(
                channel_id=self.target_channel.id,
                guild_id=interaction.guild.id,
                text=schedule_text,
                silent=self.is_silent,
                scheduled_time=internal_time,
                created_by=interaction.user.id
            )

            if entry:
                mode_text = "무음" if self.is_silent else "일반"
                display_time = scheduled_dt.strftime("%Y.%m.%d %H:%M")

                embed = discord.Embed(
                    title="✅ 공지 예약 완료",
                    description="공지가 예약되었습니다.",
                    color=0x00ff00
                )
                embed.add_field(name="🆔 예약 ID", value=f"`{entry['id']}`", inline=True)
                embed.add_field(name="📢 모드", value=mode_text, inline=True)
                embed.add_field(name="⏰ 예약 시간", value=display_time, inline=True)
                embed.add_field(name="📍 채널", value=self.target_channel.mention, inline=True)
                if self.mention_role:
                    embed.add_field(name="📣 멘션", value=self.mention_role.mention, inline=True)
                embed.add_field(
                    name="📝 내용 미리보기",
                    value=text[:100] + ("..." if len(text) > 100 else ""),
                    inline=False
                )
                embed.set_footer(text="예약을 취소하려면 /공지관리 명령어를 사용하세요.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ 예약 실패",
                    description="공지 예약 저장에 실패했습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="announcement_scheduler 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


def parse_message_link(link: str):
    """
    디스코드 메시지 링크 파싱
    형식: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
    Returns: (guild_id, channel_id, message_id) or None
    """
    pattern = r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)'
    match = re.match(pattern, link.strip())
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return None


# ===== 공지 수정 Modal (이미 전송된 메시지) =====
class AnnouncementEditModal(discord.ui.Modal, title="📝 공지 수정"):
    """이미 전송된 공지를 수정하는 Modal"""

    텍스트 = discord.ui.TextInput(
        label="수정할 내용",
        style=discord.TextStyle.paragraph,
        placeholder="수정할 내용을 입력하세요...",
        required=True,
        max_length=2000
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.target_message = message
        self.텍스트.default = message.content

    async def on_submit(self, interaction: discord.Interaction):
        new_text = self.텍스트.value.replace("\\n", "\n")
        try:
            await self.target_message.edit(content=new_text)
            embed = discord.Embed(
                title="✅ 공지 수정 완료",
                description="공지가 수정되었습니다.",
                color=0x00ff00
            )
            embed.add_field(name="📍 채널", value=f"<#{self.target_message.channel.id}>", inline=True)
            embed.add_field(
                name="📝 수정된 내용 미리보기",
                value=new_text[:100] + ("..." if len(new_text) > 100 else ""),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ 수정 실패",
                description="해당 메시지를 수정할 권한이 없습니다.\n봇이 보낸 메시지만 수정할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 오류 발생",
                description=f"공지 수정 중 오류가 발생했습니다.\n{str(e)[:100]}",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


# ===== 예약 공지 수정 Modal =====
class ScheduledAnnouncementEditModal(discord.ui.Modal, title="📝 예약 공지 수정"):
    """예약된 공지를 수정하는 Modal"""

    텍스트 = discord.ui.TextInput(
        label="수정할 내용",
        style=discord.TextStyle.paragraph,
        placeholder="수정할 내용을 입력하세요...",
        required=True,
        max_length=2000
    )

    def __init__(self, schedule_id: str, current_text: str):
        super().__init__()
        self.schedule_id = schedule_id
        self.텍스트.default = current_text

    async def on_submit(self, interaction: discord.Interaction):
        new_text = self.텍스트.value.replace("\\n", "\n")
        try:
            from announcement_scheduler import announcement_schedule_manager

            success = announcement_schedule_manager.update_schedule_text(self.schedule_id, new_text)
            if success:
                embed = discord.Embed(
                    title="✅ 예약 공지 수정 완료",
                    description=f"예약 `{self.schedule_id}`의 내용이 수정되었습니다.",
                    color=0x00ff00
                )
                embed.add_field(
                    name="📝 수정된 내용 미리보기",
                    value=new_text[:100] + ("..." if len(new_text) > 100 else ""),
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ 수정 실패",
                    description=f"예약 `{self.schedule_id}`을(를) 찾을 수 없습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="announcement_scheduler 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


def setup(bot):
    """봇에 /공지 및 /공지관리 명령어 등록"""

    # ===== /공지 명령어 =====
    @bot.tree.command(name="공지", description="공지를 전송하거나 예약합니다 (팝업으로 내용 입력)")
    @app_commands.describe(
        예약="예약 시간 (형식: YYYY.MM.DD HH:MM)",
        silent="알림 없이 전송 (on: 무음, off: 일반 알림)",
        멘션대상="공지에 멘션할 역할 (@everyone은 역할 없이 자동 포함하지 않음)"
    )
    @app_commands.choices(silent=[
        app_commands.Choice(name="on (무음)", value="on"),
        app_commands.Choice(name="off (알림)", value="off"),
    ])
    @app_commands.check(is_admin)
    async def 공지(
        interaction: discord.Interaction,
        예약: str = None,
        silent: app_commands.Choice[str] = None,
        멘션대상: discord.Role = None
    ):
        """공지 전송/예약 명령어 - Modal 팝업으로 내용 입력"""
        if bot_logger:
            bot_logger.log_command("공지", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.ANNOUNCEMENT,
                                   details={"예약": 예약, "silent": silent.value if silent else None,
                                            "멘션대상": 멘션대상.name if 멘션대상 else None})

        is_silent = silent is not None and silent.value == "on"

        modal = AnnouncementModal(
            scheduled_time=예약,
            is_silent=is_silent,
            channel=interaction.channel,
            mention_role=멘션대상
        )
        await interaction.response.send_modal(modal)

    @공지.error
    async def 공지_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ===== /공지관리 명령어 =====
    @bot.tree.command(name="공지관리", description="예약된 공지를 확인, 취소, 수정합니다")
    @app_commands.describe(
        기능="기능을 선택하세요",
        예약id="예약 ID (취소/수정 시 필수)",
        메시지링크="수정할 메시지 링크 (전송된 공지 수정 시 사용)"
    )
    @app_commands.choices(기능=[
        app_commands.Choice(name="목록", value="목록"),
        app_commands.Choice(name="취소", value="취소"),
        app_commands.Choice(name="수정", value="수정"),
    ])
    @app_commands.check(is_admin)
    async def 공지관리(
        interaction: discord.Interaction,
        기능: app_commands.Choice[str],
        예약id: str = None,
        메시지링크: str = None
    ):
        """공지 예약 관리 명령어"""
        if bot_logger:
            bot_logger.log_command("공지관리", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.ANNOUNCEMENT,
                                   details={"기능": 기능.value})

        try:
            from announcement_scheduler import announcement_schedule_manager

            if 기능.value == "목록":
                schedules = announcement_schedule_manager.get_all_schedules()

                if not schedules:
                    embed = discord.Embed(
                        title="📋 예약된 공지 목록",
                        description="예약된 공지가 없습니다.",
                        color=0x3498db
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"📋 예약된 공지 목록 ({len(schedules)}개)",
                    color=0x3498db
                )

                for s in schedules:
                    try:
                        dt = datetime.strptime(s["scheduled_time"], "%Y-%m-%d %H:%M")
                        display_time = dt.strftime("%Y.%m.%d %H:%M")
                    except ValueError:
                        display_time = s["scheduled_time"]

                    mode = "무음" if s.get("silent") else "일반"
                    preview = s["text"][:50] + ("..." if len(s["text"]) > 50 else "")

                    embed.add_field(
                        name=f"🆔 {s['id']}",
                        value=(
                            f"**채널:** <#{s['channel_id']}>\n"
                            f"**시간:** {display_time}\n"
                            f"**모드:** {mode}\n"
                            f"**내용:** {preview}\n"
                            f"**작성자:** <@{s['created_by']}>"
                        ),
                        inline=False
                    )

                embed.set_footer(text="취소: /공지관리 기능:취소 예약id:<ID> | 수정: /공지관리 기능:수정 예약id:<ID>")
                await interaction.response.send_message(embed=embed, ephemeral=True)

            elif 기능.value == "취소":
                if not 예약id:
                    embed = discord.Embed(
                        title="❌ 오류",
                        description="취소할 예약 ID를 입력해주세요.\n`/공지관리 기능:목록`으로 ID를 확인할 수 있습니다.",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                success = announcement_schedule_manager.remove_schedule(예약id)

                if success:
                    embed = discord.Embed(
                        title="✅ 예약 취소 완료",
                        description=f"예약 `{예약id}`이(가) 취소되었습니다.",
                        color=0x00ff00
                    )
                else:
                    embed = discord.Embed(
                        title="❌ 취소 실패",
                        description=f"예약 `{예약id}`을(를) 찾을 수 없습니다.\n`/공지관리 기능:목록`으로 ID를 확인해주세요.",
                        color=0xff0000
                    )
                await interaction.response.send_message(embed=embed, ephemeral=True)

            elif 기능.value == "수정":
                # 메시지링크가 있으면 → 이미 전송된 공지 수정
                if 메시지링크:
                    parsed = parse_message_link(메시지링크)
                    if not parsed:
                        embed = discord.Embed(
                            title="❌ 링크 오류",
                            description="올바른 디스코드 메시지 링크를 입력해주세요.\n형식: `https://discord.com/channels/서버ID/채널ID/메시지ID`",
                            color=0xff0000
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    guild_id, channel_id, message_id = parsed

                    if guild_id != interaction.guild.id:
                        embed = discord.Embed(
                            title="❌ 오류",
                            description="다른 서버의 메시지는 수정할 수 없습니다.",
                            color=0xff0000
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    channel = bot.get_channel(channel_id)
                    if not channel:
                        embed = discord.Embed(
                            title="❌ 오류",
                            description="채널을 찾을 수 없습니다.",
                            color=0xff0000
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    try:
                        message = await channel.fetch_message(message_id)
                    except discord.NotFound:
                        embed = discord.Embed(
                            title="❌ 오류",
                            description="메시지를 찾을 수 없습니다.",
                            color=0xff0000
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    except discord.Forbidden:
                        embed = discord.Embed(
                            title="❌ 오류",
                            description="해당 채널의 메시지를 읽을 권한이 없습니다.",
                            color=0xff0000
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    if message.author.id != bot.user.id:
                        embed = discord.Embed(
                            title="❌ 오류",
                            description="봇이 보낸 메시지만 수정할 수 있습니다.",
                            color=0xff0000
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    modal = AnnouncementEditModal(message)
                    await interaction.response.send_modal(modal)

                # 예약id가 있으면 → 예약된 공지 수정
                elif 예약id:
                    schedule = announcement_schedule_manager.get_schedule(예약id)
                    if not schedule:
                        embed = discord.Embed(
                            title="❌ 오류",
                            description=f"예약 `{예약id}`을(를) 찾을 수 없습니다.\n`/공지관리 기능:목록`으로 ID를 확인해주세요.",
                            color=0xff0000
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    modal = ScheduledAnnouncementEditModal(예약id, schedule["text"])
                    await interaction.response.send_modal(modal)

                else:
                    embed = discord.Embed(
                        title="❌ 오류",
                        description="수정하려면 **메시지링크** 또는 **예약id** 중 하나를 입력해주세요.\n"
                                    "- 이미 전송된 공지: `메시지링크` 파라미터에 메시지 링크 입력\n"
                                    "- 예약된 공지: `예약id` 파라미터에 예약 ID 입력",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)

        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="announcement_scheduler 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @공지관리.error
    async def 공지관리_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
