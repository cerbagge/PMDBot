# commands/user/basic/help.py
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
        """봇의 모든 명령어와 설명을 표시"""

        # 관리자 권한 확인
        is_admin = interaction.user.guild_permissions.administrator

        # ===== 페이지 1: 일반 사용자 명령어 =====
        embed1 = discord.Embed(
            title="📖 국민확인봇 명령어 가이드",
            description=f"안녕하세요 {interaction.user.mention}님!\n사용 가능한 명령어들을 확인해보세요.",
            color=0x2f3136
        )

        if bot.user.avatar:
            embed1.set_thumbnail(url=bot.user.avatar.url)

        # 일반 사용자 명령어
        user_cmd_text = (
            "✅ **`/확인`**\n"
            "   └ 자신의 국적을 확인하고 역할을 받습니다\n"
            "   └ 💡 *마인크래프트 계정이 연동되어 있어야 합니다*\n\n"

            "🔍 **`/resident <이름>`**\n"
            "   └ 플레이어 정보를 확인합니다 (온라인 상태, 접속일 등)\n\n"

            "🏛️ **`/nation <이름>`**\n"
            "   └ 국가 정보를 확인합니다 (왕, 국민 수, 마을, 동맹 등)\n\n"

            "🏘️ **`/town <이름>`**\n"
            "   └ 마을 정보를 확인합니다 (시장, 주민 수, 클레임 등)\n\n"

            "🏷️ **`/콜사인 <텍스트>`**\n"
            f"   └ {'개인 콜사인을 설정합니다 (15일 쿨타임, 최대 20자)' if CALLSIGN_ENABLED else '콜사인 기능이 비활성화됨'}\n\n"

            "✈️ **`/여행신청`**\n"
            "   └ 여행 신청서를 제출합니다\n\n"

            "📖 **`/도움말`**\n"
            "   └ 이 도움말을 표시합니다"
        )

        embed1.add_field(
            name="👥 일반 사용자 명령어",
            value=user_cmd_text,
            inline=False
        )

        embeds = [embed1]

        # ===== 관리자 명령어 =====
        if is_admin:
            # 페이지 2: 관리자 명령어 - 기본 / 대기열 / 스케줄러
            embed2 = discord.Embed(
                title="🛠️ 관리자 명령어 (1/3)",
                color=0x2f3136
            )

            # 기본 관리
            basic_text = (
                "🔧 **`/테스트`** - 봇의 기본 기능을 테스트합니다\n"
                "🔧 **`/국가설정 <국가>`** - 봇이 관리할 기본 국가를 설정합니다\n"
                "🔧 **`/스케줄확인`** - 자동 실행 스케줄 정보를 확인합니다"
            )
            embed2.add_field(name="🔧 기본 관리", value=basic_text, inline=False)

            # 대기열 관리
            queue_text = (
                "📋 **`/대기열추가 <유저 또는 역할>`** - 유저/역할 멤버를 대기열에 추가\n"
                "📋 **`/대기열상태`** - 현재 대기열 상태를 확인합니다\n"
                "📋 **`/대기열초기화`** - 대기열을 모두 비웁니다\n"
                "📋 **`/서버대기열`** - MC 서버 접속 대기열 인원을 확인합니다\n"
                "📋 **`/자동실행시작`** - 자동 역할 부여를 수동으로 시작합니다\n"
                "📋 **`/자동실행`** - 자동 등록할 역할을 설정합니다"
            )
            embed2.add_field(name="📋 대기열 관리", value=queue_text, inline=False)

            # 사용자 관리
            user_mgmt_text = (
                "👤 **`/예외설정`** - 자동실행 예외 대상을 관리합니다\n"
                "👤 **`/뉴비설정`** - 뉴비 알림 채널/역할을 설정합니다\n"
                "👤 **`/뉴비확인`** - 현재 뉴비 목록을 표시합니다"
            )
            if CALLSIGN_ENABLED:
                user_mgmt_text += "\n👤 **`/콜사인관리`** - 사용자 콜사인을 관리합니다"
            embed2.add_field(name="👤 사용자 관리", value=user_mgmt_text, inline=False)

            embeds.append(embed2)

            # 페이지 3: 동맹 / 마을 / 여행
            embed3 = discord.Embed(
                title="🛠️ 관리자 명령어 (2/3)",
                color=0x2f3136
            )

            # 동맹 관리
            alliance_text = (
                "🤝 **`/동맹설정 기능:추가 이름:<국가명> 역할:@역할`** - 동맹 추가\n"
                "🤝 **`/동맹설정 기능:제거 이름:<국가명>`** - 동맹 제거\n"
                "🤝 **`/동맹설정 기능:목록`** - 동맹 목록 확인 (UUID 기반)\n"
                "🤝 **`/동맹설정 기능:역할설정 이름:<국가명> 역할:@역할`** - 동맹 역할 설정\n"
                "🔍 **`/동맹확인`** - 모든 멤버의 동맹 역할을 재확인합니다"
            )
            embed3.add_field(name="🤝 동맹 관리", value=alliance_text, inline=False)

            # 마을 역할
            if TOWN_ROLE_ENABLED:
                town_text = (
                    "🏘️ **`/마을역할 기능:추가`** - 마을과 역할을 연동합니다\n"
                    "🏘️ **`/마을역할 기능:제거`** - 마을 역할 연동을 해제합니다\n"
                    "🏘️ **`/마을역할 기능:목록`** - 연동된 마을-역할 목록\n"
                    "🏘️ **`/마을역할 기능:마을목록`** - 마을 연동 가이드\n"
                    "🧪 **`/마을테스트`** - 마을 검증 기능을 테스트합니다"
                )
            else:
                town_text = "🔴 **비활성화됨** - town_role_manager 모듈이 필요합니다."
            embed3.add_field(name="🏘️ 마을 역할 관리", value=town_text, inline=False)

            # 여행 관리
            travel_text = (
                "✈️ **`/여행관리 기능:여행추가`** - 여행을 수동으로 추가합니다\n"
                "✈️ **`/여행관리 기능:여행종료`** - 진행 중인 여행을 종료합니다\n"
                "✈️ **`/여행관리 기능:여행리스트`** - 여행 목록을 확인합니다\n"
                "✈️ **`/여행관리 기능:여행로그`** - 여행 로그를 확인합니다\n"
                "✈️ **`/여행관리 기능:채널`** - 여행 알림 채널을 설정합니다\n"
                "✈️ **`/여행관리 기능:역할`** - 여행 역할을 설정합니다\n"
                "✈️ **`/여행관리 기능:현황`** - 여행 시스템 현황을 확인합니다"
            )
            embed3.add_field(name="✈️ 여행 관리", value=travel_text, inline=False)

            embeds.append(embed3)

            # 페이지 4: 시스템 / &MF 명령어
            embed4 = discord.Embed(
                title="🛠️ 관리자 명령어 (3/3)",
                color=0x2f3136
            )

            # 시스템 관리
            system_text = (
                "🗄️ **`/데이터베이스`** - 데이터베이스 조회 및 관리\n"
                "📜 **`/로그조회`** - 시스템 로그를 조회합니다\n"
                "📜 **`/로그관리`** - 로그 시스템을 관리합니다"
            )
            embed4.add_field(name="🗄️ 시스템 관리", value=system_text, inline=False)

            # &MF 명령어
            mf_text = (
                "```\n"
                "&MF {연동} <디스코드ID> <MC닉네임>\n"
                "```\n"
                "Mojang API로 UUID를 조회하여 DB에 저장합니다.\n"
                "연동된 유저는 대기열 처리 시 API 조회를 건너뜁니다.\n\n"

                "```\n"
                "&MF {대기열} <디스코드ID>\n"
                "```\n"
                "유저를 대기열에 추가합니다.\n\n"

                "```\n"
                "&MF <디스코드ID 또는 @멘션>\n"
                "```\n"
                "현재 채널 이름을 해당 유저의 국가 대사관 형식으로 변경합니다.\n\n"

                "```\n"
                "&MF {채널_이름} [형식] <디스코드ID>\n"
                "```\n"
                "사용자 정의 형식으로 채널 이름을 변경합니다.\n"
                "플레이스홀더: `{CC}` 콜사인 / `{NN}` 국가 / `{TT}` 마을 / `{MC}` MC닉네임"
            )
            embed4.add_field(name="💬 &MF 메시지 명령어", value=mf_text, inline=False)

            embeds.append(embed4)

        else:
            embed1.add_field(
                name="🛡️ 관리자 전용 명령어",
                value="🔒 관리자 권한이 필요한 명령어가 추가로 있습니다.",
                inline=False
            )

        # ===== 봇 상태 (마지막 임베드에 추가) =====
        last_embed = embeds[-1]

        queue_size = queue_manager.get_queue_size()
        is_processing = queue_manager.is_processing()
        processing_status = "🔄 처리 중" if is_processing else "⏸️ 대기 중"

        try:
            alliance_data = load_alliance_data()
            alliance_count = len(alliance_data["alliances"])
        except:
            alliance_count = 0

        status_text = (
            f"🌐 **API**: {'🟢 연결됨' if MC_API_BASE else '🔴 설정 필요'}\n"
            f"🏴 **기본 국가**: {BASE_NATION}\n"
            f"🤝 **동맹**: {alliance_count}개\n"
            f"🏘️ **마을 역할**: {'🟢' if TOWN_ROLE_ENABLED else '🔴'}\n"
            f"🏷️ **콜사인**: {'🟢' if CALLSIGN_ENABLED else '🔴'}\n"
            f"📋 **대기열**: {queue_size}명 ({processing_status})"
        )

        last_embed.add_field(name="📊 봇 상태", value=status_text, inline=False)

        # 푸터
        total_commands = len(bot.tree.get_commands())
        last_embed.set_footer(
            text=f"🤖 {bot.user.name} • 총 {total_commands}개 명령어 • 권한: {'관리자' if is_admin else '일반 사용자'}",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        last_embed.timestamp = datetime.datetime.now()

        await interaction.response.send_message(embeds=embeds, ephemeral=True)
