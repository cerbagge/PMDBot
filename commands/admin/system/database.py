# commands/admin/system/database.py
# /데이터베이스 명령어 - 데이터베이스 조회 및 관리

import discord
from discord import app_commands
from typing import Literal
import datetime

# 안전한 import 처리
try:
    from database_manager import db_manager
    DATABASE_ENABLED = True
except ImportError:
    db_manager = None
    DATABASE_ENABLED = False

try:
    from callsign_manager import callsign_manager
    CALLSIGN_ENABLED = True
except ImportError:
    callsign_manager = None
    CALLSIGN_ENABLED = False

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


# 데이터베이스 사용자 목록 페이지네이션 View
class DatabasePaginationView(discord.ui.View):
    def __init__(self, all_users: list, guild: discord.Guild, user_id: int, page_size: int = 20):
        super().__init__(timeout=300)
        self.all_users = all_users
        self.guild = guild
        self.user_id = user_id
        self.page_size = page_size
        self.current_page = 1
        self.total_pages = (len(all_users) + page_size - 1) // page_size

        # 페이지가 1개면 버튼 비활성화
        if self.total_pages <= 1:
            self.clear_items()

    def create_embed(self, page: int):
        start_idx = (page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_users = self.all_users[start_idx:end_idx]

        embed = discord.Embed(
            title="👥 전체 유저 목록",
            description=f"총 {len(self.all_users)}명 중 {start_idx + 1}-{min(end_idx, len(self.all_users))}번째",
            color=0x3498db
        )

        for i, user in enumerate(page_users, start_idx + 1):
            member = self.guild.get_member(int(user['discord_id']))
            member_name = member.name if member else f"Unknown"

            # datetime 객체 처리
            last_updated = user['last_updated']
            if hasattr(last_updated, 'strftime'):
                last_updated = last_updated.strftime('%Y-%m-%d')
            elif isinstance(last_updated, str):
                last_updated = last_updated[:10]

            nation = user.get('current_nation') or '없음'
            town = user.get('current_town') or '없음'

            embed.add_field(
                name=f"{i}. {member_name}",
                value=f"**MC닉네임:** `{user['current_minecraft_name']}`\n"
                      f"**국가:** {nation} / **마을:** {town}\n"
                      f"**업데이트:** {last_updated}",
                inline=True
            )

        embed.set_footer(text=f"페이지 {page}/{self.total_pages}")
        embed.timestamp = datetime.datetime.now()

        return embed

    @discord.ui.button(label="◀️ 이전", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 이 버튼을 사용할 권한이 없습니다.", ephemeral=True)
            return

        if self.current_page > 1:
            self.current_page -= 1
            embed = self.create_embed(self.current_page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="▶️ 다음", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 이 버튼을 사용할 권한이 없습니다.", ephemeral=True)
            return

        if self.current_page < self.total_pages:
            self.current_page += 1
            embed = self.create_embed(self.current_page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()


def setup(bot):
    """봇에 /데이터베이스 명령어 등록"""

    @bot.tree.command(name="데이터베이스", description="데이터베이스 조회 및 관리 (관리자 전용)")
    @app_commands.describe(
        기능="실행할 기능 선택",
        유저="조회할 Discord유저 (선택)",
        닉네임="검색할 MC닉네임 (선택)"
    )
    @app_commands.check(is_admin)
    async def 데이터베이스(
        interaction: discord.Interaction,
        기능: Literal["유저_조회", "MC닉네임_검색", "통계", "전체_유저"],
        유저: discord.Member = None,
        닉네임: str = None
    ):
        """데이터베이스 조회 및 관리 - 관리자 전용"""

        if not DATABASE_ENABLED or not db_manager:
            embed = discord.Embed(
                title="❌ 기능 비활성화",
                description="데이터베이스 기능이 비활성화되어 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if bot_logger:
            bot_logger.log_command("데이터베이스", interaction.user.id, interaction.user.name, source="admin_command", category=LogCategory.ADMIN, details={"기능": 기능})

        if 기능 == "유저_조회":
            if not 유저:
                await interaction.response.send_message("조회할 Discord유저를 지정해주세요.", ephemeral=True)
                return

            await interaction.response.defer()

            user_info = db_manager.get_user_info(유저.id)
            name_history = db_manager.get_name_history(유저.id, limit=10)

            if not user_info:
                embed = discord.Embed(
                    title="❌ 유저 정보 없음",
                    description=f"{유저.mention}의 정보가 데이터베이스에 없습니다.",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            embed = discord.Embed(
                title=f"💾 유저 데이터베이스 정보",
                description=f"**Discord유저:** {유저.mention}",
                color=0x00bfff
            )

            embed.add_field(
                name="🎮 Minecraft 정보",
                value=f"**현재 MC닉네임:** `{user_info['current_minecraft_name']}`\n"
                      f"**UUID:** `{user_info['minecraft_uuid']}`",
                inline=False
            )

            # datetime 객체 처리 (PostgreSQL은 datetime 객체 반환)
            first_seen = user_info['first_seen']
            last_updated = user_info['last_updated']
            if hasattr(first_seen, 'strftime'):
                first_seen = first_seen.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(first_seen, str):
                first_seen = first_seen[:19]
            if hasattr(last_updated, 'strftime'):
                last_updated = last_updated.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(last_updated, str):
                last_updated = last_updated[:19]

            embed.add_field(
                name="📅 기록",
                value=f"**첫 기록:** {first_seen}\n"
                      f"**최근 업데이트:** {last_updated}",
                inline=False
            )

            # 콜사인 정보 추가
            if CALLSIGN_ENABLED and callsign_manager:
                callsign_info = callsign_manager.get_callsign_info(유저.id)
                ban_info = callsign_manager.get_ban_info(유저.id)
                can_use, remaining_days = callsign_manager.check_cooldown(유저.id)

                callsign_text = ""

                if callsign_info:
                    callsign = callsign_info.get('callsign', 'N/A')
                    set_at = callsign_info.get('set_at', 'N/A')
                    if isinstance(set_at, str) and len(set_at) > 19:
                        set_at = set_at[:19]
                    callsign_text += f"**현재 콜사인:** `{callsign}`\n"
                    callsign_text += f"**설정 일시:** {set_at}\n"
                else:
                    callsign_text += f"**현재 콜사인:** 없음\n"

                if ban_info:
                    callsign_text += f"**상태:** ⛔ 콜사인 사용 금지\n"
                    callsign_text += f"**금지 사유:** {ban_info.get('reason', 'N/A')}\n"
                elif not can_use:
                    callsign_text += f"**쿨타임:** ⏳ {remaining_days}일 남음\n"
                else:
                    callsign_text += f"**상태:** ✅ 콜사인 변경 가능\n"

                embed.add_field(
                    name="📛 콜사인 정보",
                    value=callsign_text.strip(),
                    inline=False
                )

            if name_history:
                # 중복 제거: 같은 닉네임이 연속되면 최초 1회만 표시
                unique_names = []
                for h in name_history:
                    mc_name = h['minecraft_name']
                    if not unique_names or unique_names[-1]['minecraft_name'] != mc_name:
                        unique_names.append(h)
                history_lines = []
                for i, h in enumerate(unique_names[:5]):
                    changed_at = h['changed_at']
                    if hasattr(changed_at, 'strftime'):
                        changed_at = changed_at.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(changed_at, str):
                        changed_at = changed_at[:19]
                    history_lines.append(f"{i+1}. `{h['minecraft_name']}` - {changed_at}")
                history_text = "\n".join(history_lines)
                embed.add_field(
                    name=f"📝 MC닉네임 히스토리 (최근 {len(history_lines)}개)",
                    value=history_text or "히스토리 없음",
                    inline=False
                )

            # 국가/마을 히스토리 추가
            nation_history = db_manager.get_nation_history(유저.id, limit=30)
            if nation_history:
                # 중복 제거: 같은 국가+마을이 연속되면 최초 1회만 표시
                unique_nations = []
                for h in nation_history:
                    key = (h.get('nation_name') or '없음', h.get('town_name') or '없음')
                    if not unique_nations or (unique_nations[-1].get('nation_name') or '없음', unique_nations[-1].get('town_name') or '없음') != key:
                        unique_nations.append(h)
                nation_lines = []
                for i, h in enumerate(unique_nations[:5]):
                    changed_at = h.get('changed_at', '')
                    if hasattr(changed_at, 'strftime'):
                        changed_at = changed_at.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(changed_at, str):
                        changed_at = changed_at[:19]
                    nation_name = h.get('nation_name') or '없음'
                    town_name = h.get('town_name') or '없음'
                    nation_lines.append(f"{i+1}. **{nation_name}** / `{town_name}` - {changed_at}")
                nation_text = "\n".join(nation_lines)
                embed.add_field(
                    name=f"🏰 국가/마을 히스토리 (최근 {len(nation_lines)}개)",
                    value=nation_text,
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        elif 기능 == "MC닉네임_검색":
            if not 닉네임:
                await interaction.response.send_message("검색할 MC닉네임을 입력해주세요.", ephemeral=True)
                return

            await interaction.response.defer()

            results = db_manager.search_by_minecraft_name(닉네임)

            if not results:
                embed = discord.Embed(
                    title="🔍 검색 결과 없음",
                    description=f"`{닉네임}`와(과) 일치하는 유저를 찾을 수 없습니다.",
                    color=0xff6600
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # 검색 결과가 1명인 경우 - 유저_조회처럼 자세한 정보 표시
            if len(results) == 1:
                user = results[0]
                member = interaction.guild.get_member(int(user['discord_id']))
                name_history = db_manager.get_name_history(int(user['discord_id']), limit=10)

                embed = discord.Embed(
                    title=f"💾 유저 데이터베이스 정보",
                    description=f"**Discord유저:** {member.mention if member else 'Unknown (' + str(user['discord_id']) + ')'}",
                    color=0x00bfff
                )

                embed.add_field(
                    name="🎮 Minecraft 정보",
                    value=f"**현재 MC닉네임:** `{user['current_minecraft_name']}`\n"
                          f"**UUID:** `{user['minecraft_uuid']}`",
                    inline=False
                )

                # datetime 객체 처리 (PostgreSQL은 datetime 객체 반환)
                first_seen = user.get('first_seen')
                last_updated = user.get('last_updated')
                if first_seen:
                    if hasattr(first_seen, 'strftime'):
                        first_seen = first_seen.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(first_seen, str):
                        first_seen = first_seen[:19]
                else:
                    first_seen = 'N/A'
                if last_updated:
                    if hasattr(last_updated, 'strftime'):
                        last_updated = last_updated.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(last_updated, str):
                        last_updated = last_updated[:19]
                else:
                    last_updated = 'N/A'

                embed.add_field(
                    name="📅 기록",
                    value=f"**첫 기록:** {first_seen}\n"
                          f"**최근 업데이트:** {last_updated}",
                    inline=False
                )

                # 콜사인 정보 추가
                if CALLSIGN_ENABLED and callsign_manager:
                    discord_id_int = int(user['discord_id'])
                    callsign_info = callsign_manager.get_callsign_info(discord_id_int)
                    ban_info = callsign_manager.get_ban_info(discord_id_int)
                    can_use, remaining_days = callsign_manager.check_cooldown(discord_id_int)

                    callsign_text = ""

                    if callsign_info:
                        callsign = callsign_info.get('callsign', 'N/A')
                        set_at = callsign_info.get('set_at', 'N/A')
                        if isinstance(set_at, str) and len(set_at) > 19:
                            set_at = set_at[:19]
                        callsign_text += f"**현재 콜사인:** `{callsign}`\n"
                        callsign_text += f"**설정 일시:** {set_at}\n"
                    else:
                        callsign_text += f"**현재 콜사인:** 없음\n"

                    if ban_info:
                        callsign_text += f"**상태:** ⛔ 콜사인 사용 금지\n"
                        callsign_text += f"**금지 사유:** {ban_info.get('reason', 'N/A')}\n"
                    elif not can_use:
                        callsign_text += f"**쿨타임:** ⏳ {remaining_days}일 남음\n"
                    else:
                        callsign_text += f"**상태:** ✅ 콜사인 변경 가능\n"

                    embed.add_field(
                        name="📛 콜사인 정보",
                        value=callsign_text.strip(),
                        inline=False
                    )

                if name_history:
                    # 중복 제거: 같은 닉네임이 연속되면 최초 1회만 표시
                    unique_names = []
                    for h in name_history:
                        mc_name = h['minecraft_name']
                        if not unique_names or unique_names[-1]['minecraft_name'] != mc_name:
                            unique_names.append(h)
                    history_lines = []
                    for i, h in enumerate(unique_names[:5]):
                        changed_at = h['changed_at']
                        if hasattr(changed_at, 'strftime'):
                            changed_at = changed_at.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(changed_at, str):
                            changed_at = changed_at[:19]
                        history_lines.append(f"{i+1}. `{h['minecraft_name']}` - {changed_at}")
                    history_text = "\n".join(history_lines)
                    embed.add_field(
                        name=f"📝 MC닉네임 히스토리 (최근 {len(history_lines)}개)",
                        value=history_text or "히스토리 없음",
                        inline=False
                    )

                # 국가/마을 히스토리 추가
                nation_history = db_manager.get_nation_history(int(user['discord_id']), limit=30)
                if nation_history:
                    # 중복 제거: 같은 국가+마을이 연속되면 최초 1회만 표시
                    unique_nations = []
                    for h in nation_history:
                        key = (h.get('nation_name') or '없음', h.get('town_name') or '없음')
                        if not unique_nations or (unique_nations[-1].get('nation_name') or '없음', unique_nations[-1].get('town_name') or '없음') != key:
                            unique_nations.append(h)
                    nation_lines = []
                    for i, h in enumerate(unique_nations[:5]):
                        changed_at = h.get('changed_at', '')
                        if hasattr(changed_at, 'strftime'):
                            changed_at = changed_at.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(changed_at, str):
                            changed_at = changed_at[:19]
                        nation_name = h.get('nation_name') or '없음'
                        town_name = h.get('town_name') or '없음'
                        nation_lines.append(f"{i+1}. **{nation_name}** / `{town_name}` - {changed_at}")
                    nation_text = "\n".join(nation_lines)
                    embed.add_field(
                        name=f"🏰 국가/마을 히스토리 (최근 {len(nation_lines)}개)",
                        value=nation_text,
                        inline=False
                    )

                embed.set_footer(text=f"검색어: {닉네임}")
                await interaction.followup.send(embed=embed)

            # 검색 결과가 여러 명인 경우 - 목록 형태로 표시
            else:
                embed = discord.Embed(
                    title=f"🔍 MC닉네임 검색 결과",
                    description=f"**검색어:** `{닉네임}`\n**발견:** {len(results)}명",
                    color=0x00ff00,
                    timestamp=datetime.datetime.now()
                )

                for i, user in enumerate(results[:10], 1):
                    member = interaction.guild.get_member(int(user['discord_id']))
                    member_name = member.mention if member else f"Unknown User"
                    discord_id = user['discord_id']

                    # MC닉네임 히스토리 개수 확인
                    name_history = db_manager.get_name_history(int(discord_id), limit=1)
                    history_count = len(db_manager.get_name_history(int(discord_id), limit=100))

                    value_text = f"**Discord유저:** {member_name} (`{discord_id}`)\n"
                    value_text += f"**현재 MC닉네임:** `{user['current_minecraft_name']}`\n"
                    value_text += f"**UUID:** `{user['minecraft_uuid']}`\n"

                    if user.get('last_updated'):
                        last_upd = user['last_updated']
                        if hasattr(last_upd, 'strftime'):
                            last_upd = last_upd.strftime('%Y-%m-%d %H:%M:%S')
                        elif isinstance(last_upd, str):
                            last_upd = last_upd[:19]
                        value_text += f"**최근 업데이트:** {last_upd}\n"

                    if history_count > 1:
                        value_text += f"**MC닉네임 변경:** {history_count}회"

                    embed.add_field(
                        name=f"{i}. 유저 정보",
                        value=value_text,
                        inline=False
                    )

                if len(results) > 10:
                    embed.set_footer(text=f"10명까지 표시 중 (총 {len(results)}명)")
                else:
                    embed.set_footer(text=f"총 {len(results)}명")

                await interaction.followup.send(embed=embed)

        elif 기능 == "통계":
            await interaction.response.defer()

            stats = db_manager.get_statistics()

            embed = discord.Embed(
                title="📊 데이터베이스 통계",
                description="Minecraft 유저 데이터 통계",
                color=0x9b59b6
            )

            embed.add_field(
                name="📈 전체 통계",
                value=f"**총 유저:** {stats['total_users']}명\n"
                      f"**총 MC닉네임 변경:** {stats['total_name_changes']}회\n"
                      f"**최근 24시간 업데이트:** {stats['recent_updates']}명",
                inline=False
            )

            if stats.get('top_changers'):
                top_text = []
                for i, changer in enumerate(stats['top_changers'][:5], 1):
                    member = interaction.guild.get_member(int(changer['discord_id']))
                    member_name = member.mention if member else f"Unknown"
                    top_text.append(f"{i}. {member_name} - {changer['change_count']}회")

                embed.add_field(
                    name="🏆 MC닉네임 변경 Top 5",
                    value="\n".join(top_text) or "데이터 없음",
                    inline=False
                )

            embed.timestamp = datetime.datetime.now()
            await interaction.followup.send(embed=embed)

        elif 기능 == "전체_유저":
            await interaction.response.defer()

            # 모든 사용자 조회 (limit 없이)
            all_users = db_manager.get_all_users()

            if not all_users:
                embed = discord.Embed(
                    title="❌ 데이터 없음",
                    description="데이터베이스에 유저 정보가 없습니다.",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed)
                return

            # 페이지네이션 View 생성
            view = DatabasePaginationView(
                all_users=all_users,
                guild=interaction.guild,
                user_id=interaction.user.id,
                page_size=20
            )

            # 첫 페이지 임베드 생성
            embed = view.create_embed(page=1)

            await interaction.followup.send(embed=embed, view=view)

    # 에러 핸들러
    @데이터베이스.error
    async def 데이터베이스_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
