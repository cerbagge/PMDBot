# /부계관리 명령어 - 부계정 관리 (관리자 전용)
# 밴/킥/타임아웃 이벤트 발생 시 연결된 부계정에 동일 처벌 자동 적용

import discord
from discord import app_commands
from typing import Literal, Optional, Set
import datetime
import asyncio

try:
    from database_manager import db_manager
    DATABASE_ENABLED = True
except ImportError:
    db_manager = None
    DATABASE_ENABLED = False


def is_admin(interaction: discord.Interaction) -> bool:
    """관리자 권한 체크"""
    return interaction.user.guild_permissions.administrator


def _get_linked_ids(discord_id: int) -> Set[int]:
    """주어진 계정과 연결된 모든 계정 ID 집합 반환 (본인 제외)"""
    if not DATABASE_ENABLED:
        return set()
    linked = set()
    main_id = db_manager.get_main_account(discord_id)
    if main_id:
        # 부계정인 경우: 본계정 + 같은 본계정의 다른 부계정들
        linked.add(main_id)
        for alt in db_manager.get_alt_accounts(main_id):
            linked.add(alt['alt_discord_id'])
    else:
        # 본계정인 경우: 모든 부계정
        for alt in db_manager.get_alt_accounts(discord_id):
            linked.add(alt['alt_discord_id'])
    linked.discard(discord_id)
    return linked


class AltRemoveConfirmView(discord.ui.View):
    """부계정 제거 확인 버튼 뷰"""

    def __init__(self, 부계정: discord.Member, executor_name: str):
        super().__init__(timeout=60.0)
        self.부계정 = 부계정
        self.executor_name = executor_name
        self.message = None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        title="⏱️ 시간 초과",
                        description="60초 내에 응답하지 않아 취소되었습니다.",
                        color=discord.Color.orange()
                    ),
                    view=None
                )
            except Exception:
                pass

    @discord.ui.button(label="예 (킥)", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True

        # DB 연결 해제
        success, message = db_manager.remove_alt_account(self.부계정.id)
        if not success:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ 해제 실패",
                    description=message,
                    color=discord.Color.red()
                ),
                view=None
            )
            self.stop()
            return

        # 역할 제거
        role_removed = False
        role_error = None
        removable_roles = [r for r in self.부계정.roles if r.name != "@everyone"]
        if removable_roles:
            try:
                await self.부계정.remove_roles(
                    *removable_roles,
                    reason=f"부계관리: 부계정 연결 해제 by {self.executor_name}"
                )
                role_removed = True
            except discord.Forbidden:
                role_error = "역할 제거 권한 없음"
            except Exception as e:
                role_error = f"역할 제거 오류: {e}"

        # 킥
        kicked = False
        kick_error = None
        try:
            await self.부계정.kick(
                reason=f"부계관리: 부계정 연결 해제 by {self.executor_name}"
            )
            kicked = True
        except discord.Forbidden:
            kick_error = "킥 권한 없음"
        except Exception as e:
            kick_error = f"킥 오류: {e}"

        embed = discord.Embed(title="✅ 부계정 연결 해제", color=discord.Color.green())
        embed.add_field(name="해제된 부계정", value=self.부계정.mention, inline=True)
        embed.add_field(
            name="역할 제거",
            value="✅ 완료" if role_removed else (role_error or "역할 없음"),
            inline=True
        )
        embed.add_field(
            name="킥",
            value="✅ 완료" if kicked else kick_error,
            inline=True
        )
        embed.set_footer(text=f"처리자: {self.executor_name}")
        await interaction.edit_original_response(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="아니오 (취소)", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(
            embed=discord.Embed(
                title="❌ 취소됨",
                description="부계정 연결 해제가 취소되었습니다.",
                color=discord.Color.orange()
            ),
            view=None
        )
        self.stop()


def setup(bot):
    """봇에 /부계관리 명령어 및 처벌 동기화 이벤트 리스너 등록"""

    # ── 처벌 동기화 이벤트 리스너 ────────────────────────────────────────

    @bot.listen('on_member_ban')
    async def _alt_sync_ban(guild: discord.Guild, user: discord.User):
        """밴 발생 시 연결된 계정에도 자동 밴"""
        if not DATABASE_ENABLED:
            return
        linked_ids = _get_linked_ids(user.id)
        for uid in linked_ids:
            try:
                await guild.ban(discord.Object(id=uid), reason=f"부계정 처벌 동기화: <@{user.id}> 밴")
            except Exception:
                pass

    @bot.listen('on_member_remove')
    async def _alt_sync_kick(member: discord.Member):
        """킥 발생 시 연결된 계정에도 자동 킥 (audit log로 킥 여부 판단)"""
        if not DATABASE_ENABLED:
            return
        # 연결된 계정이 없으면 audit log 조회 자체를 하지 않음
        linked_ids = _get_linked_ids(member.id)
        if not linked_ids:
            return
        await asyncio.sleep(1)
        try:
            async for entry in member.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.kick
            ):
                if entry.target.id == member.id:
                    for uid in linked_ids:
                        target = member.guild.get_member(uid)
                        if target:
                            try:
                                await member.guild.kick(
                                    target,
                                    reason=f"부계정 처벌 동기화: <@{member.id}> 킥"
                                )
                            except Exception:
                                pass
                    break
        except Exception:
            pass

    @bot.listen('on_member_update')
    async def _alt_sync_timeout(before: discord.Member, after: discord.Member):
        """타임아웃 발생 시 연결된 계정에도 동일 타임아웃"""
        if not DATABASE_ENABLED:
            return
        if before.timed_out_until == after.timed_out_until:
            return
        if not after.timed_out_until:
            return
        linked_ids = _get_linked_ids(after.id)
        for uid in linked_ids:
            target = after.guild.get_member(uid)
            if target:
                try:
                    await target.timeout(
                        after.timed_out_until,
                        reason=f"부계정 처벌 동기화: <@{after.id}> 타임아웃"
                    )
                except Exception:
                    pass

    @bot.listen('on_member_update')
    async def _alt_sync_special_roles(before: discord.Member, after: discord.Member):
        """뉴비/복귀 역할 변경 시 연결된 계정에도 동기화"""
        if not DATABASE_ENABLED:
            return

        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)
        if not added_roles and not removed_roles:
            return

        # 동기화 대상 역할 ID 수집 (뉴비 역할 + 복귀 시스템 역할)
        sync_role_ids = set()
        try:
            from newbie_config_manager import newbie_config_manager as _ncm
            rid = _ncm.get_newbie_role()
            if rid:
                sync_role_ids.add(rid)
        except ImportError:
            pass
        try:
            from return_config_manager import return_config_manager as _rcm
            for getter in [
                _rcm.get_inactive_role,
                _rcm.get_return_role,
                _rcm.get_return_complete_role,
                _rcm.get_return_chat_role,
            ]:
                rid = getter()
                if rid:
                    sync_role_ids.add(rid)
            for rid in _rcm.get_extra_inactive_roles():
                sync_role_ids.add(rid)
        except ImportError:
            pass

        if not sync_role_ids:
            return

        added_sync = [r for r in added_roles if r.id in sync_role_ids]
        removed_sync = [r for r in removed_roles if r.id in sync_role_ids]
        if not added_sync and not removed_sync:
            return

        linked_ids = _get_linked_ids(after.id)
        if not linked_ids:
            return

        for uid in linked_ids:
            target = after.guild.get_member(uid)
            if not target:
                continue
            try:
                to_add = [r for r in added_sync if r not in target.roles]
                to_remove = [r for r in removed_sync if r in target.roles]
                if to_add:
                    await target.add_roles(*to_add, reason=f"부계정 역할 동기화: {after.display_name}")
                if to_remove:
                    await target.remove_roles(*to_remove, reason=f"부계정 역할 동기화: {after.display_name}")
            except Exception:
                pass

    # ── /부계관리 슬래시 명령어 ──────────────────────────────────────────

    @bot.tree.command(name="부계관리", description="부계정을 관리합니다 (관리자 전용)")
    @app_commands.describe(
        기능="실행할 기능 선택",
        본계정="본계정 사용자",
        부계정="부계정 사용자",
        역할="부여할 역할"
    )
    @app_commands.check(is_admin)
    async def 부계관리(
        interaction: discord.Interaction,
        기능: Literal["추가", "제거", "목록", "역할"],
        본계정: discord.Member = None,
        부계정: discord.Member = None,
        역할: discord.Role = None
    ):
        """부계정 관리 - 관리자 전용"""
        await interaction.response.defer(ephemeral=True)

        if not DATABASE_ENABLED:
            await interaction.followup.send(embed=discord.Embed(
                title="❌ 오류",
                description="데이터베이스가 비활성화되어 있습니다.",
                color=discord.Color.red()
            ))
            return

        # ── 추가 ──────────────────────────────────────────────────────────
        if 기능 == "추가":
            if not 본계정 or not 부계정:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ 오류",
                    description="`본계정`과 `부계정`을 모두 지정해야 합니다.",
                    color=discord.Color.red()
                ))
                return

            if 본계정.id == 부계정.id:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ 오류",
                    description="본계정과 부계정이 동일합니다.",
                    color=discord.Color.red()
                ))
                return

            success, message = db_manager.add_alt_account(
                main_discord_id=본계정.id,
                alt_discord_id=부계정.id,
                linked_by=interaction.user.id
            )

            if not success:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ 등록 실패",
                    description=message,
                    color=discord.Color.red()
                ))
                return

            # 본계정 역할 동기화 (@everyone 제외)
            roles_to_add = [r for r in 본계정.roles if r.name != "@everyone"]
            synced_roles = []
            sync_error = None

            if roles_to_add:
                try:
                    await 부계정.add_roles(
                        *roles_to_add,
                        reason=f"부계관리: {본계정.display_name}의 역할 동기화"
                    )
                    synced_roles = roles_to_add
                except discord.Forbidden:
                    sync_error = "봇 권한 부족으로 일부 역할을 부여하지 못했습니다."
                except Exception as e:
                    sync_error = f"역할 동기화 오류: {e}"

            # 서버에 설정된 부계정 자동 역할 부여
            auto_role_added = None
            auto_role_error = None
            configured_role_id = db_manager.get_alt_role(interaction.guild_id)
            if configured_role_id:
                configured_role = interaction.guild.get_role(configured_role_id)
                if configured_role:
                    try:
                        await 부계정.add_roles(
                            configured_role,
                            reason=f"부계관리: 부계정 자동 역할 부여 by {interaction.user.display_name}"
                        )
                        auto_role_added = configured_role
                    except discord.Forbidden:
                        auto_role_error = f"{configured_role.mention} 역할 부여 권한 없음"
                    except Exception as e:
                        auto_role_error = f"{configured_role.mention} 역할 부여 오류: {e}"

            embed = discord.Embed(title="✅ 부계정 등록 완료", color=discord.Color.green())
            embed.add_field(name="본계정", value=본계정.mention, inline=True)
            embed.add_field(name="부계정", value=부계정.mention, inline=True)

            if synced_roles:
                roles_text = " ".join(r.mention for r in synced_roles)
                embed.add_field(name="동기화된 역할", value=roles_text, inline=False)
            else:
                embed.add_field(
                    name="동기화된 역할",
                    value=sync_error if sync_error else "없음",
                    inline=False
                )

            if auto_role_added:
                embed.add_field(name="부계정 역할", value=auto_role_added.mention, inline=False)
            elif auto_role_error:
                embed.add_field(name="부계정 역할 오류", value=auto_role_error, inline=False)

            embed.set_footer(text=f"등록자: {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)

        # ── 제거 ──────────────────────────────────────────────────────────
        elif 기능 == "제거":
            if not 부계정:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ 오류",
                    description="`부계정`을 지정해야 합니다.",
                    color=discord.Color.red()
                ))
                return

            # 확인 버튼 표시
            embed = discord.Embed(
                title="⚠️ 부계정 연결 해제 확인",
                description=f"{부계정.mention} 의 부계정 연결을 해제하고 킥하시겠습니까?",
                color=discord.Color.yellow()
            )
            embed.add_field(name="처리 내용", value="• DB 연결 해제\n• 모든 역할 제거\n• 서버에서 킥", inline=False)
            embed.set_footer(text="60초 내에 응답하지 않으면 자동 취소됩니다.")

            view = AltRemoveConfirmView(부계정, interaction.user.display_name)
            msg = await interaction.followup.send(embed=embed, view=view)
            view.message = msg

        # ── 목록 ──────────────────────────────────────────────────────────
        elif 기능 == "목록":
            # 본계정 지정 시: 해당 본계정의 부계정만 표시
            if 본계정:
                alts = db_manager.get_alt_accounts(본계정.id)
                embed = discord.Embed(
                    title="📋 부계정 목록",
                    description=f"본계정: {본계정.mention}",
                    color=discord.Color.blue()
                )
                if not alts:
                    embed.add_field(name="결과", value="등록된 부계정이 없습니다.", inline=False)
                else:
                    for i, alt in enumerate(alts, 1):
                        alt_member = interaction.guild.get_member(alt['alt_discord_id'])
                        alt_mention = alt_member.mention if alt_member else f"<@{alt['alt_discord_id']}>"
                        linked_at = alt['linked_at']
                        linked_str = (
                            linked_at.strftime("%Y-%m-%d %H:%M")
                            if isinstance(linked_at, datetime.datetime)
                            else str(linked_at)
                        )
                        embed.add_field(
                            name=f"부계정 {i}",
                            value=f"{alt_mention}\n등록일: {linked_str}",
                            inline=True
                        )
                await interaction.followup.send(embed=embed)
                return

            # 본계정 미지정: 전체 연결 목록 표시 (본계정별로 그룹화)
            all_rows = db_manager.get_all_alt_accounts()

            embed = discord.Embed(
                title="📋 전체 부계정 연결 목록",
                color=discord.Color.blue()
            )

            if not all_rows:
                embed.description = "등록된 부계정이 없습니다."
                await interaction.followup.send(embed=embed)
                return

            # main_discord_id 기준으로 그룹화
            from collections import defaultdict
            grouped = defaultdict(list)
            for row in all_rows:
                grouped[row['main_discord_id']].append(row)

            embed.description = f"총 본계정 **{len(grouped)}명** / 부계정 **{len(all_rows)}개** 등록됨"

            for main_id, alts in grouped.items():
                main_member = interaction.guild.get_member(main_id)
                main_str = main_member.mention if main_member else f"<@{main_id}>"

                alt_lines = []
                for alt in alts:
                    alt_member = interaction.guild.get_member(alt['alt_discord_id'])
                    alt_mention = alt_member.mention if alt_member else f"<@{alt['alt_discord_id']}>"
                    alt_lines.append(f"└ {alt_mention}")

                embed.add_field(
                    name=f"본계정: {main_member.display_name if main_member else main_id}",
                    value=f"{main_str}\n" + "\n".join(alt_lines),
                    inline=False
                )

                # embed 필드 25개 제한
                if len(embed.fields) >= 25:
                    embed.set_footer(text=f"⚠️ 25개 이상은 표시되지 않습니다. 본계정을 지정해서 조회하세요.")
                    break

            await interaction.followup.send(embed=embed)

        # ── 역할 ──────────────────────────────────────────────────────────
        elif 기능 == "역할":
            if not 역할:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ 오류",
                    description="`역할`을 지정해야 합니다.",
                    color=discord.Color.red()
                ))
                return

            # 부계정 없이 역할만 지정 → 서버 기본 부계정 역할로 설정
            if not 부계정:
                success = db_manager.set_alt_role(interaction.guild_id, 역할.id)
                if success:
                    embed = discord.Embed(title="✅ 부계정 자동 역할 설정 완료", color=discord.Color.green())
                    embed.add_field(name="설정된 역할", value=역할.mention, inline=False)
                    embed.add_field(
                        name="적용 시점",
                        value="이후 `/부계관리 기능:추가` 사용 시 본계정 역할과 함께 자동 부여됩니다.",
                        inline=False
                    )
                    embed.set_footer(text=f"설정자: {interaction.user.display_name}")
                else:
                    embed = discord.Embed(
                        title="❌ 오류",
                        description="역할 설정 중 DB 오류가 발생했습니다.",
                        color=discord.Color.red()
                    )
                await interaction.followup.send(embed=embed)
                return

            # 부계정 + 역할 모두 지정 → 특정 부계정에게 역할 부여
            try:
                await 부계정.add_roles(
                    역할,
                    reason=f"부계관리: 역할 부여 by {interaction.user.display_name}"
                )
                embed = discord.Embed(title="✅ 역할 부여 완료", color=discord.Color.green())
                embed.add_field(name="부계정", value=부계정.mention, inline=True)
                embed.add_field(name="부여된 역할", value=역할.mention, inline=True)
                embed.set_footer(text=f"처리자: {interaction.user.display_name}")
                await interaction.followup.send(embed=embed)
            except discord.Forbidden:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ 권한 오류",
                    description="봇이 해당 역할을 부여할 권한이 없습니다.",
                    color=discord.Color.red()
                ))
            except Exception as e:
                await interaction.followup.send(embed=discord.Embed(
                    title="❌ 오류",
                    description=f"역할 부여 중 오류가 발생했습니다: {e}",
                    color=discord.Color.red()
                ))

    @부계관리.error
    async def 부계관리_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ 권한 없음",
                    description="이 명령어는 관리자만 사용할 수 있습니다.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
