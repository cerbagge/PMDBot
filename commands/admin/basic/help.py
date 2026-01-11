# commands/admin/basic/help.py
# /도움말 명령어 - 봇의 모든 명령어를 확인

import discord
from discord import app_commands
import datetime
import os
import json

# 안전한 import 처리
try:
    from queue_manager import queue_manager
except ImportError:
    class DummyQueueManager:
        def get_queue_size(self): return 0
        def is_processing(self): return False
    queue_manager = DummyQueueManager()

try:
    from callsign_manager import callsign_manager
    CALLSIGN_ENABLED = True
except ImportError:
    CALLSIGN_ENABLED = False

try:
    from town_role_manager import town_role_manager
    TOWN_ROLE_ENABLED = True
except ImportError:
    TOWN_ROLE_ENABLED = False

# 환경 변수
MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")
BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")

# 동맹 데이터 로드
def load_alliance_data():
    try:
        with open("data/alliances.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"alliances": []}


def setup(bot):
    """봇에 /도움말 명령어 등록"""

    @bot.tree.command(name="도움말", description="봇의 모든 명령어를 확인합니다")
    async def 도움말(interaction: discord.Interaction):
        """봇의 모든 명령어와 설명을 표시 - 개선된 버전"""

        # 관리자 권한 확인
        is_admin = interaction.user.guild_permissions.administrator

        # 메인 임베드 생성
        embed = discord.Embed(
            title="📖 국민확인봇 명령어 가이드",
            description=f"안녕하세요 {interaction.user.mention}님! 🎉\n사용 가능한 명령어들을 확인해보세요.",
            color=0x2f3136
        )

        # 썸네일 추가 (봇 아바타)
        if bot.user.avatar:
            embed.set_thumbnail(url=bot.user.avatar.url)

        # 일반 사용자 명령어
        user_commands_info = {
            "확인": {
                "emoji": "✅",
                "desc": "자신의 국적을 확인하고 역할을 받습니다",
                "usage": "`/확인`",
                "note": "마인크래프트 계정이 연동되어 있어야 합니다"
            },
            "콜사인": {
                "emoji": "🏷️",
                "desc": "개인 콜사인을 설정합니다 (15일 쿨타임)",
                "usage": "`/콜사인 텍스트:콜사인이름`",
                "note": "최대 20자, 국가명 대신 표시됩니다" if CALLSIGN_ENABLED else "콜사인 기능이 비활성화됨"
            },
            "국가설정": {
                "emoji": "🌍",
                "desc": "자신의 국가를 설정합니다",
                "usage": "`/국가설정 국가:국가이름`",
                "note": "영어로 정확한 국가명을 입력하세요"
            },
            "도움말": {
                "emoji": "📖",
                "desc": "봇의 모든 명령어를 확인합니다",
                "usage": "`/도움말`",
                "note": "언제든지 사용 가능합니다"
            }
        }

        user_cmd_text = ""
        for cmd_name, info in user_commands_info.items():
            user_cmd_text += f"{info['emoji']} **{info['usage']}**\n"
            user_cmd_text += f"   └ {info['desc']}\n"
            user_cmd_text += f"   └ 💡 *{info['note']}*\n\n"

        embed.add_field(
            name="👥 일반 사용자 명령어",
            value=user_cmd_text.strip(),
            inline=False
        )

        # 관리자 명령어 - 카테고리별로 분류
        if is_admin:
            # 기본 관리 명령어
            basic_admin_text = ""
            basic_admin_commands = {
                "테스트": "봇의 기본 기능을 테스트합니다",
                "스케줄확인": "자동 실행 스케줄 정보를 확인합니다",
                "서버국가설정": "디스코드 봇이 관리할 기본 국가를 설정합니다"
            }

            for cmd_name, desc in basic_admin_commands.items():
                basic_admin_text += f"🔧 **`/{cmd_name}`** - {desc}\n"

            embed.add_field(
                name="🛠️ 기본 관리 명령어",
                value=basic_admin_text,
                inline=True
            )

            # 사용자 관리 명령어
            user_mgmt_text = ""
            user_mgmt_commands = {
                "국민확인": "사용자들의 국적을 확인합니다",
                "예외설정": "자동실행 예외 대상을 관리합니다"
            }

            # 콜사인 관리 추가 (활성화된 경우)
            if CALLSIGN_ENABLED:
                user_mgmt_commands["콜사인관리"] = "사용자 콜사인을 관리합니다"

            for cmd_name, desc in user_mgmt_commands.items():
                user_mgmt_text += f"👤 **`/{cmd_name}`** - {desc}\n"

            embed.add_field(
                name="👥 사용자 관리",
                value=user_mgmt_text,
                inline=True
            )

            # 대기열 관리 명령어
            queue_mgmt_text = ""
            queue_mgmt_commands = {
                "대기열상태": "현재 대기열 상태를 확인합니다",
                "대기열초기화": "대기열을 모두 비웁니다",
                "자동실행시작": "자동 역할 부여를 수동으로 시작합니다",
                "자동실행": "자동 등록할 역할을 설정합니다"
            }

            for cmd_name, desc in queue_mgmt_commands.items():
                queue_mgmt_text += f"📋 **`/{cmd_name}`** - {desc}\n"

            embed.add_field(
                name="📋 대기열 관리",
                value=queue_mgmt_text,
                inline=False
            )

            # 동맹 관리 명령어 추가
            alliance_mgmt_text = (
                "🤝 **`/동맹설정 기능:추가 이름:국가명 역할:@역할`** - 새로운 동맹 국가/마을을 추가합니다 (자동 감지)\n"
                "🤝 **`/동맹설정 기능:제거 이름:국가명`** - 동맹을 제거합니다\n"
                "🤝 **`/동맹설정 기능:목록`** - 동맹 목록을 확인합니다 (UUID 기반)\n"
                "🤝 **`/동맹설정 기능:역할설정 이름:국가명 역할:@역할`** - 동맹의 역할을 설정합니다\n"
                "🔍 **`/동맹확인`** - 모든 멤버의 동맹 역할을 재확인합니다"
            )

            embed.add_field(
                name="🤝 동맹 관리",
                value=alliance_mgmt_text,
                inline=False
            )

            # 마을 역할 관리 (활성화된 경우에만)
            if TOWN_ROLE_ENABLED:
                town_mgmt_text = (
                    "🏘️ **`/마을역할 기능:추가`** - 마을과 역할을 연동합니다\n"
                    "🏘️ **`/마을역할 기능:제거`** - 마을 역할 연동을 해제합니다\n"
                    "🏘️ **`/마을역할 기능:목록`** - 연동된 마을-역할 목록을 확인합니다\n"
                    "🏘️ **`/마을역할 기능:마을목록`** - 마을 연동 가이드를 확인합니다\n"
                    "🧪 **`/마을테스트`** - 마을 검증 기능을 테스트합니다"
                )

                embed.add_field(
                    name="🏘️ 마을 역할 관리",
                    value=town_mgmt_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="🏘️ 마을 역할 관리",
                    value="🔴 **비활성화됨** - town_role_manager 모듈이 필요합니다.",
                    inline=False
                )
        else:
            # 관리자가 아닌 경우 (서버국가설정 명령어 추가로 +1)
            total_admin_commands = 18 + (1 if CALLSIGN_ENABLED else 0) + (5 if TOWN_ROLE_ENABLED else 0)
            embed.add_field(
                name="🛡️ 관리자 전용 명령어",
                value=f"🔒 관리자 전용 명령어 **{total_admin_commands}개**가 있습니다.\n"
                      f"관리자 권한이 필요합니다.",
                inline=False
            )

        # 봇 상태 정보
        queue_size = queue_manager.get_queue_size()
        is_processing = queue_manager.is_processing()
        processing_status = "🔄 처리 중" if is_processing else "⏸️ 대기 중"

        # 동맹 시스템 상태 추가
        try:
            alliance_data = load_alliance_data()
            alliance_count = len(alliance_data["alliances"])
        except:
            alliance_count = 0

        status_text = (
            f"🌐 **API 상태**: {'🟢 연결됨' if MC_API_BASE else '🔴 설정 필요'}\n"
            f"🏴 **기본 국가**: {BASE_NATION}\n"
            f"🤝 **동맹 국가**: {alliance_count}개\n"
            f"🏘️ **마을 역할**: {'🟢 활성화' if TOWN_ROLE_ENABLED else '🔴 비활성화'}\n"
            f"🏷️ **콜사인 기능**: {'🟢 활성화' if CALLSIGN_ENABLED else '🔴 비활성화'}\n"
            f"📋 **대기열**: {queue_size}명 ({processing_status})"
        )

        embed.add_field(
            name="📊 봇 상태",
            value=status_text,
            inline=True
        )

        # 사용 팁
        tips_text = (
            "💡 `/확인` 명령어로 언제든 역할을 다시 받을 수 있어요!\n"
            "💡 `/국가설정`으로 자신의 국가를 설정하세요.\n"
            f"💡 {'`/콜사인`으로 개인 콜사인을 설정하세요.' if CALLSIGN_ENABLED else '콜사인 기능이 비활성화되어 있습니다.'}\n"
            "💡 마인크래프트 계정 연동이 필요합니다."
        )

        embed.add_field(
            name="💡 사용 팁",
            value=tips_text,
            inline=True
        )

        # 푸터 정보
        total_commands = len(bot.tree.get_commands())
        embed.set_footer(
            text=f"🤖 {bot.user.name} • 총 {total_commands}개 명령어 • 권한: {'관리자' if is_admin else '일반 사용자'}",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )

        # 현재 시간 추가
        embed.timestamp = datetime.datetime.now()

        await interaction.response.send_message(embed=embed, ephemeral=True)
