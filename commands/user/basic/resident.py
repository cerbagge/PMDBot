# commands/user/basic/resident.py
# /resident 명령어 - 플레이어 정보 확인

import discord
from discord import app_commands
import aiohttp
import os

MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")


try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


def setup(bot):
    """봇에 /resident 명령어 등록"""

    @bot.tree.command(name="resident", description="플레이어 정보를 확인합니다.")
    @app_commands.describe(name="플레이어 이름을 입력해주세요")
    async def resident_command(interaction: discord.Interaction, name: str):
        await interaction.response.defer()

        if bot_logger:
            bot_logger.log_command("resident", interaction.user.id, interaction.user.name, source="user_command", category=LogCategory.COMMAND, details={"name": name})

        try:
            resident_data = None
            town_data = None
            db_fallback = False

            # === 1. bulk 캐시에서 먼저 조회 ===
            bulk_mgr = getattr(interaction.client, 'bulk_data_manager', None)
            if bulk_mgr:
                cached = bulk_mgr.get_resident_by_name(name)
                if cached:
                    resident_data = cached
                    if cached.get("town"):
                        town_cached = bulk_mgr.get_town_by_name(cached["town"])
                        if town_cached:
                            town_data = town_cached

            # === 2. API 폴백 ===
            if not resident_data:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{MC_API_BASE}/resident",
                            params={"name": name},
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as res:
                            if res.status == 200:
                                response_data = await res.json()
                                if isinstance(response_data, dict) and "data" in response_data:
                                    if response_data["data"]:
                                        resident_data = response_data["data"][0]
                                else:
                                    resident_data = response_data

                        # town_data가 아직 없으면 API로 조회
                        if resident_data and not town_data and resident_data.get("town"):
                            async with session.get(
                                f"{MC_API_BASE}/town",
                                params={"name": resident_data["town"]},
                                timeout=aiohttp.ClientTimeout(total=5)
                            ) as res:
                                if res.status == 200:
                                    town_response = await res.json()
                                    if isinstance(town_response, dict) and "data" in town_response:
                                        if town_response["data"]:
                                            town_data = town_response["data"][0]
                                    else:
                                        town_data = town_response
                except Exception:
                    pass  # API 실패 → DB 폴백으로 진행

            # === 3. DB 폴백 (all_players 테이블) ===
            if not resident_data:
                try:
                    from database_manager import db_manager
                    db_player = db_manager.get_player_by_name(name)
                    if db_player:
                        resident_data = db_player
                        db_fallback = True
                except Exception:
                    pass

            # === 데이터 없음 ===
            if not resident_data:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 오류",
                        description="존재하지 않는 플레이어입니다!",
                        color=discord.Color.red()
                    )
                )
                return

            embed = discord.Embed(
                title=resident_data.get("name", name).replace("_", "\\_"),
                color=discord.Color.green()
            )
            embed.set_thumbnail(
                url=f"https://mc-heads.net/avatar/{resident_data.get('name', name)}/600.png"
            )

            # 온라인 상태 (API/bulk 캐시 데이터에만 있음)
            if "online" in resident_data:
                is_online = resident_data.get("online", False)
                online_status = "🟢 온라인" if is_online else "🔴 오프라인"
                embed.add_field(name="**상태**", value=online_status, inline=False)

            if resident_data.get("registered"):
                embed.add_field(
                    name="**최초 접속일**",
                    value=f"<t:{int(resident_data['registered'])//1000}:f>",
                    inline=False
                )

            if resident_data.get("lastOnline"):
                embed.add_field(
                    name="**최근 접속일**",
                    value=f"<t:{int(resident_data['lastOnline'])//1000}:f>",
                    inline=False
                )

            embed.add_field(
                name="**마을**",
                value=resident_data["town"].replace("_", "\\_") if resident_data.get("town") else "없음",
                inline=False
            )

            # 국가: API는 town_data["nation"], DB all_players는 nation 필드 직접 보유
            nation_val = None
            if town_data and town_data.get("nation"):
                nation_val = town_data["nation"]
            elif resident_data.get("nation"):
                nation_val = resident_data["nation"]
            embed.add_field(
                name="**국가**",
                value=nation_val.replace("_", "\\_") if nation_val else "없음",
                inline=False
            )

            if db_fallback:
                embed.set_footer(text="⚠️ API 연결 불가 — DB 캐시 데이터 (최신 정보와 다를 수 있습니다)")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ 오류",
                    description=f"오류가 발생했습니다: {str(e)[:100]}",
                    color=discord.Color.red()
                )
            )
