# commands/user/travel/travel_request.py
# /여행신청 명령어 - 여행 신청 (모달 팝업)

import discord
from discord import app_commands, ui
from datetime import datetime, date
import re

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


class TravelRequestModal(ui.Modal, title="여행 신청"):
    """여행 신청 모달 - BASE_NATION 국민용 (목적지 국가 + 날짜)"""

    destination = ui.TextInput(
        label="여행 목적지 국가",
        placeholder="예: Japan, USA 등",
        required=True,
        max_length=100
    )

    start_date = ui.TextInput(
        label="여행 시작일 (YYYY.MM.DD)",
        placeholder="예: 2025.01.20",
        required=True,
        max_length=10
    )

    end_date = ui.TextInput(
        label="여행 종료일 (YYYY.MM.DD)",
        placeholder="예: 2025.01.27",
        required=True,
        max_length=10
    )

    def __init__(self, user_info: dict):
        super().__init__()
        self.user_info = user_info

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            from travel_manager import travel_manager, travel_config_manager, TravelStatus
            from database_manager import db_manager

            # 블랙리스트 확인
            if travel_config_manager.is_blacklisted(interaction.user.id):
                bl_info = travel_config_manager.get_blacklist_info(interaction.user.id)
                reason_text = f"\n사유: {bl_info['reason']}" if bl_info and bl_info.get('reason') else ""
                await interaction.followup.send(
                    f"❌ 여행 블랙리스트에 등록되어 여행 신청이 불가능합니다.{reason_text}",
                    ephemeral=True
                )
                return

            # 날짜 검증
            date_pattern = r'^\d{4}\.\d{2}\.\d{2}$'

            if not re.match(date_pattern, self.start_date.value):
                await interaction.followup.send(
                    "❌ 시작일 형식이 올바르지 않습니다. `YYYY.MM.DD` 형식으로 입력해주세요.",
                    ephemeral=True
                )
                return

            if not re.match(date_pattern, self.end_date.value):
                await interaction.followup.send(
                    "❌ 종료일 형식이 올바르지 않습니다. `YYYY.MM.DD` 형식으로 입력해주세요.",
                    ephemeral=True
                )
                return

            try:
                start = datetime.strptime(self.start_date.value, "%Y.%m.%d").date()
                end = datetime.strptime(self.end_date.value, "%Y.%m.%d").date()
            except ValueError:
                await interaction.followup.send(
                    "❌ 유효하지 않은 날짜입니다. 올바른 날짜를 입력해주세요.",
                    ephemeral=True
                )
                return

            if end < start:
                await interaction.followup.send(
                    "❌ 종료일이 시작일보다 이전입니다.",
                    ephemeral=True
                )
                return

            if start < date.today():
                await interaction.followup.send(
                    "❌ 시작일은 오늘 또는 이후 날짜여야 합니다.",
                    ephemeral=True
                )
                return

            # 여행 일수 계산
            travel_days = (end - start).days + 1

            # 여행 신청 생성
            travel_id = travel_manager.create_travel_request(
                discord_id=interaction.user.id,
                minecraft_name=self.user_info.get('minecraft_name', '알 수 없음'),
                current_nation=self.user_info.get('nation', '알 수 없음'),
                current_town=self.user_info.get('town', '알 수 없음'),
                destination_nation=self.destination.value.strip(),
                start_date=self.start_date.value,
                end_date=self.end_date.value,
                callsign=self.user_info.get('callsign')
            )

            if not travel_id:
                await interaction.followup.send(
                    "❌ 여행 신청 생성에 실패했습니다. 다시 시도해주세요.",
                    ephemeral=True
                )
                return

            # 신청자에게 DM 전송
            try:
                dm_embed = discord.Embed(
                    title="✈️ 여행 신청 완료",
                    description="여행 신청이 접수되었습니다.\n관리진의 승인을 기다려주세요.",
                    color=0x3498db
                )
                dm_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                dm_embed.add_field(name="목적지", value=self.destination.value.strip(), inline=True)
                dm_embed.add_field(name="기간", value=f"{self.start_date.value} ~ {self.end_date.value} ({travel_days}일)", inline=False)
                dm_embed.add_field(name="마크 닉네임", value=self.user_info.get('minecraft_name', '알 수 없음'), inline=True)
                dm_embed.add_field(name="현재 국가", value=self.user_info.get('nation', '알 수 없음'), inline=True)
                dm_embed.set_footer(text="승인/기각 결과는 DM으로 알려드립니다.")

                await interaction.user.send(embed=dm_embed)
            except discord.Forbidden:
                pass  # DM 전송 실패 무시

            # 관리 채널에 신청 알림 전송
            request_channel_id = travel_config_manager.get_request_channel()
            if request_channel_id:
                channel = interaction.guild.get_channel(request_channel_id)
                if channel:
                    admin_embed = discord.Embed(
                        title="✈️ 새 여행 신청",
                        description=f"{interaction.user.mention}님이 여행을 신청했습니다.",
                        color=0xf39c12
                    )
                    admin_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                    admin_embed.add_field(name="신청자", value=f"{interaction.user.mention}", inline=True)
                    admin_embed.add_field(name="마크 닉네임", value=self.user_info.get('minecraft_name', '알 수 없음'), inline=True)
                    admin_embed.add_field(name="콜사인", value=self.user_info.get('callsign') or '없음', inline=True)
                    admin_embed.add_field(name="현재 국가", value=self.user_info.get('nation', '알 수 없음'), inline=True)
                    admin_embed.add_field(name="현재 마을", value=self.user_info.get('town', '알 수 없음'), inline=True)
                    admin_embed.add_field(name="목적지 국가", value=self.destination.value.strip(), inline=True)
                    admin_embed.add_field(name="여행 기간", value=f"{self.start_date.value} ~ {self.end_date.value}", inline=True)
                    admin_embed.add_field(name="여행 일수", value=f"{travel_days}일", inline=True)
                    admin_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    admin_embed.set_footer(text=f"신청 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    # 관리 역할 멘션 생성
                    manager_roles = travel_config_manager.get_manager_roles()
                    role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                    # 수락/기각 버튼 추가
                    view = TravelReviewView(travel_id)
                    msg = await channel.send(content=role_mentions if role_mentions else None, embed=admin_embed, view=view)

                    # 메시지 ID 저장
                    travel_manager.update_message_id(travel_id, msg.id)

            # 성공 메시지
            embed = discord.Embed(
                title="✅ 여행 신청 완료",
                description=f"여행 신청이 접수되었습니다.\n신청 ID: `{travel_id}`",
                color=0x00ff00
            )
            embed.add_field(name="목적지", value=self.destination.value.strip(), inline=True)
            embed.add_field(name="기간", value=f"{self.start_date.value} ~ {self.end_date.value} ({travel_days}일)", inline=False)
            embed.set_footer(text="관리진의 승인을 기다려주세요. 결과는 DM으로 알려드립니다.")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)


class TravelRequestForeignerModal(ui.Modal, title="여행 신청"):
    """여행 신청 모달 - 외국인용 (날짜만 입력, 목적지는 BASE_NATION 고정)"""

    start_date = ui.TextInput(
        label="여행 시작일 (YYYY.MM.DD)",
        placeholder="예: 2025.01.20",
        required=True,
        max_length=10
    )

    end_date = ui.TextInput(
        label="여행 종료일 (YYYY.MM.DD)",
        placeholder="예: 2025.01.27",
        required=True,
        max_length=10
    )

    def __init__(self, user_info: dict, base_nation: str):
        super().__init__()
        self.user_info = user_info
        self.base_nation = base_nation

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            from travel_manager import travel_manager, travel_config_manager

            # 블랙리스트 확인
            if travel_config_manager.is_blacklisted(interaction.user.id):
                bl_info = travel_config_manager.get_blacklist_info(interaction.user.id)
                reason_text = f"\n사유: {bl_info['reason']}" if bl_info and bl_info.get('reason') else ""
                await interaction.followup.send(
                    f"❌ 여행 블랙리스트에 등록되어 여행 신청이 불가능합니다.{reason_text}",
                    ephemeral=True
                )
                return

            # 날짜 검증
            date_pattern = r'^\d{4}\.\d{2}\.\d{2}$'

            if not re.match(date_pattern, self.start_date.value):
                await interaction.followup.send(
                    "❌ 시작일 형식이 올바르지 않습니다. `YYYY.MM.DD` 형식으로 입력해주세요.",
                    ephemeral=True
                )
                return

            if not re.match(date_pattern, self.end_date.value):
                await interaction.followup.send(
                    "❌ 종료일 형식이 올바르지 않습니다. `YYYY.MM.DD` 형식으로 입력해주세요.",
                    ephemeral=True
                )
                return

            try:
                start = datetime.strptime(self.start_date.value, "%Y.%m.%d").date()
                end = datetime.strptime(self.end_date.value, "%Y.%m.%d").date()
            except ValueError:
                await interaction.followup.send(
                    "❌ 유효하지 않은 날짜입니다. 올바른 날짜를 입력해주세요.",
                    ephemeral=True
                )
                return

            if end < start:
                await interaction.followup.send(
                    "❌ 종료일이 시작일보다 이전입니다.",
                    ephemeral=True
                )
                return

            if start < date.today():
                await interaction.followup.send(
                    "❌ 시작일은 오늘 또는 이후 날짜여야 합니다.",
                    ephemeral=True
                )
                return

            # 여행 일수 계산
            travel_days = (end - start).days + 1

            # 여행 신청 생성 (목적지는 BASE_NATION으로 고정)
            travel_id = travel_manager.create_travel_request(
                discord_id=interaction.user.id,
                minecraft_name=self.user_info.get('minecraft_name', '알 수 없음'),
                current_nation=self.user_info.get('nation', '알 수 없음'),
                current_town=self.user_info.get('town', '알 수 없음'),
                destination_nation=self.base_nation,
                start_date=self.start_date.value,
                end_date=self.end_date.value,
                callsign=self.user_info.get('callsign')
            )

            if not travel_id:
                await interaction.followup.send(
                    "❌ 여행 신청 생성에 실패했습니다. 다시 시도해주세요.",
                    ephemeral=True
                )
                return

            # 신청자에게 DM 전송
            try:
                dm_embed = discord.Embed(
                    title="✈️ 여행 신청 완료",
                    description="여행 신청이 접수되었습니다.\n관리진의 승인을 기다려주세요.",
                    color=0x3498db
                )
                dm_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                dm_embed.add_field(name="목적지", value=self.base_nation, inline=True)
                dm_embed.add_field(name="기간", value=f"{self.start_date.value} ~ {self.end_date.value} ({travel_days}일)", inline=False)
                dm_embed.add_field(name="마크 닉네임", value=self.user_info.get('minecraft_name', '알 수 없음'), inline=True)
                dm_embed.add_field(name="현재 국가", value=self.user_info.get('nation', '알 수 없음'), inline=True)
                dm_embed.set_footer(text="승인/기각 결과는 DM으로 알려드립니다.")

                await interaction.user.send(embed=dm_embed)
            except discord.Forbidden:
                pass  # DM 전송 실패 무시

            # 관리 채널에 신청 알림 전송
            request_channel_id = travel_config_manager.get_request_channel()
            if request_channel_id:
                channel = interaction.guild.get_channel(request_channel_id)
                if channel:
                    admin_embed = discord.Embed(
                        title="✈️ 새 여행 신청 (외국인)",
                        description=f"{interaction.user.mention}님이 여행을 신청했습니다.",
                        color=0xf39c12
                    )
                    admin_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                    admin_embed.add_field(name="신청자", value=f"{interaction.user.mention}", inline=True)
                    admin_embed.add_field(name="마크 닉네임", value=self.user_info.get('minecraft_name', '알 수 없음'), inline=True)
                    admin_embed.add_field(name="콜사인", value=self.user_info.get('callsign') or '없음', inline=True)
                    admin_embed.add_field(name="현재 국가", value=self.user_info.get('nation', '알 수 없음'), inline=True)
                    admin_embed.add_field(name="현재 마을", value=self.user_info.get('town', '알 수 없음'), inline=True)
                    admin_embed.add_field(name="목적지 국가", value=self.base_nation, inline=True)
                    admin_embed.add_field(name="여행 기간", value=f"{self.start_date.value} ~ {self.end_date.value}", inline=True)
                    admin_embed.add_field(name="여행 일수", value=f"{travel_days}일", inline=True)
                    admin_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    admin_embed.set_footer(text=f"신청 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    # 관리 역할 멘션 생성
                    manager_roles = travel_config_manager.get_manager_roles()
                    role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                    # 수락/기각 버튼 추가
                    view = TravelReviewView(travel_id)
                    msg = await channel.send(content=role_mentions if role_mentions else None, embed=admin_embed, view=view)

                    # 메시지 ID 저장
                    travel_manager.update_message_id(travel_id, msg.id)

            # 성공 메시지
            embed = discord.Embed(
                title="✅ 여행 신청 완료",
                description=f"여행 신청이 접수되었습니다.\n신청 ID: `{travel_id}`",
                color=0x00ff00
            )
            embed.add_field(name="목적지", value=self.base_nation, inline=True)
            embed.add_field(name="기간", value=f"{self.start_date.value} ~ {self.end_date.value} ({travel_days}일)", inline=False)
            embed.set_footer(text="관리진의 승인을 기다려주세요. 결과는 DM으로 알려드립니다.")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)


class TravelReviewReasonModal(ui.Modal):
    """수락/기각 사유 입력 모달"""

    reason = ui.TextInput(
        label="사유 (선택사항)",
        placeholder="사유를 입력해주세요 (생략 가능)",
        required=False,
        max_length=500,
        style=discord.TextStyle.paragraph
    )

    original_nation = ui.TextInput(
        label="원래 소속 국가 (선택사항)",
        placeholder="유저의 원래 국가명 입력 → 국민이면 조직원, 아니면 외국인 역할 자동 처리",
        required=False,
        max_length=100,
        style=discord.TextStyle.short
    )

    def __init__(self, travel_id: str, action: str):
        super().__init__(title=f"여행 {action}")
        self.travel_id = travel_id
        self.action = action  # "승인" or "기각"

    async def _apply_travel_roles(self, member: discord.Member, original_nation: str, guild: discord.Guild):
        """원래 국가 기반으로 조직원/외국인 역할 자동 처리"""
        from config import config

        success_role_id = config.SUCCESS_ROLE_ID
        success_role_out_id = config.SUCCESS_ROLE_ID_OUT
        base_nation = config.BASE_NATION
        base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)

        if not success_role_id:
            return None

        # 원래 국가가 base nation인지 확인
        is_base = False
        if base_nation_uuid:
            # bulk 캐시에서 UUID 비교 시도
            try:
                from bulk_updater import bulk_data_manager
                nation_info = bulk_data_manager.get_nation_by_name(original_nation)
                if nation_info and nation_info.get('uuid') == base_nation_uuid:
                    is_base = True
                elif base_nation and original_nation.lower() == base_nation.lower():
                    is_base = True
            except Exception:
                if base_nation and original_nation.lower() == base_nation.lower():
                    is_base = True
        else:
            if base_nation and original_nation.lower() == base_nation.lower():
                is_base = True

        changes = []

        if is_base:
            # 국민 → 조직원 역할 추가, 외국인 역할 제거
            success_role = guild.get_role(success_role_id)
            if success_role and success_role not in member.roles:
                try:
                    await member.add_roles(success_role)
                    changes.append(f"+{success_role.name}")
                except Exception as e:
                    print(f"[TRAVEL] 조직원 역할 추가 실패: {e}")

            if success_role_out_id:
                out_role = guild.get_role(success_role_out_id)
                if out_role and out_role in member.roles:
                    try:
                        await member.remove_roles(out_role)
                        changes.append(f"-{out_role.name}")
                    except Exception as e:
                        print(f"[TRAVEL] 외국인 역할 제거 실패: {e}")
        else:
            # 외국인 → 외국인 역할 추가, 조직원 역할 제거
            if success_role_out_id:
                out_role = guild.get_role(success_role_out_id)
                if out_role and out_role not in member.roles:
                    try:
                        await member.add_roles(out_role)
                        changes.append(f"+{out_role.name}")
                    except Exception as e:
                        print(f"[TRAVEL] 외국인 역할 추가 실패: {e}")

            success_role = guild.get_role(success_role_id)
            if success_role and success_role in member.roles:
                try:
                    await member.remove_roles(success_role)
                    changes.append(f"-{success_role.name}")
                except Exception as e:
                    print(f"[TRAVEL] 조직원 역할 제거 실패: {e}")

        role_type = "국민(조직원)" if is_base else "외국인"
        print(f"[TRAVEL] 역할 처리: {member.display_name} → {role_type} [{', '.join(changes)}]")
        return is_base

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            from travel_manager import travel_manager, travel_config_manager
            from database_manager import db_manager

            travel = travel_manager.get_travel(self.travel_id)
            if not travel:
                await interaction.followup.send("❌ 해당 여행 신청을 찾을 수 없습니다.", ephemeral=True)
                return

            # 권한 확인
            if not travel_config_manager.is_manager(interaction.user):
                await interaction.followup.send("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
                return

            reason = self.reason.value.strip() if self.reason.value else None
            orig_nation = self.original_nation.value.strip() if self.original_nation.value else None

            if self.action == "승인":
                success = travel_manager.approve_travel(self.travel_id, interaction.user.id, reason)
                status_text = "승인됨"
                color = 0x00ff00

                # 원래 국가 정보 저장
                if orig_nation:
                    travel_manager.set_original_nation(self.travel_id, orig_nation)
            else:
                success = travel_manager.reject_travel(self.travel_id, interaction.user.id, reason)
                status_text = "기각됨"
                color = 0xff0000

            if not success:
                await interaction.followup.send(f"❌ 여행 {self.action} 처리에 실패했습니다.", ephemeral=True)
                return

            # 승인 시 원래 국가 기반 역할 처리
            role_change_msg = ""
            if self.action == "승인" and orig_nation and interaction.guild:
                applicant = interaction.guild.get_member(travel["discord_id"])
                if applicant:
                    is_base = await self._apply_travel_roles(applicant, orig_nation, interaction.guild)
                    role_type = "국민(조직원)" if is_base else "외국인"
                    role_change_msg = f"\n🏷️ 원래 국가: **{orig_nation}** → **{role_type}** 역할 적용됨"

            # 신청자에게 DM 전송
            dm_failed = False
            try:
                applicant = interaction.guild.get_member(travel["discord_id"])
                if applicant:
                    dm_embed = discord.Embed(
                        title=f"✈️ 여행 신청 {status_text}",
                        description=f"여행 신청이 **{status_text}**되었습니다.",
                        color=color
                    )
                    dm_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                    dm_embed.add_field(name="목적지", value=travel["destination_nation"], inline=True)
                    dm_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=False)
                    if reason:
                        dm_embed.add_field(name="사유", value=reason, inline=False)
                    dm_embed.add_field(name="처리자", value=interaction.user.display_name, inline=True)
                    dm_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    # 승인된 경우 DM에 취소/종료 버튼 추가
                    if self.action == "승인":
                        # 외국인 국내 여행인지 확인 (목적지가 BASE_NATION)
                        from config import config as _cfg
                        _base = getattr(_cfg, 'BASE_NATION', 'Red_Mafia')
                        is_foreigner_travel = (
                            travel.get("destination_nation", "").lower() == _base.lower()
                        )

                        if is_foreigner_travel:
                            dm_embed.add_field(
                                name="📌 마을 초대 안내",
                                value=f"`/t leave` 로 마을을 나간 뒤에 아래 `초대 요청` 버튼을 눌러 초대를 요청하세요.",
                                inline=False
                            )

                        dm_embed.add_field(
                            name="💡 안내",
                            value="여행을 조기 취소하거나 종료하려면 아래 버튼을 사용하세요.\n(시작일 2일 전부터 취소 가능)",
                            inline=False
                        )
                        view = TravelUserControlView(self.travel_id, travel["discord_id"], show_invite=is_foreigner_travel)
                        await applicant.send(embed=dm_embed, view=view)
                    else:
                        await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                dm_failed = True

            # DM 실패 시 로그 채널에 알림
            if dm_failed:
                log_channel_id = travel_config_manager.get_log_channel()
                if log_channel_id and interaction.guild:
                    log_channel = interaction.guild.get_channel(log_channel_id)
                    if log_channel:
                        manager_roles = travel_config_manager.get_manager_roles()
                        role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                        dm_fail_embed = discord.Embed(
                            title="⚠️ DM 전송 실패",
                            description=f"<@{travel['discord_id']}>님에게 여행 {status_text} 알림을 전송할 수 없습니다.\n**DM이 차단되어 있습니다.**",
                            color=0xff9900
                        )
                        dm_fail_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        dm_fail_embed.add_field(name="마크 닉네임", value=travel.get("minecraft_name", "알 수 없음"), inline=True)
                        dm_fail_embed.add_field(name="처리 결과", value=status_text, inline=True)
                        dm_fail_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                        await log_channel.send(content=role_mentions if role_mentions else None, embed=dm_fail_embed)

            # 로그 채널에 기록
            log_channel_id = travel_config_manager.get_log_channel()
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title=f"📋 여행 신청 {status_text}",
                        color=color
                    )
                    log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                    log_embed.add_field(name="신청자", value=f"<@{travel['discord_id']}>", inline=True)
                    log_embed.add_field(name="마크 닉네임", value=travel["minecraft_name"], inline=True)
                    log_embed.add_field(name="목적지", value=travel["destination_nation"], inline=True)
                    log_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=True)
                    log_embed.add_field(name="처리자", value=interaction.user.mention, inline=True)
                    if orig_nation:
                        log_embed.add_field(name="원래 국가", value=orig_nation, inline=True)
                    if reason:
                        log_embed.add_field(name="사유", value=reason, inline=False)
                    log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    await log_channel.send(embed=log_embed)

            # 원본 메시지 수정
            try:
                # 메시지 임베드 업데이트
                message = interaction.message
                if message:
                    updated_embed = message.embeds[0] if message.embeds else None
                    if updated_embed:
                        updated_embed.color = color
                        updated_embed.title = f"✈️ 여행 신청 - {status_text}"
                        result_text = f"**{status_text}** by {interaction.user.mention}"
                        if orig_nation:
                            result_text += f"\n원래 국가: **{orig_nation}**"
                        updated_embed.add_field(name="처리 결과", value=result_text, inline=False)
                        if reason:
                            updated_embed.add_field(name="사유", value=reason, inline=False)

                        # 승인된 경우 관리용 버튼 추가, 기각된 경우 버튼 제거
                        if self.action == "승인":
                            admin_view = TravelAdminControlView(self.travel_id, travel["discord_id"])
                            await message.edit(embed=updated_embed, view=admin_view)
                        else:
                            await message.edit(embed=updated_embed, view=None)
            except Exception as e:
                print(f"메시지 수정 실패: {e}")

            result_msg = f"✅ 여행 신청이 **{status_text}**되었습니다.{role_change_msg}"
            await interaction.followup.send(result_msg, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)


class TravelReviewView(ui.View):
    """여행 신청 수락/기각 버튼 뷰 (영구 View)"""

    def __init__(self, travel_id: str):
        super().__init__(timeout=None)
        self.travel_id = travel_id

        # 동적 custom_id로 버튼 추가 (봇 재시작 후에도 유지)
        approve_btn = ui.Button(
            label="수락",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"travel_approve_{travel_id}"
        )
        approve_btn.callback = self.approve_callback
        self.add_item(approve_btn)

        reject_btn = ui.Button(
            label="기각",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"travel_reject_{travel_id}"
        )
        reject_btn.callback = self.reject_callback
        self.add_item(reject_btn)

    async def approve_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_config_manager

        # 권한 확인
        if not travel_config_manager.is_manager(interaction.user):
            await interaction.response.send_message("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
            return

        modal = TravelReviewReasonModal(self.travel_id, "승인")
        await interaction.response.send_modal(modal)

    async def reject_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_config_manager

        # 권한 확인
        if not travel_config_manager.is_manager(interaction.user):
            await interaction.response.send_message("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
            return

        modal = TravelReviewReasonModal(self.travel_id, "기각")
        await interaction.response.send_modal(modal)


class TravelAdminControlView(ui.View):
    """관리자용 여행 취소/종료 버튼 뷰 (영구 View)"""

    def __init__(self, travel_id: str, user_discord_id: int):
        super().__init__(timeout=None)
        self.travel_id = travel_id
        self.user_discord_id = user_discord_id

        # 동적 custom_id로 버튼 추가
        cancel_btn = ui.Button(
            label="여행 취소",
            style=discord.ButtonStyle.danger,
            emoji="🚫",
            custom_id=f"travel_admin_cancel_{travel_id}"
        )
        cancel_btn.callback = self.cancel_callback
        self.add_item(cancel_btn)

        end_btn = ui.Button(
            label="여행 종료",
            style=discord.ButtonStyle.secondary,
            emoji="🏁",
            custom_id=f"travel_admin_end_{travel_id}"
        )
        end_btn.callback = self.end_callback
        self.add_item(end_btn)

    async def cancel_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager

        # 권한 확인
        if not travel_config_manager.is_manager(interaction.user):
            await interaction.response.send_message("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
            return

        travel = travel_manager.get_travel(self.travel_id)
        if not travel:
            await interaction.response.send_message("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
            return

        if travel["status"] not in ["approved", "active"]:
            await interaction.response.send_message("❌ 이미 종료되었거나 취소된 여행입니다.", ephemeral=True)
            return

        # 여행 취소 처리
        success = travel_manager.cancel_travel(self.travel_id)
        if success:
            db_manager.set_user_traveling(self.user_discord_id, False)

            # 임베드 업데이트
            updated_embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if updated_embed:
                updated_embed.color = 0xff0000
                updated_embed.title = "✈️ 여행 신청 - 취소됨"
                updated_embed.add_field(name="취소 처리", value=f"관리자 {interaction.user.mention}에 의해 취소됨", inline=False)
                await interaction.message.edit(embed=updated_embed, view=None)

            # 신청자에게 DM 전송
            dm_failed = False
            try:
                guild = interaction.guild
                if guild:
                    applicant = guild.get_member(self.user_discord_id)
                    if applicant:
                        dm_embed = discord.Embed(
                            title="🚫 여행이 취소되었습니다",
                            description=f"관리자에 의해 여행이 취소되었습니다.",
                            color=0xff0000
                        )
                        dm_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        dm_embed.add_field(name="처리자", value=interaction.user.display_name, inline=True)
                        await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                dm_failed = True

            # DM 실패 시 로그 채널에 알림
            if dm_failed:
                await self._notify_dm_failed(interaction, travel, "취소")

            # 로그 채널에 취소 기록
            log_channel_id = travel_config_manager.get_log_channel()
            if log_channel_id and interaction.guild:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="📋 여행 취소 (관리자)",
                        color=0xff0000
                    )
                    log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                    log_embed.add_field(name="대상자", value=f"<@{self.user_discord_id}>", inline=True)
                    log_embed.add_field(name="마크 닉네임", value=travel.get('minecraft_name', '?'), inline=True)
                    log_embed.add_field(name="목적지", value=travel.get('destination_nation', '?'), inline=True)
                    log_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=True)
                    log_embed.add_field(name="처리자", value=interaction.user.mention, inline=True)
                    log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    await log_channel.send(embed=log_embed)

            await interaction.response.send_message("✅ 여행이 취소되었습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 여행 취소에 실패했습니다.", ephemeral=True)

    async def end_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager

        # 권한 확인
        if not travel_config_manager.is_manager(interaction.user):
            await interaction.response.send_message("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
            return

        travel = travel_manager.get_travel(self.travel_id)
        if not travel:
            await interaction.response.send_message("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
            return

        if travel["status"] not in ["approved", "active"]:
            await interaction.response.send_message("❌ 이미 종료되었거나 취소된 여행입니다.", ephemeral=True)
            return

        # 여행 종료 처리
        success = travel_manager.complete_travel(self.travel_id)
        if success:
            db_manager.set_user_traveling(self.user_discord_id, False)

            # 원래 국가 기반 역할 복원
            role_restored = False
            try:
                guild = interaction.guild
                if guild and travel.get('original_nation'):
                    applicant = guild.get_member(self.user_discord_id)
                    if applicant:
                        from travel_scheduler import restore_travel_roles
                        await restore_travel_roles(applicant, travel, guild)
                        role_restored = True
            except Exception as e:
                print(f"[TRAVEL] 역할 복원 오류: {e}")

            # 임베드 업데이트
            updated_embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if updated_embed:
                updated_embed.color = 0x808080
                updated_embed.title = "✈️ 여행 신청 - 종료됨"
                end_text = f"관리자 {interaction.user.mention}에 의해 조기 종료됨"
                if role_restored:
                    end_text += f"\n🏷️ 원래 국가({travel['original_nation']}) 기반 역할 복원됨"
                updated_embed.add_field(name="종료 처리", value=end_text, inline=False)
                await interaction.message.edit(embed=updated_embed, view=None)

            # 신청자에게 DM 전송
            dm_failed = False
            try:
                guild = interaction.guild
                if guild:
                    applicant = guild.get_member(self.user_discord_id)
                    if applicant:
                        dm_embed = discord.Embed(
                            title="🏁 여행이 종료되었습니다",
                            description=f"관리자에 의해 여행이 조기 종료되었습니다.\n이제부터 역할/닉네임 변동이 정상적으로 적용됩니다.",
                            color=0x808080
                        )
                        dm_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        dm_embed.add_field(name="처리자", value=interaction.user.display_name, inline=True)
                        await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                dm_failed = True

            # DM 실패 시 로그 채널에 알림
            if dm_failed:
                await self._notify_dm_failed(interaction, travel, "종료")

            # 로그 채널에 종료 기록
            log_channel_id = travel_config_manager.get_log_channel()
            if log_channel_id and interaction.guild:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="📋 여행 조기 종료 (관리자)",
                        color=0x808080
                    )
                    log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                    log_embed.add_field(name="대상자", value=f"<@{self.user_discord_id}>", inline=True)
                    log_embed.add_field(name="마크 닉네임", value=travel.get('minecraft_name', '?'), inline=True)
                    log_embed.add_field(name="목적지", value=travel.get('destination_nation', '?'), inline=True)
                    log_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=True)
                    log_embed.add_field(name="처리자", value=interaction.user.mention, inline=True)
                    if role_restored:
                        log_embed.add_field(name="역할 복원", value=f"원래 국가: {travel.get('original_nation', '?')}", inline=False)
                    log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    await log_channel.send(embed=log_embed)

            await interaction.response.send_message("✅ 여행이 종료되었습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 여행 종료에 실패했습니다.", ephemeral=True)

    async def _notify_dm_failed(self, interaction: discord.Interaction, travel: dict, action: str):
        """DM 전송 실패 시 로그 채널에 알림"""
        from travel_manager import travel_config_manager

        log_channel_id = travel_config_manager.get_log_channel()
        if log_channel_id and interaction.guild:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                manager_roles = travel_config_manager.get_manager_roles()
                role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                embed = discord.Embed(
                    title="⚠️ DM 전송 실패",
                    description=f"<@{self.user_discord_id}>님에게 여행 {action} 알림을 전송할 수 없습니다.\n**DM이 차단되어 있습니다.**",
                    color=0xff9900
                )
                embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                embed.add_field(name="마크 닉네임", value=travel.get("minecraft_name", "알 수 없음"), inline=True)
                embed.add_field(name="처리 내용", value=f"여행 {action}", inline=True)
                embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                await log_channel.send(content=role_mentions if role_mentions else None, embed=embed)


class TravelExtendModal(ui.Modal, title="여행 연장"):
    """여행 연장 시 새 종료일 입력 모달"""

    new_end_date = ui.TextInput(
        label="새 종료일 (YYYY.MM.DD)",
        placeholder="예: 2025.02.15",
        required=True,
        max_length=10
    )

    def __init__(self, travel_id: str, user_discord_id: int):
        super().__init__()
        self.travel_id = travel_id
        self.user_discord_id = user_discord_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            from travel_manager import travel_manager, travel_config_manager
            from database_manager import db_manager

            # 권한 확인
            if not travel_config_manager.is_manager(interaction.user):
                await interaction.followup.send("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
                return

            travel = travel_manager.get_travel(self.travel_id)
            if not travel:
                await interaction.followup.send("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
                return

            # 날짜 검증
            date_pattern = r'^\d{4}\.\d{2}\.\d{2}$'
            if not re.match(date_pattern, self.new_end_date.value):
                await interaction.followup.send("❌ 날짜 형식이 올바르지 않습니다. `YYYY.MM.DD` 형식으로 입력해주세요.", ephemeral=True)
                return

            try:
                new_end = datetime.strptime(self.new_end_date.value, "%Y.%m.%d").date()
            except ValueError:
                await interaction.followup.send("❌ 유효하지 않은 날짜입니다.", ephemeral=True)
                return

            if new_end <= date.today():
                await interaction.followup.send("❌ 새 종료일은 오늘 이후여야 합니다.", ephemeral=True)
                return

            # 여행 연장 처리
            success = travel_manager.extend_travel(self.travel_id, self.new_end_date.value)
            if not success:
                await interaction.followup.send("❌ 여행 연장에 실패했습니다.", ephemeral=True)
                return

            db_manager.set_user_traveling(self.user_discord_id, True)

            # 임베드 업데이트
            if interaction.message:
                updated_embed = interaction.message.embeds[0] if interaction.message.embeds else None
                if updated_embed:
                    updated_embed.color = 0x00ff00
                    updated_embed.title = "⏳ 여행 미복귀 - 연장 처리됨"
                    updated_embed.add_field(
                        name="연장 처리",
                        value=f"관리자 {interaction.user.mention}에 의해 연장됨\n새 종료일: **{self.new_end_date.value}**",
                        inline=False
                    )
                    # 연장 후에는 일반 관리 버튼으로 교체
                    admin_view = TravelAdminControlView(self.travel_id, self.user_discord_id)
                    await interaction.message.edit(embed=updated_embed, view=admin_view)

            # 신청자에게 DM 전송
            try:
                from config import config
                bot = interaction.client
                guild = bot.get_guild(config.GUILD_ID) if config.GUILD_ID else (interaction.guild)
                if guild:
                    applicant = guild.get_member(self.user_discord_id)
                    if applicant:
                        dm_embed = discord.Embed(
                            title="⏳ 여행이 연장되었습니다",
                            description=f"관리자에 의해 여행 기간이 연장되었습니다.\n"
                                       f"새 종료일: **{self.new_end_date.value}**\n"
                                       f"연장된 기간 동안 역할/닉네임 변동이 적용되지 않습니다.",
                            color=0x00ff00
                        )
                        dm_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        dm_embed.add_field(name="목적지", value=travel.get('destination_nation', '?'), inline=True)
                        dm_embed.add_field(name="새 종료일", value=self.new_end_date.value, inline=True)
                        await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass

            # 로그 채널에 기록
            log_channel_id = travel_config_manager.get_log_channel()
            if log_channel_id:
                guild = interaction.guild
                if not guild:
                    from config import config
                    guild = interaction.client.get_guild(config.GUILD_ID)
                if guild:
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="📋 여행 연장 처리",
                            color=0x00ff00
                        )
                        log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        log_embed.add_field(name="대상자", value=f"<@{self.user_discord_id}>", inline=True)
                        log_embed.add_field(name="마크 닉네임", value=travel.get('minecraft_name', '?'), inline=True)
                        log_embed.add_field(name="목적지", value=travel.get('destination_nation', '?'), inline=True)
                        log_embed.add_field(name="새 종료일", value=self.new_end_date.value, inline=True)
                        log_embed.add_field(name="처리자", value=interaction.user.mention, inline=True)
                        log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        await log_channel.send(embed=log_embed)

            await interaction.followup.send(
                f"✅ 여행이 **{self.new_end_date.value}**까지 연장되었습니다.",
                ephemeral=True
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)


class TravelOverstayView(ui.View):
    """여행 종료 후 미복귀 시 관리자용 연장/정착 버튼 뷰 (영구 View)"""

    def __init__(self, travel_id: str, user_discord_id: int):
        super().__init__(timeout=None)
        self.travel_id = travel_id
        self.user_discord_id = user_discord_id

        # 여행 연장 버튼
        extend_btn = ui.Button(
            label="여행 연장",
            style=discord.ButtonStyle.primary,
            emoji="⏳",
            custom_id=f"travel_overstay_extend_{travel_id}"
        )
        extend_btn.callback = self.extend_callback
        self.add_item(extend_btn)

        # 정착 처리 버튼
        settle_btn = ui.Button(
            label="정착 처리",
            style=discord.ButtonStyle.success,
            emoji="🏠",
            custom_id=f"travel_overstay_settle_{travel_id}"
        )
        settle_btn.callback = self.settle_callback
        self.add_item(settle_btn)

        # 여행 종료 버튼
        end_btn = ui.Button(
            label="여행 종료",
            style=discord.ButtonStyle.danger,
            emoji="🏁",
            custom_id=f"travel_overstay_end_{travel_id}"
        )
        end_btn.callback = self.end_callback
        self.add_item(end_btn)

    async def end_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager

        # 권한 확인
        if not travel_config_manager.is_manager(interaction.user):
            await interaction.response.send_message("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
            return

        travel = travel_manager.get_travel(self.travel_id)
        if not travel:
            await interaction.response.send_message("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
            return

        if travel["status"] == "completed":
            await interaction.response.send_message("❌ 이미 종료된 여행입니다.", ephemeral=True)
            return

        # 여행 종료 처리
        travel_manager.complete_travel(self.travel_id)
        db_manager.set_user_traveling(self.user_discord_id, False)

        # 원래 국가 기반 역할 복원
        role_restored = False
        try:
            from config import config
            guild = interaction.guild
            if not guild:
                guild = interaction.client.get_guild(config.GUILD_ID)
            if guild and travel.get('original_nation'):
                applicant = guild.get_member(self.user_discord_id)
                if applicant:
                    from travel_scheduler import restore_travel_roles
                    await restore_travel_roles(applicant, travel, guild)
                    role_restored = True
        except Exception as e:
            print(f"[TRAVEL] 역할 복원 오류: {e}")

        # 임베드 업데이트
        if interaction.message:
            updated_embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if updated_embed:
                updated_embed.color = 0x808080
                updated_embed.title = "✈️ 여행 신청 - 종료됨"
                end_text = f"관리자 {interaction.user.mention}에 의해 종료됨"
                if role_restored:
                    end_text += f"\n🏷️ 원래 국가({travel.get('original_nation', '?')}) 기반 역할 복원됨"
                updated_embed.add_field(name="종료 처리", value=end_text, inline=False)
                await interaction.message.edit(embed=updated_embed, view=None)

        # 신청자에게 DM 전송
        try:
            from config import config
            guild = interaction.guild or interaction.client.get_guild(config.GUILD_ID)
            if guild:
                applicant = guild.get_member(self.user_discord_id)
                if applicant:
                    dm_embed = discord.Embed(
                        title="🏁 여행이 종료되었습니다",
                        description=f"관리자에 의해 여행이 종료되었습니다.\n이제부터 역할/닉네임 변동이 정상적으로 적용됩니다.",
                        color=0x808080
                    )
                    dm_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                    dm_embed.add_field(name="처리자", value=interaction.user.display_name, inline=True)
                    await applicant.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        # 로그 채널에 종료 기록
        log_channel_id = travel_config_manager.get_log_channel()
        if log_channel_id:
            guild = interaction.guild
            if not guild:
                from config import config
                guild = interaction.client.get_guild(config.GUILD_ID)
            if guild:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="📋 여행 종료 (미복귀 → 관리자 종료)",
                        color=0x808080
                    )
                    log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                    log_embed.add_field(name="대상자", value=f"<@{self.user_discord_id}>", inline=True)
                    log_embed.add_field(name="마크 닉네임", value=travel.get('minecraft_name', '?'), inline=True)
                    log_embed.add_field(name="목적지", value=travel.get('destination_nation', '?'), inline=True)
                    log_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=True)
                    log_embed.add_field(name="처리자", value=interaction.user.mention, inline=True)
                    if role_restored:
                        log_embed.add_field(name="역할 복원", value=f"원래 국가: {travel.get('original_nation', '?')}", inline=False)
                    log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    await log_channel.send(embed=log_embed)

        await interaction.response.send_message("✅ 여행이 종료되었습니다.", ephemeral=True)

    async def extend_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_config_manager

        # 권한 확인
        if not travel_config_manager.is_manager(interaction.user):
            await interaction.response.send_message("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
            return

        modal = TravelExtendModal(self.travel_id, self.user_discord_id)
        await interaction.response.send_modal(modal)

    async def settle_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager

        # 권한 확인
        if not travel_config_manager.is_manager(interaction.user):
            await interaction.response.send_message("❌ 여행 관리 권한이 없습니다.", ephemeral=True)
            return

        travel = travel_manager.get_travel(self.travel_id)
        if not travel:
            await interaction.response.send_message("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
            return

        # 정착 처리: 여행 완료 + 여행 상태 해제 + 역할을 목적지 국가 기준으로 설정
        travel_manager.complete_travel(self.travel_id)
        db_manager.set_user_traveling(self.user_discord_id, False)

        try:
            from config import config
            guild = interaction.guild
            if not guild:
                guild = interaction.client.get_guild(config.GUILD_ID)

            destination = travel.get('destination_nation', '')
            role_change_msg = ""

            if guild:
                applicant = guild.get_member(self.user_discord_id)
                if applicant:
                    # 목적지 국가 기반으로 역할 설정 (정착이므로 목적지가 새 소속)
                    success_role_id = config.SUCCESS_ROLE_ID
                    success_role_out_id = config.SUCCESS_ROLE_ID_OUT
                    base_nation = config.BASE_NATION
                    base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)

                    if success_role_id:
                        # 목적지가 base nation인지 확인
                        is_base = False
                        if base_nation_uuid:
                            try:
                                from bulk_updater import bulk_data_manager
                                nation_info = bulk_data_manager.get_nation_by_name(destination)
                                if nation_info and nation_info.get('uuid') == base_nation_uuid:
                                    is_base = True
                                elif base_nation and destination.lower() == base_nation.lower():
                                    is_base = True
                            except Exception:
                                if base_nation and destination.lower() == base_nation.lower():
                                    is_base = True
                        else:
                            if base_nation and destination.lower() == base_nation.lower():
                                is_base = True

                        if is_base:
                            # 정착지가 base nation → 조직원
                            success_role = guild.get_role(success_role_id)
                            if success_role and success_role not in applicant.roles:
                                await applicant.add_roles(success_role)
                            if success_role_out_id:
                                out_role = guild.get_role(success_role_out_id)
                                if out_role and out_role in applicant.roles:
                                    await applicant.remove_roles(out_role)
                            role_change_msg = "→ 국민(조직원) 역할 적용"
                        else:
                            # 정착지가 외국 → 외국인
                            if success_role_out_id:
                                out_role = guild.get_role(success_role_out_id)
                                if out_role and out_role not in applicant.roles:
                                    await applicant.add_roles(out_role)
                            success_role = guild.get_role(success_role_id)
                            if success_role and success_role in applicant.roles:
                                await applicant.remove_roles(success_role)
                            role_change_msg = "→ 외국인 역할 적용"

            # 임베드 업데이트
            if interaction.message:
                updated_embed = interaction.message.embeds[0] if interaction.message.embeds else None
                if updated_embed:
                    updated_embed.color = 0x808080
                    updated_embed.title = "⏳ 여행 미복귀 - 정착 처리됨"
                    updated_embed.add_field(
                        name="정착 처리",
                        value=f"관리자 {interaction.user.mention}에 의해 정착 처리됨\n"
                              f"정착 국가: **{destination}** {role_change_msg}",
                        inline=False
                    )
                    await interaction.message.edit(embed=updated_embed, view=None)

            # 신청자에게 DM 전송
            try:
                if guild:
                    applicant = guild.get_member(self.user_discord_id)
                    if applicant:
                        dm_embed = discord.Embed(
                            title="🏠 정착 처리되었습니다",
                            description=f"**{destination}**에 정착 처리되었습니다.\n"
                                       f"이제부터 역할/닉네임 변동이 정상적으로 적용됩니다.",
                            color=0x808080
                        )
                        dm_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        dm_embed.add_field(name="정착 국가", value=destination, inline=True)
                        await applicant.send(embed=dm_embed)
            except discord.Forbidden:
                pass

            # 로그 채널에 기록
            log_channel_id = travel_config_manager.get_log_channel()
            if log_channel_id and guild:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="📋 정착 처리",
                        color=0x808080
                    )
                    log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                    log_embed.add_field(name="대상자", value=f"<@{self.user_discord_id}>", inline=True)
                    log_embed.add_field(name="마크 닉네임", value=travel.get('minecraft_name', '?'), inline=True)
                    log_embed.add_field(name="정착 국가", value=destination, inline=True)
                    log_embed.add_field(name="처리자", value=interaction.user.mention, inline=True)
                    if role_change_msg:
                        log_embed.add_field(name="역할 변경", value=role_change_msg, inline=True)
                    log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    await log_channel.send(embed=log_embed)

            await interaction.response.send_message(
                f"✅ <@{self.user_discord_id}>님이 **{destination}**에 정착 처리되었습니다. {role_change_msg}",
                ephemeral=True
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)
            except:
                pass


class TravelUserControlView(ui.View):
    """유저용 여행 취소/종료 버튼 뷰 (DM에서 사용, 영구 View)"""

    def __init__(self, travel_id: str, user_discord_id: int, show_invite: bool = False):
        super().__init__(timeout=None)
        self.travel_id = travel_id
        self.user_discord_id = user_discord_id

        # 외국인 국내 여행 시 초대 요청 버튼 추가
        if show_invite:
            invite_btn = ui.Button(
                label="초대 요청",
                style=discord.ButtonStyle.primary,
                emoji="📨",
                custom_id=f"travel_invite_{travel_id}"
            )
            invite_btn.callback = self.invite_callback
            self.add_item(invite_btn)

        # 동적 custom_id로 버튼 추가 (봇 재시작 후에도 유지)
        cancel_btn = ui.Button(
            label="여행 취소",
            style=discord.ButtonStyle.danger,
            emoji="🚫",
            custom_id=f"travel_user_cancel_{travel_id}"
        )
        cancel_btn.callback = self.cancel_callback
        self.add_item(cancel_btn)

        end_btn = ui.Button(
            label="여행 종료",
            style=discord.ButtonStyle.secondary,
            emoji="🏁",
            custom_id=f"travel_user_end_{travel_id}"
        )
        end_btn.callback = self.end_callback
        self.add_item(end_btn)

    async def cancel_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager

        # 본인 확인
        if interaction.user.id != self.user_discord_id:
            await interaction.response.send_message("❌ 본인의 여행만 취소할 수 있습니다.", ephemeral=True)
            return

        travel = travel_manager.get_travel(self.travel_id)
        if not travel:
            await interaction.response.send_message("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
            return

        if travel["status"] not in ["approved", "active", "pending"]:
            await interaction.response.send_message("❌ 이미 종료되었거나 취소된 여행입니다.", ephemeral=True)
            return

        # 시작일 2일 이하일 때만 취소 가능 확인
        try:
            start_date = datetime.strptime(travel["start_date"], "%Y.%m.%d").date()
            days_until_start = (start_date - date.today()).days

            if days_until_start > 2:
                await interaction.response.send_message(
                    f"❌ 여행 취소는 시작일 2일 전부터 가능합니다.\n"
                    f"현재 시작일까지 **{days_until_start}일** 남았습니다.\n"
                    f"시작일: {travel['start_date']}",
                    ephemeral=True
                )
                return
        except Exception as e:
            print(f"날짜 파싱 오류: {e}")

        # 여행 취소 처리
        success = travel_manager.cancel_travel(self.travel_id)
        if success:
            db_manager.set_user_traveling(self.user_discord_id, False)

            # 메시지 업데이트
            updated_embed = discord.Embed(
                title="🚫 여행이 취소되었습니다",
                description="본인에 의해 여행이 취소되었습니다.",
                color=0xff0000
            )
            updated_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
            updated_embed.add_field(name="취소 시간", value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), inline=True)

            await interaction.message.edit(embed=updated_embed, view=None)

            # 로그 채널에 취소 기록
            try:
                from config import config
                bot = interaction.client
                guild = bot.get_guild(config.GUILD_ID) if config.GUILD_ID else None
                log_channel_id = travel_config_manager.get_log_channel()
                if guild and log_channel_id:
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="📋 여행 취소 (본인)",
                            color=0xff0000
                        )
                        log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        log_embed.add_field(name="여행자", value=f"<@{self.user_discord_id}>", inline=True)
                        log_embed.add_field(name="마크 닉네임", value=travel.get('minecraft_name', '?'), inline=True)
                        log_embed.add_field(name="목적지", value=travel.get('destination_nation', '?'), inline=True)
                        log_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=True)
                        log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"[TRAVEL] 취소 로그 전송 오류: {e}")

            await interaction.response.send_message("✅ 여행이 취소되었습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 여행 취소에 실패했습니다.", ephemeral=True)

    async def end_callback(self, interaction: discord.Interaction):
        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager

        # 본인 확인
        if interaction.user.id != self.user_discord_id:
            await interaction.response.send_message("❌ 본인의 여행만 종료할 수 있습니다.", ephemeral=True)
            return

        travel = travel_manager.get_travel(self.travel_id)
        if not travel:
            await interaction.response.send_message("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
            return

        if travel["status"] not in ["approved", "active"]:
            await interaction.response.send_message("❌ 이미 종료되었거나 취소된 여행입니다.", ephemeral=True)
            return

        # 여행 종료 처리
        success = travel_manager.complete_travel(self.travel_id)
        if success:
            db_manager.set_user_traveling(self.user_discord_id, False)

            # 원래 국가 기반 역할 복원 (DM에서 실행되므로 bot에서 guild 가져옴)
            try:
                if travel.get('original_nation'):
                    from config import config
                    bot = interaction.client
                    guild = bot.get_guild(config.GUILD_ID) if config.GUILD_ID else None
                    if guild:
                        member = guild.get_member(self.user_discord_id)
                        if member:
                            from travel_scheduler import restore_travel_roles
                            await restore_travel_roles(member, travel, guild)
            except Exception as e:
                print(f"[TRAVEL] 유저 종료 시 역할 복원 오류: {e}")

            # 메시지 업데이트
            updated_embed = discord.Embed(
                title="🏁 여행이 종료되었습니다",
                description="본인에 의해 여행이 조기 종료되었습니다.\n이제부터 역할/닉네임 변동이 정상적으로 적용됩니다.",
                color=0x808080
            )
            updated_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
            updated_embed.add_field(name="종료 시간", value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), inline=True)

            await interaction.message.edit(embed=updated_embed, view=None)

            # 로그 채널에 종료 기록
            try:
                from config import config
                bot = interaction.client
                guild = bot.get_guild(config.GUILD_ID) if config.GUILD_ID else None
                log_channel_id = travel_config_manager.get_log_channel()
                if guild and log_channel_id:
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="📋 여행 조기 종료 (본인)",
                            color=0x808080
                        )
                        log_embed.add_field(name="신청 ID", value=f"`{self.travel_id}`", inline=True)
                        log_embed.add_field(name="여행자", value=f"<@{self.user_discord_id}>", inline=True)
                        log_embed.add_field(name="마크 닉네임", value=travel.get('minecraft_name', '?'), inline=True)
                        log_embed.add_field(name="목적지", value=travel.get('destination_nation', '?'), inline=True)
                        log_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=True)
                        log_embed.set_footer(text=f"처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"[TRAVEL] 종료 로그 전송 오류: {e}")

            await interaction.response.send_message("✅ 여행이 종료되었습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 여행 종료에 실패했습니다.", ephemeral=True)

    async def invite_callback(self, interaction: discord.Interaction):
        """초대 요청 버튼 클릭 시 로그 채널에 알림 전송"""
        from travel_manager import travel_manager, travel_config_manager

        # 본인 확인
        if interaction.user.id != self.user_discord_id:
            await interaction.response.send_message("❌ 본인만 사용할 수 있습니다.", ephemeral=True)
            return

        travel = travel_manager.get_travel(self.travel_id)
        if not travel:
            await interaction.response.send_message("❌ 해당 여행을 찾을 수 없습니다.", ephemeral=True)
            return

        if travel["status"] not in ["approved", "active"]:
            await interaction.response.send_message("❌ 이미 종료되었거나 취소된 여행입니다.", ephemeral=True)
            return

        # 로그 채널 확인
        log_channel_id = travel_config_manager.get_log_channel()
        if not log_channel_id:
            await interaction.response.send_message("❌ 로그 채널이 설정되지 않았습니다. 관리자에게 문의해주세요.", ephemeral=True)
            return

        try:
            from config import config
            bot = interaction.client
            guild = bot.get_guild(config.GUILD_ID) if config.GUILD_ID else None
            if not guild:
                await interaction.response.send_message("❌ 서버를 찾을 수 없습니다.", ephemeral=True)
                return

            log_channel = guild.get_channel(log_channel_id)
            if not log_channel:
                await interaction.response.send_message("❌ 로그 채널을 찾을 수 없습니다.", ephemeral=True)
                return

            minecraft_name = travel.get("minecraft_name", "알 수 없음")

            invite_embed = discord.Embed(
                title="📨 마을 초대 요청",
                description=f"<@{self.user_discord_id}>님이 마을 초대를 요청했습니다.",
                color=0x3498db
            )
            invite_embed.add_field(name="마크 닉네임", value=minecraft_name, inline=True)
            invite_embed.add_field(name="여행 ID", value=f"`{self.travel_id}`", inline=True)
            invite_embed.add_field(name="초대 명령어", value=f"`/t add {minecraft_name}`", inline=False)

            await log_channel.send(content="@here", embed=invite_embed)

            await interaction.response.send_message("✅ 초대 요청이 전송되었습니다! 관리진이 확인 후 마을에 초대해드립니다.", ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)
            except:
                pass


def setup(bot):
    """봇에 /여행신청 명령어 등록"""

    @bot.tree.command(name="여행신청", description="여행을 신청합니다")
    async def 여행신청(interaction: discord.Interaction):
        """여행 신청 명령어"""
        await interaction.response.defer(ephemeral=True)

        if bot_logger:
            bot_logger.log_command("여행신청", interaction.user.id, interaction.user.name, source="user_command", category=LogCategory.TRAVEL)

        try:
            from travel_manager import travel_manager, travel_config_manager
            from database_manager import db_manager
            from config import config

            # 시스템 설정 확인
            if not travel_config_manager.is_configured():
                await interaction.followup.send(
                    "❌ 여행 시스템이 설정되지 않았습니다. 관리자에게 문의해주세요.",
                    ephemeral=True
                )
                return

            if not travel_config_manager.is_enabled():
                await interaction.followup.send(
                    "❌ 여행 시스템이 비활성화되어 있습니다.",
                    ephemeral=True
                )
                return

            # 사용자 정보 조회
            user_info = db_manager.get_user_info(interaction.user.id)
            if not user_info:
                await interaction.followup.send(
                    "❌ 등록된 사용자 정보가 없습니다. 먼저 인증을 완료해주세요.",
                    ephemeral=True
                )
                return

            # 현재 활성 여행이 있는지 확인
            active_travel = travel_manager.get_active_travel(interaction.user.id)
            if active_travel:
                await interaction.followup.send(
                    f"❌ 이미 진행 중인 여행 신청이 있습니다.\n"
                    f"신청 ID: `{active_travel['id']}`\n"
                    f"상태: {active_travel['status']}\n"
                    f"기간: {active_travel['start_date']} ~ {active_travel['end_date']}",
                    ephemeral=True
                )
                return

            # 대기 중인 신청이 있는지 확인
            pending_travels = travel_manager.get_user_travels(interaction.user.id)
            for t in pending_travels:
                if t["status"] == "pending":
                    await interaction.followup.send(
                        f"❌ 대기 중인 여행 신청이 있습니다.\n"
                        f"신청 ID: `{t['id']}`\n"
                        f"기간: {t['start_date']} ~ {t['end_date']}\n"
                        f"관리진의 승인을 기다려주세요.",
                        ephemeral=True
                    )
                    return

            # 국가 정보 조회
            nation_info = db_manager.get_current_nation(interaction.user.id)
            current_nation = nation_info.get('nation_name') if nation_info else None
            current_town = nation_info.get('town_name') if nation_info else None

            # 콜사인 조회
            callsign = db_manager.get_callsign(interaction.user.id)

            # 사용자 정보 구성
            user_data = {
                'minecraft_name': user_info.get('current_minecraft_name', '알 수 없음'),
                'nation': current_nation or '알 수 없음',
                'town': current_town or '알 수 없음',
                'callsign': callsign
            }

            # BASE_NATION 국민인지 확인
            base_nation = getattr(config, 'BASE_NATION', 'Red_Mafia')
            is_base_nation_member = (current_nation and current_nation.lower() == base_nation.lower())

            # 모달 표시
            if is_base_nation_member:
                # BASE_NATION 국민: 목적지 국가 + 날짜 입력
                modal = TravelRequestModal(user_data)
            else:
                # 외국인: 날짜만 입력 (목적지는 BASE_NATION으로 고정)
                modal = TravelRequestForeignerModal(user_data, base_nation)

            # defer된 상태이므로 followup으로 안내 후 모달은 새 인터랙션에서 표시
            # 모달은 defer 후에 표시할 수 없으므로 버튼을 사용
            view = TravelStartView(user_data, is_base_nation_member, base_nation)

            embed = discord.Embed(
                title="✈️ 여행 신청",
                description="아래 버튼을 클릭하여 여행 신청서를 작성해주세요.",
                color=0x3498db
            )
            embed.add_field(name="마크 닉네임", value=user_data['minecraft_name'], inline=True)
            embed.add_field(name="현재 국가", value=user_data['nation'], inline=True)
            embed.add_field(name="현재 마을", value=user_data['town'], inline=True)

            if is_base_nation_member:
                embed.add_field(
                    name="안내",
                    value=f"**{base_nation}** 국민으로 확인되었습니다.\n여행 목적지 국가와 기간을 입력해주세요.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="안내",
                    value=f"외국인으로 확인되었습니다.\n여행 목적지는 **{base_nation}**으로 자동 설정됩니다.",
                    inline=False
                )

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)


class TravelStartView(ui.View):
    """여행 신청 시작 버튼 뷰"""

    def __init__(self, user_data: dict, is_base_nation_member: bool, base_nation: str):
        super().__init__(timeout=300)  # 5분 타임아웃
        self.user_data = user_data
        self.is_base_nation_member = is_base_nation_member
        self.base_nation = base_nation

    @ui.button(label="신청서 작성", style=discord.ButtonStyle.primary, emoji="📝")
    async def start_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.is_base_nation_member:
            modal = TravelRequestModal(self.user_data)
        else:
            modal = TravelRequestForeignerModal(self.user_data, self.base_nation)

        await interaction.response.send_modal(modal)

    @ui.button(label="취소", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content="❌ 여행 신청이 취소되었습니다.",
            embed=None,
            view=None
        )


class TravelPanelView(ui.View):
    """여행 신청 패널 뷰 (영구 View - 채널에 고정, 봇 재시작 후에도 유지)"""

    def __init__(self):
        super().__init__(timeout=None)

        apply_btn = ui.Button(
            label="여행 신청하기",
            style=discord.ButtonStyle.primary,
            emoji="✈️",
            custom_id="travel_panel_apply"
        )
        apply_btn.callback = self.apply_callback
        self.add_item(apply_btn)

    async def apply_callback(self, interaction: discord.Interaction):
        """여행 신청 버튼 클릭 시 처리"""
        try:
            from travel_manager import travel_manager, travel_config_manager
            from database_manager import db_manager
            from config import config

            # 시스템 설정 확인
            if not travel_config_manager.is_configured():
                await interaction.response.send_message(
                    "❌ 여행 시스템이 설정되지 않았습니다. 관리자에게 문의해주세요.",
                    ephemeral=True
                )
                return

            if not travel_config_manager.is_enabled():
                await interaction.response.send_message(
                    "❌ 여행 시스템이 비활성화되어 있습니다.",
                    ephemeral=True
                )
                return

            # 블랙리스트 확인
            if travel_config_manager.is_blacklisted(interaction.user.id):
                bl_info = travel_config_manager.get_blacklist_info(interaction.user.id)
                reason_text = f"\n사유: {bl_info['reason']}" if bl_info and bl_info.get('reason') else ""
                await interaction.response.send_message(
                    f"❌ 여행 블랙리스트에 등록되어 여행 신청이 불가능합니다.{reason_text}",
                    ephemeral=True
                )
                return

            # 사용자 정보 조회
            user_info = db_manager.get_user_info(interaction.user.id)
            if not user_info:
                await interaction.response.send_message(
                    "❌ 등록된 사용자 정보가 없습니다. 먼저 인증을 완료해주세요.",
                    ephemeral=True
                )
                return

            # 현재 활성 여행이 있는지 확인
            active_travel = travel_manager.get_active_travel(interaction.user.id)
            if active_travel:
                await interaction.response.send_message(
                    f"❌ 이미 진행 중인 여행 신청이 있습니다.\n"
                    f"신청 ID: `{active_travel['id']}`\n"
                    f"상태: {active_travel['status']}\n"
                    f"기간: {active_travel['start_date']} ~ {active_travel['end_date']}",
                    ephemeral=True
                )
                return

            # 대기 중인 신청이 있는지 확인
            pending_travels = travel_manager.get_user_travels(interaction.user.id)
            for t in pending_travels:
                if t["status"] == "pending":
                    await interaction.response.send_message(
                        f"❌ 대기 중인 여행 신청이 있습니다.\n"
                        f"신청 ID: `{t['id']}`\n"
                        f"기간: {t['start_date']} ~ {t['end_date']}\n"
                        f"관리진의 승인을 기다려주세요.",
                        ephemeral=True
                    )
                    return

            # 국가 정보 조회
            nation_info = db_manager.get_current_nation(interaction.user.id)
            current_nation = nation_info.get('nation_name') if nation_info else None
            current_town = nation_info.get('town_name') if nation_info else None

            # 콜사인 조회
            callsign = db_manager.get_callsign(interaction.user.id)

            # 사용자 정보 구성
            user_data = {
                'minecraft_name': user_info.get('current_minecraft_name', '알 수 없음'),
                'nation': current_nation or '알 수 없음',
                'town': current_town or '알 수 없음',
                'callsign': callsign
            }

            # BASE_NATION 국민인지 확인
            base_nation = getattr(config, 'BASE_NATION', 'Red_Mafia')
            is_base_nation_member = (current_nation and current_nation.lower() == base_nation.lower())

            # 모달 바로 표시 (패널에서는 defer 없이 바로 모달)
            if is_base_nation_member:
                modal = TravelRequestModal(user_data)
            else:
                modal = TravelRequestForeignerModal(user_data, base_nation)

            await interaction.response.send_modal(modal)

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)
            except:
                pass
