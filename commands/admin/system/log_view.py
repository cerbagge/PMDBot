# commands/admin/system/log_view.py
# /로그조회 명령어 - 시스템 로그 조회

import discord
from discord import app_commands
from typing import Optional, Literal
import datetime
from datetime import timedelta

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


# 페이지네이션을 위한 View 클래스
class LogPaginationView(discord.ui.View):
    def __init__(self, logs: list, page_size: int, user_id: int):
        super().__init__(timeout=300)
        self.logs = logs
        self.page_size = page_size
        self.user_id = user_id
        self.current_page = 1
        self.total_pages = (len(logs) + page_size - 1) // page_size

        # 페이지가 1개면 버튼 비활성화
        if self.total_pages <= 1:
            self.clear_items()

    def create_embed(self, page: int):
        start_idx = (page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_logs = self.logs[start_idx:end_idx]

        embed = discord.Embed(
            title="📋 로그 조회 결과",
            description=f"총 {len(self.logs)}개 로그 중 {start_idx + 1}-{min(end_idx, len(self.logs))}번째",
            color=0x00AE86
        )

        for i, log in enumerate(page_logs, start_idx + 1):
            level_emoji = {
                "INFO": "ℹ️",
                "WARNING": "⚠️",
                "ERROR": "❌",
                "ADMIN": "🔧",
                "AUTO": "🤖",
                "SYSTEM": "⚙️"
            }

            emoji = level_emoji.get(log['level'], "📝")
            # source/action 정보 표시
            source_label = f" [{log.get('source', '')}]" if log.get('source') else ""
            field_name = f"{emoji} {log['time']} | {log['category']}{source_label}"

            field_value = f"**{log['message']}**\n"
            if log.get('user_name'):
                field_value += f"👤 {log['user_name']}"
                if log.get('command'):
                    field_value += f" | 🔸 /{log['command']}"
            if log.get('target_user_name'):
                field_value += f"\n🎯 대상: {log['target_user_name']}"
            if log.get('action'):
                field_value += f"\n📌 액션: {log['action']}"

            embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
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
    """봇에 /로그조회 명령어 등록"""

    @bot.tree.command(name="로그조회", description="시스템 로그를 조회합니다")
    @app_commands.describe(
        범위="조회할 로그 범위",
        카테고리="로그 카테고리 필터",
        출처="로그 발생 위치 필터",
        사용자="특정 사용자의 로그만 조회",
        날짜="특정 날짜 (YYYY-MM-DD 형식)"
    )
    @app_commands.check(is_admin)
    async def 로그조회(
        interaction: discord.Interaction,
        범위: Literal["최근", "오늘", "어제", "특정날짜", "사용자활동", "대기열감사", "명령어내역"] = "최근",
        카테고리: Optional[Literal[
            "콜사인", "대기열", "동맹", "역할", "예외처리", "스케줄러", "시스템", "관리자",
            "대기열추가", "대기열처리", "복귀", "경고", "여행", "공지", "명령어"
        ]] = None,
        출처: Optional[Literal["admin_command", "user_command", "scheduler", "event_handler", "mf_handler", "system"]] = None,
        사용자: Optional[discord.User] = None,
        날짜: Optional[str] = None
    ):
        """로그 조회 명령어"""

        # log_manager 모듈 확인
        try:
            from log_manager import log_manager, LogCategory
        except ImportError:
            embed = discord.Embed(
                title="❌ 로그 시스템 비활성화",
                description="로그 관리 시스템(log_manager.py)이 설치되지 않았습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await interaction.response.defer()

            try:
                from log_manager import bot_logger as _bot_logger
                if _bot_logger:
                    _bot_logger.log_command("로그조회", interaction.user.id, interaction.user.name,
                                           source="admin_command", category=LogCategory.COMMAND,
                                           details={"범위": 범위, "카테고리": 카테고리, "출처": 출처})
            except ImportError:
                pass

            # 카테고리 매핑 (기존 + 신규)
            category_map = {
                "콜사인": LogCategory.CALLSIGN,
                "대기열": LogCategory.QUEUE,
                "동맹": LogCategory.ALLIANCE,
                "역할": LogCategory.ROLE,
                "예외처리": LogCategory.EXCEPTION,
                "스케줄러": LogCategory.SCHEDULER,
                "시스템": LogCategory.SYSTEM,
                "관리자": LogCategory.ADMIN,
                "대기열추가": LogCategory.QUEUE_ADD,
                "대기열처리": LogCategory.QUEUE_PROCESS,
                "복귀": LogCategory.RETURN,
                "경고": LogCategory.WARNING_SYS,
                "여행": LogCategory.TRAVEL,
                "공지": LogCategory.ANNOUNCEMENT,
                "명령어": LogCategory.COMMAND,
            }

            selected_category = category_map.get(카테고리) if 카테고리 else None

            # 로그 조회
            if 범위 == "대기열감사":
                # 대기열 감사 전용 — WHO/WHEN/WHY 추적
                logs = log_manager.get_logs_by_filter(
                    category=LogCategory.QUEUE_ADD,
                    source=출처,
                    days=7, limit=100
                )
            elif 범위 == "명령어내역":
                # 명령어 사용 내역 전용
                logs = log_manager.get_logs_by_filter(
                    category=LogCategory.COMMAND,
                    source=출처,
                    days=7, limit=100
                )
            elif 범위 == "최근":
                if 출처:
                    logs = log_manager.get_logs_by_filter(
                        source=출처, category=selected_category,
                        days=7, limit=50
                    )
                else:
                    logs = log_manager.get_recent_logs(count=50, category=selected_category)
            elif 범위 == "오늘":
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                logs = log_manager.get_logs_by_date(today, category=selected_category)
                if 출처:
                    logs = [l for l in logs if l.get('source') == 출처]
            elif 범위 == "어제":
                yesterday = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                logs = log_manager.get_logs_by_date(yesterday, category=selected_category)
                if 출처:
                    logs = [l for l in logs if l.get('source') == 출처]
            elif 범위 == "특정날짜":
                if not 날짜:
                    await interaction.followup.send("특정날짜를 선택한 경우 날짜를 입력해주세요. (예: 2024-01-15)", ephemeral=True)
                    return
                try:
                    datetime.datetime.strptime(날짜, '%Y-%m-%d')
                    logs = log_manager.get_logs_by_date(날짜, category=selected_category)
                    if 출처:
                        logs = [l for l in logs if l.get('source') == 출처]
                except ValueError:
                    await interaction.followup.send("올바른 날짜 형식을 입력해주세요. (YYYY-MM-DD)", ephemeral=True)
                    return
            elif 범위 == "사용자활동":
                if not 사용자:
                    await interaction.followup.send("사용자활동을 선택한 경우 사용자를 지정해주세요.", ephemeral=True)
                    return
                logs = log_manager.get_user_logs(사용자.id, days=7)
                if selected_category:
                    logs = [log for log in logs if log['category'] == selected_category.value]
                if 출처:
                    logs = [l for l in logs if l.get('source') == 출처]

            if not logs:
                embed = discord.Embed(
                    title="📋 로그 조회 결과",
                    description="조회 조건에 맞는 로그가 없습니다.",
                    color=0x2f3136
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # 결과를 페이지별로 나누기 (페이지당 10개)
            page_size = 10
            total_pages = (len(logs) + page_size - 1) // page_size

            # 페이지 네비게이션 View 생성
            view = LogPaginationView(logs, page_size, interaction.user.id)
            embed = view.create_embed(1)

            if total_pages > 1:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

        except ImportError:
            await interaction.followup.send("❌ 로그 관리 시스템이 로드되지 않았습니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 로그 조회 중 오류가 발생했습니다: {str(e)}", ephemeral=True)

    # 에러 핸들러
    @로그조회.error
    async def 로그조회_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
