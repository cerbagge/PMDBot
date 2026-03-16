# commands/admin/queue/server_queue.py
# /서버대기열 명령어 - 서버 접속 대기열 인원을 확인

import discord
from discord import app_commands
import aiohttp
import asyncio
import json
import datetime

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


# ========== 서버 대기열 확인 기능 ==========
class ServerQueueChecker:
    """마인크래프트 서버 대기열 확인 클래스"""

    def __init__(self, mc_host: str, mc_port: int, dynmap_url: str):
        self.mc_host = mc_host
        self.mc_port = mc_port
        self.dynmap_url = dynmap_url.rstrip('/')

    async def _fetch_mc_status(self, session):
        """마인크래프트 서버 상태 조회 (공유 세션 사용)"""
        try:
            api_url = f"https://mcapi.us/server/status?ip={self.mc_host}"
            headers = {'User-Agent': 'Discord-Bot-PlanetEarth/1.0'}
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('online'):
                        player_count = data.get('players', {}).get('now', 0)
                        print(f"✅ 서버 온라인: {player_count}명 (mcapi.us)")
                        return data
            return None
        except Exception as e:
            print(f"❌ MC 서버 조회 실패: {e}")
            return None

    async def _fetch_dynmap_data(self, session, world: str = "world"):
        """Dynmap 데이터 조회 (공유 세션 사용, 1회 호출로 전체+로비 모두 반환)"""
        try:
            dynmap_api_url = f"{self.dynmap_url}/up/world/{world}/"
            async with session.get(dynmap_api_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    text = await response.text()
                    data = json.loads(text)
                    players = data.get('players', [])
                    total_count = len(players)
                    lobby_players = [p for p in players if p.get('world') == '-some-other-bogus-world-']
                    lobby_count = len(lobby_players)
                    print(f"  ✅ Dynmap: 전체 {total_count}명, 로비 {lobby_count}명")
                    return total_count, lobby_count
            return -1, -1
        except Exception as e:
            print(f"❌ Dynmap 조회 실패: {e}")
            return -1, -1

    async def get_minecraft_status(self):
        """마인크래프트 서버 상태 조회 (하위 호환)"""
        async with aiohttp.ClientSession() as session:
            return await self._fetch_mc_status(session)

    async def get_mc_player_count(self):
        """마인크래프트 서버 전체 플레이어 수"""
        status = await self.get_minecraft_status()
        if not status:
            return -1
        return status.get('players', {}).get('now', 0)

    async def get_dynmap_players(self, world: str = "world"):
        """Dynmap 전체 플레이어 수 (하위 호환)"""
        async with aiohttp.ClientSession() as session:
            total, _ = await self._fetch_dynmap_data(session, world)
            return total

    async def get_dynmap_lobby_players(self, world: str = "world"):
        """Dynmap 로비 플레이어 수 (하위 호환)"""
        async with aiohttp.ClientSession() as session:
            _, lobby = await self._fetch_dynmap_data(session, world)
            return lobby

    async def get_queue_info(self):
        """대기열 정보 계산 - MC + Dynmap 병렬 호출"""
        async with aiohttp.ClientSession() as session:
            # MC 상태와 Dynmap을 동시에 호출 (병렬)
            mc_task = self._fetch_mc_status(session)
            dynmap_task = self._fetch_dynmap_data(session)
            mc_status, (dynmap_ingame, _) = await asyncio.gather(mc_task, dynmap_task)

        mc_total = -1
        if mc_status:
            mc_total = mc_status.get('players', {}).get('now', 0)

        # MC 서버 연결 실패했지만 Dynmap은 성공한 경우
        if mc_total == -1 and dynmap_ingame != -1:
            print(f"ℹ️ MC 서버 연결 실패, Dynmap 데이터만 사용: {dynmap_ingame}명")
            return (-1, dynmap_ingame, dynmap_ingame, 0)

        # 둘 다 실패한 경우
        if mc_total == -1 or dynmap_ingame == -1:
            return (-1, -1, -1, -1)

        # 대기열 계산
        queue_count = max(0, mc_total - dynmap_ingame)
        print(f"ℹ️ 대기열 계산: {mc_total} - {dynmap_ingame} = {queue_count}명")

        return (mc_total, dynmap_ingame, dynmap_ingame, queue_count)


def setup(bot):
    """봇에 /서버대기열 명령어 등록"""

    @bot.tree.command(name="서버대기열", description="서버 접속 대기열 인원을 확인합니다")
    async def 서버대기열(interaction: discord.Interaction):
        """서버 대기열 확인 슬래시 커맨드"""
        await interaction.response.defer()

        if bot_logger:
            bot_logger.log_command("서버대기열", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.COMMAND)

        try:
            # ServerQueueChecker 인스턴스 생성
            checker = ServerQueueChecker(
                mc_host="planetearth.kr",
                mc_port=25565,
                dynmap_url="https://map.planetearth.kr"
            )

            api_total, dynmap_total, ingame, queue = await checker.get_queue_info()

            if api_total == -1 and dynmap_total == -1:
                embed = discord.Embed(
                    title="❌ 서버 오류",
                    description="서버 상태를 확인할 수 없습니다.",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now()
                )
                await interaction.followup.send(embed=embed)
                return

            # 대기열 상태에 따른 색상
            if queue == 0:
                color = discord.Color.green()
                status_emoji = "✅"
                status_text = "대기열 없음 - 바로 입장 가능!"
            elif queue < 10:
                color = discord.Color.yellow()
                status_emoji = "⏳"
                status_text = f"{queue}명이 입장 대기 중"
            else:
                color = discord.Color.red()
                status_emoji = "⚠️"
                status_text = f"{queue}명이 입장 대기 중 - 대기 시간이 길 수 있습니다"

            embed = discord.Embed(
                title="🌍 PlanetEarth 서버 대기열",
                description=f"{status_emoji} **{status_text}**",
                color=color,
                timestamp=datetime.datetime.now()
            )

            # 서버 정보 - API와 Dynmap 수치 모두 표시
            if api_total != -1:
                embed.add_field(
                    name="📊 서버 연결 인원 (API)",
                    value=f"**{api_total}명**",
                    inline=True
                )

            embed.add_field(
                name="🗺️ Dynmap 플레이어",
                value=f"**{dynmap_total}명**",
                inline=True
            )

            embed.add_field(
                name="⏳ 예상대기열",
                value=f"**{queue}명**",
                inline=True
            )

            # 진행 바 표시 (Dynmap 기준)
            if dynmap_total > 0:
                # API 데이터가 있으면 API 기준으로, 없으면 Dynmap 기준으로
                total_for_bar = api_total if api_total != -1 else dynmap_total

                if total_for_bar > 0:
                    ingame_percent = int((ingame / total_for_bar) * 100)
                    queue_percent = int((queue / total_for_bar) * 100)

                    # 간단한 진행 바
                    bar_length = 20
                    ingame_blocks = int((ingame / total_for_bar) * bar_length)
                    queue_blocks = bar_length - ingame_blocks

                    progress_bar = "🟩" * ingame_blocks + "🟨" * queue_blocks

                    embed.add_field(
                        name="📈 비율",
                        value=f"{progress_bar}\n게임 내: {ingame_percent}% | 예상대기: {queue_percent}%",
                        inline=False
                    )

            embed.set_footer(text="서버: planetearth.kr")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="❌ 오류",
                description=f"대기열 정보를 가져오는 중 오류가 발생했습니다:\n```{str(e)[:100]}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
