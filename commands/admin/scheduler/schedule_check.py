# commands/admin/scheduler/schedule_check.py
# /스케줄확인 명령어 - 자동 실행 스케줄 정보를 확인

import discord
from discord import app_commands

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def setup(bot):
    """봇에 /스케줄확인 명령어 등록"""

    @bot.tree.command(name="스케줄확인", description="자동 실행 스케줄 정보를 확인합니다")
    @app_commands.check(is_admin)
    async def 스케줄확인(interaction: discord.Interaction):
        """스케줄러 상태 확인"""
        try:
            from scheduler import get_scheduler_info

            info = get_scheduler_info()

            embed = discord.Embed(
                title="📅 자동 실행 스케줄 정보",
                color=0x00ff00 if info["running"] else 0xff0000
            )

            # 스케줄러 상태
            status = "🟢 실행 중" if info["running"] else "🔴 중지됨"
            embed.add_field(
                name="⚙️ 스케줄러 상태",
                value=status,
                inline=False
            )

            # 자동 실행 설정
            day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            day_name = day_names[info["auto_execution_day"]]

            embed.add_field(
                name="🕒 자동 실행 스케줄",
                value=f"**매주 {day_name}** {info['auto_execution_hour']:02d}:{info['auto_execution_minute']:02d}",
                inline=False
            )

            # 등록된 작업들
            if info["jobs"]:
                job_list = []
                for job in info["jobs"]:
                    job_list.append(f"• **{job['name']}**\n  다음 실행: {job['next_run']}")

                embed.add_field(
                    name="📋 등록된 작업",
                    value="\n\n".join(job_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📋 등록된 작업",
                    value="등록된 작업이 없습니다.",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="scheduler 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 오류 발생",
                description=f"스케줄 정보를 가져오는 중 오류가 발생했습니다.\n{str(e)}",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
