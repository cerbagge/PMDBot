# commands/admin/travel/travel_manage.py
# /여행관리 명령어 - 여행 시스템 설정 및 관리

import discord
from discord import app_commands, ui
from typing import Literal
from datetime import datetime, date
import re

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


class AdminTravelAddModal(ui.Modal, title="여행 추가"):
    """관리자용 여행 추가 모달"""

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

    original_nation = ui.TextInput(
        label="원래 소속 국가 (선택사항)",
        placeholder="유저의 원래 국가 → 국민이면 조직원, 아니면 외국인 역할 자동 처리",
        required=False,
        max_length=100
    )

    def __init__(self, target_user: discord.Member, user_info: dict, admin: discord.Member):
        super().__init__()
        self.target_user = target_user
        self.user_info = user_info
        self.admin = admin

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

            # 여행 일수 계산
            travel_days = (end - start).days + 1

            orig_nation = self.original_nation.value.strip() if self.original_nation.value else None

            # 여행 신청 생성
            travel_id = travel_manager.create_travel_request(
                discord_id=self.target_user.id,
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
                    "❌ 여행 추가에 실패했습니다.",
                    ephemeral=True
                )
                return

            # 관리자가 추가한 것이므로 바로 승인 처리
            travel_manager.approve_travel(travel_id, self.admin.id, "관리자 직접 추가")

            # 원래 국가 정보 저장
            if orig_nation:
                travel_manager.set_original_nation(travel_id, orig_nation)

            # 시작일이 오늘이거나 이전이면 바로 활성화
            today = date.today()
            if start <= today:
                travel_manager.activate_travel(travel_id)
                db_manager.set_user_traveling(self.target_user.id, True)

            # 원래 국가 기반 역할 처리
            role_change_msg = ""
            if orig_nation and interaction.guild:
                is_base = await self._apply_travel_roles(self.target_user, orig_nation, interaction.guild)
                role_type = "국민(조직원)" if is_base else "외국인"
                role_change_msg = f"\n🏷️ 원래 국가: **{orig_nation}** → **{role_type}** 역할 적용됨"

            # 여행 신청 채널에 승인 메시지 전송 (유저 신청 승인과 동일한 형태)
            request_channel_id = travel_config_manager.get_request_channel()
            if request_channel_id and interaction.guild:
                request_channel = interaction.guild.get_channel(request_channel_id)
                if request_channel:
                    try:
                        from commands.user.travel.travel_request import TravelAdminControlView

                        admin_embed = discord.Embed(
                            title="✈️ 여행 신청 - 승인됨",
                            description=f"{self.target_user.mention}님이 여행을 신청했습니다.",
                            color=0x00ff00
                        )
                        admin_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                        admin_embed.add_field(name="신청자", value=self.target_user.mention, inline=True)
                        admin_embed.add_field(name="마크 닉네임", value=self.user_info.get('minecraft_name', '알 수 없음'), inline=True)
                        admin_embed.add_field(name="콜사인", value=self.user_info.get('callsign') or '없음', inline=True)
                        admin_embed.add_field(name="현재 국가", value=self.user_info.get('nation', '알 수 없음'), inline=True)
                        admin_embed.add_field(name="현재 마을", value=self.user_info.get('town', '알 수 없음'), inline=True)
                        admin_embed.add_field(name="목적지 국가", value=self.destination.value.strip(), inline=True)
                        admin_embed.add_field(name="여행 기간", value=f"{self.start_date.value} ~ {self.end_date.value}", inline=True)
                        admin_embed.add_field(name="여행 일수", value=f"{travel_days}일", inline=True)
                        admin_embed.add_field(name="처리 결과", value=f"**승인됨** by {self.admin.mention}", inline=False)
                        admin_embed.set_thumbnail(url=self.target_user.display_avatar.url)
                        admin_embed.set_footer(text=f"신청 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                        # 관리 역할 멘션
                        manager_roles = travel_config_manager.get_manager_roles()
                        role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                        # 취소/종료 버튼
                        admin_view = TravelAdminControlView(travel_id, self.target_user.id)
                        msg = await request_channel.send(
                            content=role_mentions if role_mentions else None,
                            embed=admin_embed,
                            view=admin_view
                        )

                        # 메시지 ID 저장
                        travel_manager.update_message_id(travel_id, msg.id)
                    except Exception as e:
                        print(f"[TRAVEL] 신청 채널 메시지 전송 실패: {e}")

            # 대상 유저에게 DM 전송
            try:
                dm_embed = discord.Embed(
                    title="✈️ 여행이 등록되었습니다",
                    description=f"관리자에 의해 여행이 등록되었습니다.",
                    color=0x00ff00
                )
                dm_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                dm_embed.add_field(name="목적지", value=self.destination.value.strip(), inline=True)
                dm_embed.add_field(name="기간", value=f"{self.start_date.value} ~ {self.end_date.value} ({travel_days}일)", inline=False)
                dm_embed.add_field(name="등록자", value=self.admin.display_name, inline=True)
                dm_embed.set_footer(text="여행 기간 동안 역할/닉네임 변동이 유예됩니다.")

                await self.target_user.send(embed=dm_embed)
            except discord.Forbidden:
                pass

            # 로그 채널에 기록
            log_channel_id = travel_config_manager.get_log_channel()
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="📋 여행 직접 추가",
                        color=0x00ff00
                    )
                    log_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                    log_embed.add_field(name="대상자", value=self.target_user.mention, inline=True)
                    log_embed.add_field(name="마크 닉네임", value=self.user_info.get('minecraft_name', '?'), inline=True)
                    log_embed.add_field(name="목적지", value=self.destination.value.strip(), inline=True)
                    log_embed.add_field(name="기간", value=f"{self.start_date.value} ~ {self.end_date.value}", inline=True)
                    log_embed.add_field(name="등록자", value=self.admin.mention, inline=True)
                    if orig_nation:
                        log_embed.add_field(name="원래 국가", value=orig_nation, inline=True)
                    log_embed.set_footer(text=f"등록 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                    await log_channel.send(embed=log_embed)

            # 성공 메시지
            embed = discord.Embed(
                title="✅ 여행 추가 완료",
                description=f"{self.target_user.mention}의 여행이 등록되었습니다.{role_change_msg}",
                color=0x00ff00
            )
            embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
            embed.add_field(name="마크 닉네임", value=self.user_info.get('minecraft_name', '?'), inline=True)
            embed.add_field(name="목적지", value=self.destination.value.strip(), inline=True)
            embed.add_field(name="기간", value=f"{self.start_date.value} ~ {self.end_date.value} ({travel_days}일)", inline=False)

            status_text = "여행중" if start <= today else "승인됨 (대기중)"
            embed.add_field(name="상태", value=status_text, inline=True)
            if orig_nation:
                embed.add_field(name="원래 국가", value=orig_nation, inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)


def setup(bot):
    """봇에 /여행관리 명령어 등록"""

    @bot.tree.command(name="여행관리", description="여행 시스템을 설정하고 관리합니다")
    @app_commands.describe(
        기능="설정할 기능을 선택하세요",
        채널="채널 (채널/로그_채널 설정 시)",
        역할="역할 (역할 설정/제거 시)",
        유저="유저 (여행추가/여행종료/블랙추가/블랙제거 시)",
        id="여행 ID (여행종료 기능 사용 시, 예: T000001)",
        사유="사유 (블랙추가 시)"
    )
    @app_commands.choices(기능=[
        app_commands.Choice(name="여행추가", value="여행추가"),
        app_commands.Choice(name="여행종료", value="여행종료"),
        app_commands.Choice(name="여행리스트", value="여행리스트"),
        app_commands.Choice(name="여행로그", value="여행로그"),
        app_commands.Choice(name="여행신청패널", value="여행신청패널"),
        app_commands.Choice(name="채널", value="채널"),
        app_commands.Choice(name="로그_채널", value="로그_채널"),
        app_commands.Choice(name="역할", value="역할"),
        app_commands.Choice(name="역할목록", value="역할목록"),
        app_commands.Choice(name="역할제거", value="역할제거"),
        app_commands.Choice(name="현황", value="현황"),
        app_commands.Choice(name="대기목록", value="대기목록"),
        app_commands.Choice(name="활성목록", value="활성목록"),
        app_commands.Choice(name="블랙추가", value="블랙추가"),
        app_commands.Choice(name="블랙제거", value="블랙제거"),
        app_commands.Choice(name="블랙목록", value="블랙목록"),
    ])
    @app_commands.check(is_admin)
    async def 여행관리(
        interaction: discord.Interaction,
        기능: app_commands.Choice[str],
        채널: discord.TextChannel = None,
        역할: discord.Role = None,
        유저: discord.Member = None,
        id: str = None,
        사유: str = None
    ):
        """여행 시스템 관리"""
        if bot_logger:
            bot_logger.log_command("여행관리", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.TRAVEL,
                                   details={"기능": 기능.value})

        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager

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

        # 여행추가 기능은 모달을 사용하므로 defer 없이 처리
        if 기능.value == "여행추가":
            # 관리자가 직접 유저의 여행을 추가
            if not 유저:
                await interaction.response.send_message("❌ 유저를 지정해주세요.", ephemeral=True)
                return

            # 대상 유저 정보 조회
            user_info = db_manager.get_user_info(유저.id)
            if not user_info:
                await interaction.response.send_message(
                    f"❌ {유저.mention}의 등록된 정보가 없습니다.",
                    ephemeral=True
                )
                return

            # 블랙리스트 확인
            if travel_config_manager.is_blacklisted(유저.id):
                bl_info = travel_config_manager.get_blacklist_info(유저.id)
                reason_text = f"\n사유: {bl_info['reason']}" if bl_info and bl_info.get('reason') else ""
                await interaction.response.send_message(
                    f"❌ {유저.mention}은(는) 여행 블랙리스트에 등록되어 있습니다.{reason_text}",
                    ephemeral=True
                )
                return

            # 현재 활성 여행이 있는지 확인
            active_travel = travel_manager.get_active_travel(유저.id)
            if active_travel:
                await interaction.response.send_message(
                    f"❌ {유저.mention}은(는) 이미 진행 중인 여행이 있습니다.\n"
                    f"신청 ID: `{active_travel['id']}`\n"
                    f"상태: {active_travel['status']}\n"
                    f"기간: {active_travel['start_date']} ~ {active_travel['end_date']}",
                    ephemeral=True
                )
                return

            # 국가 정보 조회
            nation_info = db_manager.get_current_nation(유저.id)
            current_nation = nation_info.get('nation_name') if nation_info else None
            current_town = nation_info.get('town_name') if nation_info else None

            # 콜사인 조회
            callsign = db_manager.get_callsign(유저.id)

            # 사용자 정보 구성
            user_data = {
                'minecraft_name': user_info.get('current_minecraft_name', '알 수 없음'),
                'nation': current_nation or '알 수 없음',
                'town': current_town or '알 수 없음',
                'callsign': callsign
            }

            # 모달 표시
            modal = AdminTravelAddModal(유저, user_data, interaction.user)
            await interaction.response.send_modal(modal)
            return

        # 여행종료 기능
        if 기능.value == "여행종료":
            # 유저 또는 ID 중 하나는 필수
            if not 유저 and not id:
                await interaction.response.send_message(
                    "❌ 유저 또는 여행 ID를 지정해주세요.\n"
                    "사용법:\n"
                    "- `/여행관리 기능:여행종료 유저:@멤버`\n"
                    "- `/여행관리 기능:여행종료 id:T000001`",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            try:
                from travel_manager import travel_manager, travel_config_manager
                from database_manager import db_manager

                # ID로 여행 조회
                if id:
                    travel_id = id.strip().upper()
                    active_travel = travel_manager.get_travel(travel_id)
                    if not active_travel:
                        await interaction.followup.send(
                            f"❌ 여행 ID `{travel_id}`를 찾을 수 없습니다.",
                            ephemeral=True
                        )
                        return

                    # 이미 종료된 여행인지 확인
                    if active_travel['status'] not in ['approved', 'active']:
                        await interaction.followup.send(
                            f"❌ 여행 ID `{travel_id}`는 이미 종료되었거나 활성 상태가 아닙니다.\n"
                            f"현재 상태: `{active_travel['status']}`",
                            ephemeral=True
                        )
                        return

                    discord_id = active_travel['discord_id']
                else:
                    # 유저로 여행 조회
                    active_travel = travel_manager.get_active_travel(유저.id)
                    if not active_travel:
                        await interaction.followup.send(
                            f"❌ {유저.mention}은(는) 진행 중인 여행이 없습니다.",
                            ephemeral=True
                        )
                        return

                    travel_id = active_travel['id']
                    discord_id = 유저.id

                # 여행 완료 처리
                success = travel_manager.complete_travel(travel_id)
                if not success:
                    await interaction.followup.send("❌ 여행 종료 처리에 실패했습니다.", ephemeral=True)
                    return

                # 여행 상태 해제
                db_manager.set_user_traveling(discord_id, False)

                # 대상 유저 찾기
                target_user = 유저 if 유저 else interaction.guild.get_member(discord_id)

                # 원래 국가 기반 역할 복원
                if target_user and active_travel.get('original_nation') and interaction.guild:
                    try:
                        from travel_scheduler import restore_travel_roles
                        await restore_travel_roles(target_user, active_travel, interaction.guild)
                    except Exception as e:
                        print(f"[TRAVEL] 역할 복원 오류: {e}")

                # 대상 유저에게 DM 전송
                if target_user:
                    try:
                        dm_embed = discord.Embed(
                            title="✈️ 여행이 종료되었습니다",
                            description=f"관리자에 의해 여행이 조기 종료되었습니다.",
                            color=0xff9900
                        )
                        dm_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                        dm_embed.add_field(name="목적지", value=active_travel['destination_nation'], inline=True)
                        dm_embed.add_field(name="원래 기간", value=f"{active_travel['start_date']} ~ {active_travel['end_date']}", inline=False)
                        dm_embed.add_field(name="종료 처리자", value=interaction.user.display_name, inline=True)
                        dm_embed.set_footer(text="여행 유예 상태가 해제되었습니다.")

                        await target_user.send(embed=dm_embed)
                    except discord.Forbidden:
                        pass

                # 로그 채널에 기록
                log_channel_id = travel_config_manager.get_log_channel()
                if log_channel_id:
                    log_channel = interaction.guild.get_channel(log_channel_id)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="📋 여행 조기 종료",
                            color=0xff9900
                        )
                        log_embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                        log_embed.add_field(name="대상자", value=target_user.mention if target_user else f"`{discord_id}`", inline=True)
                        log_embed.add_field(name="마크 닉네임", value=active_travel.get('minecraft_name', '?'), inline=True)
                        log_embed.add_field(name="목적지", value=active_travel['destination_nation'], inline=True)
                        log_embed.add_field(name="원래 기간", value=f"{active_travel['start_date']} ~ {active_travel['end_date']}", inline=True)
                        log_embed.add_field(name="종료 처리자", value=interaction.user.mention, inline=True)
                        log_embed.set_footer(text=f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                        await log_channel.send(embed=log_embed)

                # 성공 메시지
                embed = discord.Embed(
                    title="✅ 여행 종료 완료",
                    description=f"여행 `{travel_id}`가 종료되었습니다.",
                    color=0x00ff00
                )
                embed.add_field(name="신청 ID", value=f"`{travel_id}`", inline=True)
                embed.add_field(name="대상자", value=target_user.mention if target_user else f"`{discord_id}`", inline=True)
                embed.add_field(name="마크 닉네임", value=active_travel.get('minecraft_name', '?'), inline=True)
                embed.add_field(name="목적지", value=active_travel['destination_nation'], inline=True)
                embed.add_field(name="원래 기간", value=f"{active_travel['start_date']} ~ {active_travel['end_date']}", inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                import traceback
                traceback.print_exc()
                await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)

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

            elif 기능.value == "대기목록":
                # 대기 중인 신청 목록
                pending = travel_manager.get_pending_travels()

                if not pending:
                    await interaction.followup.send("📋 대기 중인 여행 신청이 없습니다.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"📋 대기 중인 여행 신청 ({len(pending)}건)",
                    color=0xf39c12
                )

                for travel in pending[:10]:  # 최대 10개만 표시
                    travel_days = travel_manager.calculate_travel_days(travel)
                    embed.add_field(
                        name=f"`{travel['id']}` - {travel['minecraft_name']}",
                        value=f"• 신청자: <@{travel['discord_id']}>\n"
                              f"• 현재 국가: {travel['current_nation']}\n"
                              f"• 목적지: {travel['destination_nation']}\n"
                              f"• 기간: {travel['start_date']} ~ {travel['end_date']} ({travel_days}일)\n"
                              f"• 신청일: {travel['created_at'][:10]}",
                        inline=False
                    )

                if len(pending) > 10:
                    embed.set_footer(text=f"총 {len(pending)}건 중 10건만 표시됩니다.")

                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "활성목록":
                # 활성 여행 목록
                active = travel_manager.get_active_travels()

                if not active:
                    await interaction.followup.send("🛫 진행 중인 여행이 없습니다.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"🛫 진행 중인 여행 ({len(active)}건)",
                    color=0x00ff00
                )

                for travel in active[:10]:
                    travel_days = travel_manager.calculate_travel_days(travel)
                    embed.add_field(
                        name=f"`{travel['id']}` - {travel['minecraft_name']}",
                        value=f"• 여행자: <@{travel['discord_id']}>\n"
                              f"• 현재 국가: {travel['current_nation']}\n"
                              f"• 목적지: {travel['destination_nation']}\n"
                              f"• 기간: {travel['start_date']} ~ {travel['end_date']} ({travel_days}일)\n"
                              f"• 상태: {travel['status']}",
                        inline=False
                    )

                if len(active) > 10:
                    embed.set_footer(text=f"총 {len(active)}건 중 10건만 표시됩니다.")

                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "여행리스트":
                # 현재 여행중인 목록만 (active 상태)
                active_travels = travel_manager.get_active_travels()

                if not active_travels:
                    await interaction.followup.send("✈️ 현재 여행중인 사람이 없습니다.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"✈️ 현재 여행중 ({len(active_travels)}명)",
                    color=0x00ff00
                )

                for travel in active_travels[:20]:
                    travel_days = travel_manager.calculate_travel_days(travel)
                    # 남은 일수 계산
                    try:
                        end_date = datetime.strptime(travel['end_date'], "%Y.%m.%d").date()
                        today = date.today()
                        remaining = (end_date - today).days
                        remaining_text = f"(D-{remaining})" if remaining > 0 else "(오늘 종료)" if remaining == 0 else "(기간 초과)"
                    except:
                        remaining_text = ""

                    embed.add_field(
                        name=f"✈️ `{travel['id']}` - {travel['minecraft_name']} {remaining_text}",
                        value=f"• 여행자: <@{travel['discord_id']}>\n"
                              f"• 목적지: {travel['destination_nation']}\n"
                              f"• 기간: {travel['start_date']} ~ {travel['end_date']} ({travel_days}일)",
                        inline=False
                    )

                if len(active_travels) > 20:
                    embed.set_footer(text=f"총 {len(active_travels)}명 중 20명만 표시됩니다.")
                else:
                    embed.set_footer(text="여행 종료: /여행관리 기능:여행종료 id:T000001")

                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "여행로그":
                # 전체 여행 기록 (최근 20개)
                all_travels = travel_manager.get_all_travels(limit=20)

                if not all_travels:
                    await interaction.followup.send("📋 등록된 여행 기록이 없습니다.", ephemeral=True)
                    return

                # 상태별 이모지
                status_emoji = {
                    'pending': '⏳',
                    'approved': '✅',
                    'active': '✈️',
                    'completed': '🏁',
                    'rejected': '❌',
                    'cancelled': '🚫'
                }

                status_text = {
                    'pending': '대기중',
                    'approved': '승인됨',
                    'active': '여행중',
                    'completed': '완료',
                    'rejected': '기각됨',
                    'cancelled': '취소됨'
                }

                embed = discord.Embed(
                    title=f"📋 여행 로그 (최근 {len(all_travels)}건)",
                    color=0x3498db
                )

                for travel in all_travels:
                    status = travel.get('status', 'pending')
                    emoji = status_emoji.get(status, '❓')
                    status_display = status_text.get(status, status)
                    travel_days = travel_manager.calculate_travel_days(travel)

                    embed.add_field(
                        name=f"{emoji} `{travel['id']}` - {travel['minecraft_name']}",
                        value=f"• 상태: **{status_display}**\n"
                              f"• 여행자: <@{travel['discord_id']}>\n"
                              f"• 목적지: {travel['destination_nation']}\n"
                              f"• 기간: {travel['start_date']} ~ {travel['end_date']} ({travel_days}일)",
                        inline=False
                    )

                embed.set_footer(text="여행 종료: /여행관리 기능:여행종료 id:T000001")
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능.value == "블랙추가":
                if not 유저:
                    await interaction.followup.send("❌ 블랙리스트에 추가할 유저를 지정해주세요.", ephemeral=True)
                    return

                if travel_config_manager.is_blacklisted(유저.id):
                    await interaction.followup.send(
                        f"⚠️ {유저.mention}은(는) 이미 블랙리스트에 등록되어 있습니다.",
                        ephemeral=True
                    )
                    return

                success = travel_config_manager.add_blacklist(유저.id, interaction.user.id, 사유)

                if success:
                    embed = discord.Embed(
                        title="✅ 여행 블랙리스트 추가 완료",
                        description=f"{유저.mention}이(가) 여행 블랙리스트에 추가되었습니다.",
                        color=0xff0000
                    )
                    embed.add_field(name="대상자", value=유저.mention, inline=True)
                    embed.add_field(name="등록자", value=interaction.user.mention, inline=True)
                    if 사유:
                        embed.add_field(name="사유", value=사유, inline=False)
                    embed.set_footer(text=f"등록 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 블랙리스트 추가에 실패했습니다.", ephemeral=True)

            elif 기능.value == "블랙제거":
                if not 유저:
                    await interaction.followup.send("❌ 블랙리스트에서 제거할 유저를 지정해주세요.", ephemeral=True)
                    return

                if not travel_config_manager.is_blacklisted(유저.id):
                    await interaction.followup.send(
                        f"⚠️ {유저.mention}은(는) 블랙리스트에 등록되어 있지 않습니다.",
                        ephemeral=True
                    )
                    return

                success = travel_config_manager.remove_blacklist(유저.id)

                if success:
                    embed = discord.Embed(
                        title="✅ 여행 블랙리스트 제거 완료",
                        description=f"{유저.mention}이(가) 여행 블랙리스트에서 제거되었습니다.",
                        color=0x00ff00
                    )
                    embed.add_field(name="대상자", value=유저.mention, inline=True)
                    embed.add_field(name="처리자", value=interaction.user.mention, inline=True)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 블랙리스트 제거에 실패했습니다.", ephemeral=True)

            elif 기능.value == "블랙목록":
                blacklist = travel_config_manager.get_all_blacklist()

                if not blacklist:
                    await interaction.followup.send("📋 여행 블랙리스트가 비어 있습니다.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"🚫 여행 블랙리스트 ({len(blacklist)}명)",
                    color=0xff0000
                )

                for discord_id_str, info in list(blacklist.items())[:20]:
                    reason = info.get('reason') or '사유 없음'
                    added_at = info.get('added_at', '?')[:10]
                    added_by = info.get('added_by')
                    by_text = f"<@{added_by}>" if added_by else "알 수 없음"

                    embed.add_field(
                        name=f"<@{discord_id_str}>",
                        value=f"• 사유: {reason}\n• 등록자: {by_text}\n• 등록일: {added_at}",
                        inline=False
                    )

                if len(blacklist) > 20:
                    embed.set_footer(text=f"총 {len(blacklist)}명 중 20명만 표시됩니다.")

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}", ephemeral=True)

    # 에러 핸들러
    @여행관리.error
    async def 여행관리_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자 또는 여행 관리 역할만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
