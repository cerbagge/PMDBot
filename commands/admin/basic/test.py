# commands/admin/basic/test.py
# /테스트 명령어 - 봇의 기본 기능을 테스트

import discord
from discord import app_commands
import os

# 안전한 import 처리
try:
    from queue_manager import queue_manager
except ImportError:
    class DummyQueueManager:
        def get_queue_size(self): return 0
        def is_processing(self): return False
    queue_manager = DummyQueueManager()

try:
    from exception_manager import exception_manager
except ImportError:
    class DummyExceptionManager:
        def get_exceptions(self): return []
    exception_manager = DummyExceptionManager()

try:
    from town_role_manager import town_role_manager
    TOWN_ROLE_ENABLED = True
except ImportError:
    town_role_manager = None
    TOWN_ROLE_ENABLED = False

try:
    from callsign_manager import callsign_manager
    CALLSIGN_ENABLED = True
except ImportError:
    callsign_manager = None
    CALLSIGN_ENABLED = False

# 환경 변수
MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")
BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")
SUCCESS_ROLE_ID = int(os.getenv("SUCCESS_ROLE_ID", "0"))

# 동맹 데이터 로드
import json
def load_alliance_data():
    try:
        with open("data/alliances.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"alliances": []}

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def setup(bot):
    """봇에 /테스트 명령어 등록"""

    @bot.tree.command(name="테스트", description="봇의 기본 기능을 테스트합니다")
    @app_commands.check(is_admin)
    async def 테스트(interaction: discord.Interaction):
        """봇 테스트 명령어"""
        await interaction.response.defer(thinking=True)

        embed = discord.Embed(
            title="🧪 봇 테스트 결과",
            color=0x00ff00
        )

        # 기본 정보
        embed.add_field(
            name="🤖 봇 정보",
            value=f"**봇 이름:** {bot.user.name}\n**핑:** {round(bot.latency * 1000)}ms",
            inline=False
        )

        # 서버 정보
        guild = interaction.guild
        embed.add_field(
            name="🏰 서버 정보",
            value=f"**서버 이름:** {guild.name}\n**멤버 수:** {guild.member_count}명",
            inline=False
        )

        # 환경변수 확인
        env_status = []
        env_status.append(f"MC_API_BASE: {'✅' if MC_API_BASE else '❌'}")
        env_status.append(f"BASE_NATION: {'✅' if BASE_NATION else '❌'}")
        env_status.append(f"SUCCESS_ROLE_ID: {'✅' if SUCCESS_ROLE_ID != 0 else '❌'}")
        env_status.append(f"TOWN_ROLE_ENABLED: {'✅' if TOWN_ROLE_ENABLED else '❌'}")
        env_status.append(f"CALLSIGN_ENABLED: {'✅' if CALLSIGN_ENABLED else '❌'}")

        embed.add_field(
            name="⚙️ 환경변수 상태",
            value="\n".join(env_status),
            inline=False
        )

        # 대기열 상태
        queue_size = queue_manager.get_queue_size()
        is_processing = queue_manager.is_processing()

        embed.add_field(
            name="📋 대기열 상태",
            value=f"**대기 중:** {queue_size}명\n**처리 상태:** {'🔄 처리 중' if is_processing else '⏸️ 대기 중'}",
            inline=False
        )

        # 예외 관리자 상태
        exception_count = len(exception_manager.get_exceptions())
        embed.add_field(
            name="🚫 예외 관리자",
            value=f"**예외 사용자:** {exception_count}명",
            inline=False
        )

        # 마을 역할 관리자 상태
        if TOWN_ROLE_ENABLED and town_role_manager:
            try:
                town_mapping_count = town_role_manager.get_mapping_count()
                embed.add_field(
                    name="🏘️ 마을 역할 관리자",
                    value=f"**연동된 마을:** {town_mapping_count}개",
                    inline=False
                )
            except:
                embed.add_field(
                    name="🏘️ 마을 역할 관리자",
                    value="**상태:** 로드됨 (일부 기능 제한)",
                    inline=False
                )

        # 콜사인 관리자 상태
        if CALLSIGN_ENABLED and callsign_manager:
            try:
                callsign_count = callsign_manager.get_callsign_count()
                embed.add_field(
                    name="🏷️ 콜사인 관리자",
                    value=f"**설정된 콜사인:** {callsign_count}개",
                    inline=False
                )
            except:
                embed.add_field(
                    name="🏷️ 콜사인 관리자",
                    value="**상태:** 로드됨 (일부 기능 제한)",
                    inline=False
                )

        # 동맹 시스템 상태
        try:
            alliance_data = load_alliance_data()
            alliance_count = len(alliance_data["alliances"])
            embed.add_field(
                name="🤝 동맹 시스템",
                value=f"**등록된 동맹:** {alliance_count}개",
                inline=False
            )
        except:
            embed.add_field(
                name="🤝 동맹 시스템",
                value="**상태:** 초기화 필요",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)
