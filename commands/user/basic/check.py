# commands/admin/basic/check.py
# /확인 명령어 - 자신의 국적을 확인하고 역할을 받음

import discord
from discord import app_commands
import aiohttp
import os

# 환경 변수
BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")


def setup(bot):
    """봇에 /확인 명령어 등록"""

    @bot.tree.command(name="확인", description="자신의 국적을 확인하고 역할을 받습니다")
    async def 확인(interaction: discord.Interaction):
        """사용자 본인의 국적 확인 및 역할 부여 - scheduler의 process_single_user 사용"""
        await interaction.response.defer(thinking=True)

        member = interaction.user
        discord_id = member.id

        print(f"🔍 /확인 명령어 시작 - 사용자: {member.display_name} (ID: {discord_id})")

        # scheduler의 process_single_user 함수 import
        try:
            from scheduler import process_single_user
        except ImportError:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ 오류",
                    description="scheduler 모듈을 로드할 수 없습니다.",
                    color=0xff0000
                ),
                ephemeral=True
            )
            return

        # aiohttp 세션 생성 및 처리
        try:
            async with aiohttp.ClientSession() as session:
                result = await process_single_user(interaction.client, session, discord_id)

            # 결과 확인 및 사용자별 메시지 생성
            if result and result.get('success'):
                nation = result.get('nation', 'Unknown')
                town = result.get('town', 'Unknown')
                mc_id = result.get('mc_id', 'Unknown')
                role_changes = result.get('role_changes', [])
                is_incomplete = result.get('incomplete', False)

                # 국가/마을 정보가 불완전한 경우
                if is_incomplete:
                    embed = discord.Embed(
                        title="⚠️ 국가/마을 정보 없음",
                        description="게임 내에서 만약 국가/마을에 가입을 했으면 ``/확인``을 쳐서 재인증 해주세요.",
                        color=0xff6600
                    )

                    # 마인크래프트 정보
                    mc_info = f"**닉네임:** ``{mc_id}``"
                    if town and town not in ["❌", "무소속"]:
                        mc_info += f"\n**마을:** ``{town}``"
                    else:
                        mc_info += f"\n**마을:** 없음"
                    if nation and nation not in ["❌", "무소속"]:
                        mc_info += f"\n**국가:** ``{nation}``"
                    else:
                        mc_info += f"\n**국가:** 없음"

                    embed.add_field(
                        name="🎮 마인크래프트 정보",
                        value=mc_info,
                        inline=False
                    )

                # 국가에 따른 메시지 생성
                elif nation == BASE_NATION:
                    embed = discord.Embed(
                        title="✅ 국민 확인 완료",
                        description=f"**``{BASE_NATION}``** 국민으로 확인되었습니다!",
                        color=0x00ff00
                    )

                    embed.add_field(
                        name="🎮 마인크래프트 정보",
                        value=f"**닉네임:** ``{mc_id}``\n**마을:** ``{town}``\n**국가:** ``{nation}``",
                        inline=False
                    )
                else:
                    embed = discord.Embed(
                        title="⚠️ 다른 국가 소속",
                        description=f"**``{nation}``** 국가에 소속되어 있습니다.",
                        color=0xff9900
                    )

                    embed.add_field(
                        name="🎮 마인크래프트 정보",
                        value=f"**닉네임:** ``{mc_id}``\n**마을:** ``{town}``\n**국가:** ``{nation}``",
                        inline=False
                    )

                # 변경 사항
                if role_changes:
                    changes_text = "\n".join(role_changes[:10])  # 최대 10개
                    embed.add_field(
                        name="🔄 변경 사항",
                        value=changes_text,
                        inline=False
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)
                print(f"🏁 /확인 처리 완료 - {member.display_name}: {nation}/{town}")
            else:
                # 처리 실패
                error_msg = result.get('error', '알 수 없는 오류') if result else '처리 실패'
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 확인 실패",
                        description=f"{error_msg}",
                        color=0xff0000
                    ),
                    ephemeral=True
                )
                print(f"❌ /확인 처리 실패 - {member.display_name}: {error_msg}")

        except Exception as e:
            print(f"💥 /확인 예외 발생: {e}")
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ 오류 발생",
                    description=f"처리 중 오류가 발생했습니다.\n{str(e)[:100]}",
                    color=0xff0000
                ),
                ephemeral=True
            )
