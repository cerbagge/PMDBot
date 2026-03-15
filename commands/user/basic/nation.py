# commands/user/basic/nation.py
# /nation 명령어 - 국가 정보 확인

import discord
from discord import app_commands
import aiohttp
import json
import os

MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")


def setup(bot):
    """봇에 /nation 명령어 등록"""

    @bot.tree.command(name="nation", description="국가 정보를 확인합니다.")
    @app_commands.describe(name="국가 이름을 입력해주세요")
    async def nation_command(interaction: discord.Interaction, name: str):
        await interaction.response.defer()

        try:
            nation_data = None
            db_fallback = False

            # === 1. bulk 캐시에서 먼저 조회 ===
            bulk_mgr = getattr(interaction.client, 'bulk_data_manager', None)
            if bulk_mgr:
                cached = bulk_mgr.get_nation_by_name(name)
                if cached:
                    nation_data = cached

            # === 2. API 폴백 ===
            if not nation_data:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{MC_API_BASE}/nation",
                            params={"name": name},
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as res:
                            if res.status == 200:
                                response_data = await res.json()
                                if isinstance(response_data, dict) and "data" in response_data:
                                    if response_data["data"]:
                                        nation_data = response_data["data"][0]
                                else:
                                    nation_data = response_data
                except Exception:
                    pass  # API 실패 → DB 폴백으로 진행

            # === 3. DB 폴백 (all_nations 테이블) ===
            if not nation_data:
                try:
                    from database_manager import db_manager
                    db_nation = db_manager.get_nation_by_name(name)
                    if db_nation:
                        # DB 컬럼명 → API 필드명 매핑
                        db_nation["board"] = db_nation.get("nation_board")
                        db_nation["numResidents"] = db_nation.get("num_residents")
                        # towns/allies/enemies는 DB에 JSON 문자열로 저장됨 → 리스트로 파싱
                        for field in ("towns", "allies", "enemies"):
                            raw = db_nation.get(field)
                            if isinstance(raw, str):
                                try:
                                    db_nation[field] = json.loads(raw)
                                except Exception:
                                    db_nation[field] = []
                            elif not isinstance(raw, list):
                                db_nation[field] = []
                        nation_data = db_nation
                        db_fallback = True
                except Exception:
                    pass

            # === 데이터 없음 ===
            if not nation_data:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 오류",
                        description="존재하지 않는 국가입니다!",
                        color=discord.Color.red()
                    )
                )
                return

            embed = discord.Embed(
                title=nation_data.get("name", name).replace("_", "\\_"),
                color=discord.Color.green()
            )

            # 공지
            board = nation_data.get("nationBoard") or nation_data.get("board") or "없음"
            embed.add_field(
                name="**공지**",
                value=str(board).replace("_", "\\_"),
                inline=False
            )

            # 왕
            leader = nation_data.get("leader") or nation_data.get("king") or "없음"
            embed.add_field(
                name="**왕**",
                value=str(leader).replace("_", "\\_"),
                inline=False
            )

            # 국민 수
            member_count = nation_data.get("memberCount") or nation_data.get("numResidents") or 0
            embed.add_field(
                name="**국민 수**",
                value=str(member_count),
                inline=False
            )

            # 마을
            towns = nation_data.get("towns", [])
            if isinstance(towns, list):
                towns_str = ", ".join(str(t).replace("_", "\\_") for t in towns[:10]) if towns else "없음"
                if len(towns) > 10:
                    towns_str += f" 외 {len(towns) - 10}개"
            else:
                towns_str = str(towns).replace("_", "\\_") if towns else "없음"
            embed.add_field(
                name="**마을**",
                value=towns_str,
                inline=False
            )

            # 동맹
            allies = nation_data.get("allies", [])
            if isinstance(allies, list):
                allies_str = ", ".join(str(a).replace("_", "\\_") for a in allies) if allies else "없음"
            else:
                allies_str = str(allies).replace("_", "\\_") if allies else "없음"
            embed.add_field(
                name="**동맹**",
                value=allies_str,
                inline=False
            )

            # 적
            enemies = nation_data.get("enemies", [])
            if isinstance(enemies, list):
                enemies_str = ", ".join(str(e).replace("_", "\\_") for e in enemies) if enemies else "없음"
            else:
                enemies_str = str(enemies).replace("_", "\\_") if enemies else "없음"
            embed.add_field(
                name="**적**",
                value=enemies_str,
                inline=False
            )

            # 설립일
            if nation_data.get("registered"):
                embed.add_field(
                    name="**설립일**",
                    value=f"<t:{int(nation_data['registered'])//1000}:f>",
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
