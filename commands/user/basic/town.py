# commands/user/basic/town.py
# /town 명령어 - 마을 정보 확인

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
    """봇에 /town 명령어 등록"""

    @bot.tree.command(name="town", description="마을 정보를 확인합니다.")
    @app_commands.describe(name="마을 이름을 입력해주세요")
    async def town_command(interaction: discord.Interaction, name: str):
        await interaction.response.defer()

        if bot_logger:
            bot_logger.log_command("town", interaction.user.id, interaction.user.name, source="user_command", category=LogCategory.COMMAND, details={"name": name})

        try:
            town_data = None
            db_fallback = False

            # === 1. bulk 캐시에서 먼저 조회 ===
            bulk_mgr = getattr(interaction.client, 'bulk_data_manager', None)
            if bulk_mgr:
                cached = bulk_mgr.get_town_by_name(name)
                if cached:
                    town_data = cached

            # === 2. API 폴백 ===
            if not town_data:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{MC_API_BASE}/town",
                            params={"name": name},
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as res:
                            if res.status == 200:
                                response_data = await res.json()
                                if isinstance(response_data, dict) and "data" in response_data:
                                    if response_data["data"]:
                                        town_data = response_data["data"][0]
                                else:
                                    town_data = response_data
                except Exception:
                    pass  # API 실패 → DB 폴백으로 진행

            # === 3. DB 폴백 (all_towns 테이블) ===
            if not town_data:
                try:
                    from database_manager import db_manager
                    db_town = db_manager.get_town_by_name(name)
                    if db_town:
                        # DB 컬럼명 → API 필드명 매핑
                        db_town["board"] = db_town.get("town_board")
                        db_town["numResidents"] = db_town.get("num_residents")
                        db_town["numTownBlocks"] = db_town.get("num_town_blocks")
                        town_data = db_town
                        db_fallback = True
                except Exception:
                    pass

            # === 데이터 없음 ===
            if not town_data:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 오류",
                        description="존재하지 않는 마을입니다!",
                        color=discord.Color.red()
                    )
                )
                return

            embed = discord.Embed(
                title=town_data.get("name", name).replace("_", "\\_"),
                color=discord.Color.green()
            )

            # 공지
            board = town_data.get("townBoard") or town_data.get("board") or "없음"
            embed.add_field(
                name="**공지**",
                value=str(board).replace("_", "\\_"),
                inline=False
            )

            # 시장
            mayor = town_data.get("mayor") or "없음"
            embed.add_field(
                name="**시장**",
                value=str(mayor).replace("_", "\\_"),
                inline=False
            )

            # 국가
            nation = town_data.get("nation") or "없음"
            embed.add_field(
                name="**국가**",
                value=str(nation).replace("_", "\\_") if nation != "없음" else "없음",
                inline=False
            )

            # 주민 수
            member_count = town_data.get("memberCount") or town_data.get("numResidents") or 0
            embed.add_field(
                name="**주민 수**",
                value=str(member_count),
                inline=False
            )

            # 클레임 크기
            claim_size = town_data.get("claimSize") or town_data.get("numTownBlocks") or 0
            embed.add_field(
                name="**클레임 크기**",
                value=str(claim_size),
                inline=False
            )

            # 설립일
            if town_data.get("registered"):
                embed.add_field(
                    name="**설립일**",
                    value=f"<t:{int(town_data['registered'])//1000}:f>",
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
