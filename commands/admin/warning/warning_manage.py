# commands/admin/warning/warning_manage.py
# /경고관리 명령어 - 경고 시스템 관리 (관리자 전용)

import discord
from discord import app_commands, ui
from typing import Literal
import datetime
import json
import re

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


# 관리자 권한 체크 함수
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def can_modify_warning(guild: discord.Guild, modifier: discord.Member, warned_by_id: int) -> tuple[bool, str]:
    """
    경고를 수정/취소할 권한이 있는지 역할 서열로 판단.
    - 경고를 넣은 관리자(warned_by)보다 역할 서열이 같거나 높아야 수정/취소 가능
    - 서버 소유자는 항상 가능

    Returns:
        (허용 여부, 거부 시 사유 메시지)
    """
    # 서버 소유자 또는 최고 권한 유저는 항상 허용
    SUPER_ADMIN_IDS = {753079165779050647}
    if modifier.id == guild.owner_id or modifier.id in SUPER_ADMIN_IDS:
        return True, ""

    warned_by_member = guild.get_member(warned_by_id)

    # 경고를 넣은 관리자가 서버에 없으면 허용 (퇴장한 관리자)
    if not warned_by_member:
        return True, ""

    # 경고를 넣은 사람 본인이면 허용
    if modifier.id == warned_by_id:
        return True, ""

    # 역할 서열 비교 (top_role.position) — 같은 서열도 불가, 반드시 상위여야 함
    if modifier.top_role.position <= warned_by_member.top_role.position:
        return False, (
            f"이 경고는 <@{warned_by_id}> (역할: {warned_by_member.top_role.name})이(가) 부여했습니다.\n"
            f"상위 관리자만 수정/취소할 수 있습니다."
        )

    return True, ""


def is_valid_punishment(action: str) -> bool:
    """처벌 액션 유효성 검증"""
    if action in ('kick', 'ban'):
        return True
    if re.match(r'^mute_\d+[hm]$', action):
        return True
    return False


class WarningEditModal(ui.Modal, title="경고 수정"):
    """경고 사유 수정 모달"""

    new_reason = ui.TextInput(
        label="수정할 사유",
        placeholder="새로운 경고 사유를 입력하세요",
        required=True,
        max_length=500
    )

    def __init__(self, warning_id: int):
        super().__init__()
        self.warning_id = warning_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from database_manager import db_manager

            # 경고 정보 조회
            warning = db_manager.get_warning_by_id(self.warning_id)
            if not warning:
                await interaction.response.send_message("❌ 경고를 찾을 수 없습니다.", ephemeral=True)
                return

            old_reason = warning['reason']

            # 사유 수정
            success = db_manager.update_warning_reason(self.warning_id, self.new_reason.value)
            if not success:
                await interaction.response.send_message("❌ 경고 사유 수정에 실패했습니다.", ephemeral=True)
                return

            # 행위 로그 기록
            db_manager.log_warning_action(
                warning['guild_id'], warning['discord_id'], interaction.user.id,
                'edit', f"{old_reason} → {self.new_reason.value}", self.warning_id
            )

            # 원본 로그 메시지 임베드 갱신
            warning['reason'] = self.new_reason.value
            guild = interaction.guild
            member = guild.get_member(warning['discord_id'])

            new_embed = await build_warning_log_embed(
                guild, member, warning, db_manager,
                title_prefix="⚠️ 경고 부여 (수정됨)"
            )
            new_embed.add_field(
                name="📝 사유 수정 이력",
                value=f"**이전:** {old_reason}\n**변경:** {self.new_reason.value}\n**수정자:** {interaction.user.mention}",
                inline=False
            )

            await interaction.response.send_message(
                f"✅ 경고 #{self.warning_id} 사유가 수정되었습니다.\n"
                f"**이전:** {old_reason}\n**변경:** {self.new_reason.value}",
                ephemeral=True
            )

            # 메시지 임베드 수정
            await interaction.message.edit(embed=new_embed)

        except Exception as e:
            print(f"[ERROR] 경고 수정 모달 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 오류: {e}", ephemeral=True)
            except:
                pass


class WarningLogView(ui.View):
    """경고 로그 수정/취소 버튼 (영구 View, timeout=None)"""

    def __init__(self, warning_id: int):
        super().__init__(timeout=None)
        self.warning_id = warning_id

        edit_btn = ui.Button(
            label="경고 수정",
            style=discord.ButtonStyle.primary,
            emoji="📝",
            custom_id=f"warning_edit_{warning_id}"
        )
        edit_btn.callback = self.edit_callback
        self.add_item(edit_btn)

        cancel_btn = ui.Button(
            label="경고 취소",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"warning_cancel_{warning_id}"
        )
        cancel_btn.callback = self.cancel_callback
        self.add_item(cancel_btn)

    async def edit_callback(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("❌ 관리자만 사용할 수 있습니다.", ephemeral=True)
            return

        # 역할 서열 체크
        from database_manager import db_manager
        warning = db_manager.get_warning_by_id(self.warning_id)
        if warning:
            allowed, reason = can_modify_warning(interaction.guild, interaction.user, warning['warned_by'])
            if not allowed:
                await interaction.response.send_message(f"❌ 권한 부족\n{reason}", ephemeral=True)
                return

        modal = WarningEditModal(self.warning_id)
        await interaction.response.send_modal(modal)

    async def cancel_callback(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("❌ 관리자만 사용할 수 있습니다.", ephemeral=True)
            return

        try:
            from database_manager import db_manager

            warning = db_manager.get_warning_by_id(self.warning_id)
            if not warning:
                await interaction.response.send_message("❌ 경고를 찾을 수 없습니다.", ephemeral=True)
                return

            if not warning['is_active']:
                await interaction.response.send_message("❌ 이미 비활성화된 경고입니다.", ephemeral=True)
                return

            # 역할 서열 체크
            allowed, reason = can_modify_warning(interaction.guild, interaction.user, warning['warned_by'])
            if not allowed:
                await interaction.response.send_message(f"❌ 권한 부족\n{reason}", ephemeral=True)
                return

            # 경고 비활성화
            success = db_manager.remove_warning(self.warning_id, interaction.user.id)
            if not success:
                await interaction.response.send_message("❌ 경고 취소에 실패했습니다.", ephemeral=True)
                return

            # 행위 로그 기록
            db_manager.log_warning_action(
                warning['guild_id'], warning['discord_id'], interaction.user.id,
                'cancel', warning.get('reason', ''), self.warning_id
            )

            # 임베드 수정 - "취소됨" 표시
            guild = interaction.guild
            member = guild.get_member(warning['discord_id'])

            # 갱신된 경고 정보 가져오기
            updated_warning = db_manager.get_warning_by_id(self.warning_id)

            cancelled_embed = await build_warning_log_embed(
                guild, member, updated_warning or warning, db_manager,
                title_prefix="🗑️ 경고 취소됨"
            )
            cancelled_embed.color = 0x808080
            cancelled_embed.add_field(
                name="🗑️ 취소 정보",
                value=f"**취소자:** {interaction.user.mention}\n**취소 시간:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                inline=False
            )

            # 버튼 비활성화
            disabled_view = ui.View(timeout=None)
            disabled_edit = ui.Button(
                label="경고 수정", style=discord.ButtonStyle.primary,
                emoji="📝", disabled=True, custom_id=f"warning_edit_{self.warning_id}_disabled"
            )
            disabled_cancel = ui.Button(
                label="취소됨", style=discord.ButtonStyle.secondary,
                emoji="🗑️", disabled=True, custom_id=f"warning_cancel_{self.warning_id}_disabled"
            )
            disabled_view.add_item(disabled_edit)
            disabled_view.add_item(disabled_cancel)

            active_count = db_manager.get_active_warning_count(warning['guild_id'], warning['discord_id'])
            await interaction.response.send_message(
                f"✅ 경고 #{self.warning_id}이(가) 취소되었습니다.\n"
                f"**대상:** <@{warning['discord_id']}>\n"
                f"**남은 활성 경고:** {active_count}회",
                ephemeral=True
            )

            await interaction.message.edit(embed=cancelled_embed, view=disabled_view)

        except Exception as e:
            print(f"[ERROR] 경고 취소 실패: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ 오류: {e}", ephemeral=True)
            except:
                pass


async def build_warning_log_embed(guild, member, warning, db_manager,
                                   title_prefix="⚠️ 경고 부여"):
    """경고 로그 임베드 생성 (상세 정보 포함)"""

    warning_id = warning['id']
    discord_id = warning['discord_id']
    guild_id = warning['guild_id']
    warning_count = warning.get('count', 1)

    count_text = f" x{warning_count}" if warning_count > 1 else ""
    embed = discord.Embed(
        title=f"{title_prefix} (#{warning_id}{count_text})",
        color=0xff9900,
        timestamp=datetime.datetime.now()
    )

    # 유저 프로필 사진
    if member:
        embed.set_thumbnail(url=member.display_avatar.url)
        user_text = f"{member.mention}\n**디스코드 ID:** `{discord_id}`"
    else:
        user_text = f"<@{discord_id}>\n**디스코드 ID:** `{discord_id}`"

    embed.add_field(name="👤 대상", value=user_text, inline=False)

    # 사유
    embed.add_field(name="📝 사유", value=warning.get('reason', '사유 없음'), inline=False)

    # 누적 경고 수
    active_count = db_manager.get_active_warning_count(guild_id, discord_id)
    if warning_count > 1:
        embed.add_field(name="🔢 부여 횟수", value=f"**{warning_count}회**", inline=True)
    embed.add_field(name="🔢 누적 경고", value=f"**{active_count}회**", inline=True)

    # 마크 닉네임 히스토리
    user_info = db_manager.get_user_info(discord_id)
    name_history = db_manager.get_name_history(discord_id, limit=5)

    if user_info and user_info.get('current_minecraft_name'):
        current_mc = user_info['current_minecraft_name']
        if name_history and len(name_history) > 1:
            past_names = [h['minecraft_name'] for h in name_history[1:] if h['minecraft_name'] != current_mc]
            if past_names:
                history_text = f"**`{current_mc}`** <- " + " <- ".join(f"`{n}`" for n in past_names)
            else:
                history_text = f"**`{current_mc}`**"
        else:
            history_text = f"**`{current_mc}`**"
    else:
        history_text = "정보 없음"

    embed.add_field(name="🎮 마크 닉네임", value=history_text, inline=False)

    # 경고 기록
    all_warnings = db_manager.get_user_warnings(guild_id, discord_id, active_only=False)
    if all_warnings:
        record_lines = []
        for w in all_warnings[:8]:
            w_id = w['id']
            w_action = w.get('action_type', 'give')
            w_reason = w['reason'] or ''
            if len(w_reason) > 30:
                w_reason = w_reason[:30] + "..."
            w_date = w['created_at'].strftime('%Y-%m-%d') if isinstance(w['created_at'], datetime.datetime) else str(w['created_at'])[:10]

            if w_action == 'give':
                if not w['is_active']:
                    status = "🗑️제거"
                else:
                    status = "🔴활성"
                w_count = w.get('count', 1)
                count_label = f" x{w_count}" if w_count > 1 else ""
                marker = " **← 현재**" if w['id'] == warning_id else ""
                record_lines.append(f"`#{w_id}{count_label}` {w_reason} ({w_date}) {status}{marker}")
            else:
                ref = w.get('reference_id')
                ref_text = f" (#{ref})" if ref else ""
                action_labels = {'cancel': '📝취소', 'edit': '📝수정', 'remove': '📝삭제', 'reset': '📝초기화'}
                label = action_labels.get(w_action, w_action)
                record_lines.append(f"`#{w_id}` {label}{ref_text} ({w_date})")

        if len(all_warnings) > 8:
            record_lines.append(f"... 외 {len(all_warnings) - 8}건")

        embed.add_field(name="📋 경고 기록", value="\n".join(record_lines), inline=False)
    else:
        embed.add_field(name="📋 경고 기록", value="이 경고가 첫 번째 기록입니다.", inline=False)

    # 처리자
    embed.add_field(name="🔧 처리자", value=f"<@{warning['warned_by']}>", inline=True)

    embed.set_footer(text=f"경고 ID: #{warning_id}")

    return embed


async def send_warning_log(guild, db_manager, guild_id, warning, member):
    """경고 로그 채널에 상세 임베드 + 버튼 전송. 성공 시 메시지 객체 반환."""
    try:
        config_data = db_manager.get_warning_config(guild_id)
        log_ch_id = config_data.get('log_channel_id')

        if not log_ch_id:
            print(f"[WARN] 경고 로그 채널 미설정 (guild_id: {guild_id})")
            return None

        log_channel = guild.get_channel(log_ch_id)
        if not log_channel:
            print(f"[WARN] 경고 로그 채널을 찾을 수 없음 (channel_id: {log_ch_id})")
            return None

        embed = await build_warning_log_embed(guild, member, warning, db_manager)
        view = WarningLogView(warning['id'])

        msg = await log_channel.send(embed=embed, view=view)

        # 메시지 ID 저장
        db_manager.update_warning_message_id(warning['id'], msg.id)
        print(f"[OK] 경고 로그 전송 성공: #{warning['id']} -> {log_channel.name}")

        return msg

    except Exception as e:
        print(f"[ERROR] 경고 로그 채널 전송 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


async def send_simple_log(guild, db_manager, guild_id, embed):
    """단순 로그 임베드 전송 (버튼 없이)"""
    try:
        config_data = db_manager.get_warning_config(guild_id)
        log_ch_id = config_data.get('log_channel_id')

        if not log_ch_id:
            return

        log_channel = guild.get_channel(log_ch_id)
        if log_channel:
            await log_channel.send(embed=embed)

    except Exception as e:
        print(f"[ERROR] 로그 채널 전송 실패: {e}")


async def check_and_apply_punishment(guild, member, active_count, db_manager, guild_id):
    """활성 경고 수에 따른 자동 처벌 실행"""
    config_data = db_manager.get_warning_config(guild_id)
    punishments_str = config_data.get('punishments', '{}')

    try:
        punishments = json.loads(punishments_str) if isinstance(punishments_str, str) else punishments_str
    except:
        return

    count_str = str(active_count)
    if count_str not in punishments:
        return

    action = punishments[count_str]
    punishment_text = ""

    try:
        if action == 'kick':
            await member.kick(reason=f"경고 {active_count}회 자동 처벌")
            punishment_text = "서버 추방"

        elif action == 'ban':
            await member.ban(reason=f"경고 {active_count}회 자동 처벌", delete_message_days=0)
            punishment_text = "서버 차단"

        elif action.startswith('mute_'):
            match = re.match(r'mute_(\d+)([hm])', action)
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                if unit == 'h':
                    delta = datetime.timedelta(hours=amount)
                    duration_text = f"{amount}시간"
                else:
                    delta = datetime.timedelta(minutes=amount)
                    duration_text = f"{amount}분"

                await member.timeout(delta, reason=f"경고 {active_count}회 자동 처벌")
                punishment_text = f"{duration_text} 타임아웃"
            else:
                return
        else:
            return

        # 처벌 로그 전송
        punishment_embed = discord.Embed(
            title="🔨 자동 처벌 실행",
            description=f"**대상:** {member.mention}\n"
                        f"**경고 횟수:** {active_count}회\n"
                        f"**처벌:** {punishment_text}",
            color=0xff0000,
            timestamp=datetime.datetime.now()
        )
        await send_simple_log(guild, db_manager, guild_id, punishment_embed)

    except discord.Forbidden:
        print(f"[WARNING] 자동 처벌 권한 부족: {member.id} -> {action}")
    except Exception as e:
        print(f"[ERROR] 자동 처벌 실행 실패: {e}")


def setup(bot):
    """봇에 /경고관리 명령어 등록"""

    @bot.tree.command(name="경고관리", description="경고 시스템을 관리합니다")
    @app_commands.describe(
        기능="실행할 기능 선택",
        유저="대상 사용자",
        사유="제거 사유",
        경고id="특정 경고 ID (경고제거 시)"
    )
    @app_commands.check(is_admin)
    async def 경고관리(
        interaction: discord.Interaction,
        기능: Literal["경고제거", "경고초기화", "경고조회", "경고목록"],
        유저: discord.Member = None,
        사유: str = None,
        경고id: int = None
    ):
        """경고 시스템 관리 - 관리자 전용"""
        from database_manager import db_manager

        guild_id = interaction.guild.id

        # ===== 경고 제거 =====
        if 기능 == "경고제거":
            if not 유저:
                await interaction.response.send_message("대상 사용자를 선택해주세요.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            if bot_logger:
                bot_logger.log_command("경고관리", interaction.user.id, interaction.user.name,
                                       source="admin_command", category=LogCategory.WARNING_SYS,
                                       details={"기능": 기능})

            reason = 사유 or None

            if 경고id:
                # 역할 서열 체크
                target_warning = db_manager.get_warning_by_id(경고id)
                if target_warning:
                    allowed, deny_reason = can_modify_warning(interaction.guild, interaction.user, target_warning['warned_by'])
                    if not allowed:
                        await interaction.followup.send(f"❌ 권한 부족\n{deny_reason}", ephemeral=True)
                        return

                success = db_manager.remove_warning(경고id, interaction.user.id)
                result_text = f"경고 #{경고id}" if success else f"경고 #{경고id}를 찾을 수 없습니다"
            else:
                # 최근 경고의 서열 체크
                user_warnings = db_manager.get_user_warnings(guild_id, 유저.id, active_only=True)
                if user_warnings:
                    latest = user_warnings[0]
                    allowed, deny_reason = can_modify_warning(interaction.guild, interaction.user, latest['warned_by'])
                    if not allowed:
                        await interaction.followup.send(f"❌ 권한 부족\n{deny_reason}", ephemeral=True)
                        return

                removed_id = db_manager.remove_latest_warning(guild_id, 유저.id, interaction.user.id)
                success = removed_id is not None
                result_text = f"경고 #{removed_id}" if success else "활성 경고가 없습니다"

            active_count = db_manager.get_active_warning_count(guild_id, 유저.id)

            embed = discord.Embed(
                title="✅ 경고 제거" if success else "⚠️ 경고 제거 실패",
                description=f"**대상:** {유저.mention}\n**결과:** {result_text}",
                color=0x00ff00 if success else 0xff0000,
                timestamp=datetime.datetime.now()
            )
            if reason:
                embed.add_field(name="사유", value=reason, inline=False)
            embed.add_field(name="남은 활성 경고", value=f"{active_count}회", inline=True)
            embed.set_footer(text=f"처리자: {interaction.user.name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

            if success:
                ref_id = 경고id if 경고id else removed_id
                db_manager.log_warning_action(
                    guild_id, 유저.id, interaction.user.id,
                    'remove', reason or "경고 제거", ref_id
                )
                await send_simple_log(interaction.guild, db_manager, guild_id, embed)

        # ===== 경고 초기화 =====
        elif 기능 == "경고초기화":
            if not 유저:
                await interaction.response.send_message("대상 사용자를 선택해주세요.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            if bot_logger:
                bot_logger.log_command("경고관리", interaction.user.id, interaction.user.name,
                                       source="admin_command", category=LogCategory.WARNING_SYS,
                                       details={"기능": 기능})

            # 역할 서열 체크 - 상위 관리자가 넣은 경고가 포함되어 있으면 차단
            user_warnings = db_manager.get_user_warnings(guild_id, 유저.id, active_only=True)
            for w in user_warnings:
                allowed, deny_reason = can_modify_warning(interaction.guild, interaction.user, w['warned_by'])
                if not allowed:
                    await interaction.followup.send(
                        f"❌ 권한 부족\n"
                        f"경고 #{w['id']}은(는) 상위 관리자가 부여한 경고입니다.\n{deny_reason}\n\n"
                        f"상위 관리자가 부여한 경고가 포함되어 있어 초기화할 수 없습니다.",
                        ephemeral=True
                    )
                    return

            count = db_manager.reset_warnings(guild_id, 유저.id, interaction.user.id)

            embed = discord.Embed(
                title="🔄 경고 초기화",
                description=f"**대상:** {유저.mention}\n**초기화된 경고:** {count}개",
                color=0x00ff00,
                timestamp=datetime.datetime.now()
            )
            if 사유:
                embed.add_field(name="사유", value=사유, inline=False)
            embed.set_footer(text=f"처리자: {interaction.user.name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

            if count > 0:
                db_manager.log_warning_action(
                    guild_id, 유저.id, interaction.user.id,
                    'reset', 사유 or "경고 초기화"
                )
                await send_simple_log(interaction.guild, db_manager, guild_id, embed)

        # ===== 경고 조회 =====
        elif 기능 == "경고조회":
            if not 유저:
                await interaction.response.send_message("조회할 사용자를 선택해주세요.", ephemeral=True)
                return

            warnings = db_manager.get_user_warnings(guild_id, 유저.id, active_only=False)
            active_count = db_manager.get_active_warning_count(guild_id, 유저.id)

            embed = discord.Embed(
                title=f"📋 {유저.display_name}의 경고 내역",
                description=f"**활성 경고:** {active_count}회 | **전체:** {len(warnings)}회",
                color=0xff9900 if active_count > 0 else 0x00ff00
            )
            embed.set_thumbnail(url=유저.display_avatar.url)

            # 마크 닉네임
            user_info = db_manager.get_user_info(유저.id)
            if user_info and user_info.get('current_minecraft_name'):
                embed.add_field(name="🎮 마크 닉네임", value=user_info['current_minecraft_name'], inline=True)

            embed.add_field(name="🆔 디스코드 ID", value=f"`{유저.id}`", inline=True)

            for i, w in enumerate(warnings[:10], 1):
                w_action = w.get('action_type', 'give')
                w_date = w['created_at'].strftime('%Y-%m-%d %H:%M') if isinstance(w['created_at'], datetime.datetime) else str(w['created_at'])[:16]

                if w_action == 'give':
                    if not w['is_active']:
                        status = "🗑️ 제거됨"
                    else:
                        status = "🔴 활성"
                    w_count = w.get('count', 1)
                    count_label = f" (x{w_count})" if w_count > 1 else ""
                    embed.add_field(
                        name=f"#{w['id']}{count_label} - {status}",
                        value=f"**사유:** {w['reason']}\n"
                              f"**일시:** {w_date}\n"
                              f"**처리자:** <@{w['warned_by']}>",
                        inline=False
                    )
                else:
                    action_labels = {'cancel': '취소', 'edit': '수정', 'remove': '삭제', 'reset': '초기화'}
                    label = action_labels.get(w_action, w_action)
                    ref = w.get('reference_id')
                    ref_text = f" (#{ref})" if ref else ""
                    embed.add_field(
                        name=f"#{w['id']} {label}{ref_text} - 📝 기록",
                        value=f"**사유:** {w['reason'] or '-'}\n"
                              f"**일시:** {w_date}\n"
                              f"**처리자:** <@{w['warned_by']}>",
                        inline=False
                    )

            if len(warnings) > 10:
                embed.set_footer(text=f"최근 10건만 표시 (전체 {len(warnings)}건)")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ===== 경고 목록 =====
        elif 기능 == "경고목록":
            warned_users = db_manager.get_all_warned_users(guild_id)

            if not warned_users:
                embed = discord.Embed(
                    title="📋 경고 목록",
                    description="현재 활성 경고가 있는 사용자가 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📋 경고 목록",
                    description=f"총 {len(warned_users)}명의 사용자에게 활성 경고가 있습니다.",
                    color=0xff9900
                )

                for i, user_data in enumerate(warned_users[:15], 1):
                    member = interaction.guild.get_member(user_data['discord_id'])
                    name = member.display_name if member else f"Unknown ({user_data['discord_id']})"
                    mention = member.mention if member else f"<@{user_data['discord_id']}>"

                    embed.add_field(
                        name=f"{i}. {name}",
                        value=f"{mention} - **{user_data['active_count']}회** 경고",
                        inline=False
                    )

                if len(warned_users) > 15:
                    embed.set_footer(text=f"... 외 {len(warned_users) - 15}명")

            await interaction.response.send_message(embed=embed, ephemeral=True)

    # 에러 핸들러
    @경고관리.error
    async def 경고관리_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
