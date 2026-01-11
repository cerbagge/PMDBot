# commands/admin/system/log_manage.py
# /로그관리 명령어 - 로그 시스템 관리

import discord
from discord import app_commands
from typing import Optional, Literal
import datetime
from datetime import timedelta
import os
import shutil

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


# 로그 정리 확인을 위한 View 클래스
class LogCleanupConfirmView(discord.ui.View):
    def __init__(self, days_to_keep: int, user_id: int):
        super().__init__(timeout=60)
        self.days_to_keep = days_to_keep
        self.user_id = user_id

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.danger)
    async def confirm_cleanup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 이 버튼을 사용할 권한이 없습니다.", ephemeral=True)
            return

        try:
            from log_manager import log_manager, bot_logger

            # 정리 전 파일 개수 확인
            log_dir = log_manager.log_dir
            old_files = []
            cutoff_date = datetime.datetime.now() - timedelta(days=self.days_to_keep)

            for filename in os.listdir(log_dir):
                if filename.startswith(('bot_', 'logs_')) and filename.endswith(('.log', '.json')):
                    try:
                        if filename.startswith('bot_'):
                            date_part = filename[4:14]
                        else:
                            date_part = filename[5:15]

                        file_date = datetime.datetime.strptime(date_part, '%Y-%m-%d')
                        if file_date < cutoff_date:
                            old_files.append(filename)
                    except:
                        continue

            # 정리 실행
            log_manager.cleanup_old_logs(self.days_to_keep)

            embed = discord.Embed(
                title="🧹 로그 정리 완료",
                description=f"**삭제된 파일:** {len(old_files)}개\n"
                        f"**보관 기간:** {self.days_to_keep}일\n"
                        f"**기준 날짜:** {cutoff_date.strftime('%Y-%m-%d')} 이전",
                color=0x00ff00
            )

            if old_files:
                files_list = "\n".join([f"• {f}" for f in old_files[:10]])
                if len(old_files) > 10:
                    files_list += f"\n... 외 {len(old_files) - 10}개"

                embed.add_field(
                    name="🗑️ 삭제된 파일 목록",
                    value=files_list,
                    inline=False
                )

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            embed.timestamp = datetime.datetime.now()

            # 버튼 비활성화
            self.clear_items()
            await interaction.response.edit_message(embed=embed, view=self)

            # 로그 기록
            bot_logger.log_system_event(
                f"로그 정리 실행: {len(old_files)}개 파일 삭제",
                details=f"보관기간: {self.days_to_keep}일, 처리자: {interaction.user.name}"
            )

        except Exception as e:
            embed = discord.Embed(
                title="❌ 로그 정리 실패",
                description=f"오류가 발생했습니다: {str(e)}",
                color=0xff0000
            )
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.secondary)
    async def cancel_cleanup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ 이 버튼을 사용할 권한이 없습니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="❌ 로그 정리 취소",
            description="로그 정리가 취소되었습니다.",
            color=0x6c757d
        )

        self.clear_items()
        await interaction.response.edit_message(embed=embed, view=self)


def setup(bot):
    """봇에 /로그관리 명령어 등록"""

    @bot.tree.command(name="로그관리", description="로그 시스템 관리 기능")
    @app_commands.describe(
        기능="수행할 관리 기능",
        날짜="시작 날짜 (YYYY-MM-DD)",
        종료날짜="종료 날짜 (YYYY-MM-DD)",
        보관기간="로그 보관 기간 (일)"
    )
    @app_commands.check(is_admin)
    async def 로그관리(
        interaction: discord.Interaction,
        기능: Literal["통계", "정리", "내보내기", "백업"],
        날짜: Optional[str] = None,
        종료날짜: Optional[str] = None,
        보관기간: Optional[int] = None
    ):
        """로그 관리 명령어"""

        # log_manager 모듈 확인
        try:
            from log_manager import log_manager, bot_logger
        except ImportError:
            embed = discord.Embed(
                title="❌ 로그 시스템 비활성화",
                description="로그 관리 시스템(log_manager.py)이 설치되지 않았습니다.\n\n"
                           "이 기능을 사용하려면 log_manager.py 모듈이 필요합니다.",
                color=0xff0000
            )
            embed.add_field(
                name="💡 안내",
                value="로그 시스템은 선택적 기능입니다.\n"
                      "다른 관리 명령어들은 정상적으로 사용 가능합니다.",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await interaction.response.defer()

            if 기능 == "통계":
                # 로그 통계 정보 표시
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                yesterday = (datetime.datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

                today_logs = log_manager.get_logs_by_date(today)
                yesterday_logs = log_manager.get_logs_by_date(yesterday)

                # 카테고리별 통계
                today_stats = {}
                yesterday_stats = {}

                for log in today_logs:
                    category = log['category']
                    today_stats[category] = today_stats.get(category, 0) + 1

                for log in yesterday_logs:
                    category = log['category']
                    yesterday_stats[category] = yesterday_stats.get(category, 0) + 1

                embed = discord.Embed(
                    title="📊 로그 시스템 통계",
                    color=0x00AE86
                )

                embed.add_field(
                    name="📈 전체 통계",
                    value=f"**오늘:** {len(today_logs)}개 로그\n"
                        f"**어제:** {len(yesterday_logs)}개 로그\n"
                        f"**메모리:** {len(log_manager.recent_logs)}개 (최근)",
                    inline=False
                )

                # 오늘 카테고리별 통계
                if today_stats:
                    today_text = ""
                    for category, count in sorted(today_stats.items()):
                        today_text += f"• {category}: {count}개\n"

                    embed.add_field(
                        name="📅 오늘 카테고리별",
                        value=today_text,
                        inline=True
                    )

                # 어제 카테고리별 통계
                if yesterday_stats:
                    yesterday_text = ""
                    for category, count in sorted(yesterday_stats.items()):
                        yesterday_text += f"• {category}: {count}개\n"

                    embed.add_field(
                        name="📅 어제 카테고리별",
                        value=yesterday_text,
                        inline=True
                    )

                embed.set_footer(text=f"조회자: {interaction.user.name}")
                embed.timestamp = datetime.datetime.now()

                await interaction.followup.send(embed=embed, ephemeral=True)

            elif 기능 == "정리":
                # 오래된 로그 파일 정리
                days_to_keep = 보관기간 or 30

                embed = discord.Embed(
                    title="🧹 로그 정리 확인",
                    description=f"**{days_to_keep}일** 이전의 로그 파일을 삭제하시겠습니까?\n"
                            f"이 작업은 되돌릴 수 없습니다.",
                    color=0xff6600
                )

                view = LogCleanupConfirmView(days_to_keep, interaction.user.id)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)

            elif 기능 == "내보내기":
                # 로그 내보내기
                if not 날짜 or not 종료날짜:
                    await interaction.followup.send(
                        "내보내기 기능을 사용하려면 시작 날짜와 종료 날짜를 모두 입력해주세요.\n"
                        "예: `/로그관리 기능:내보내기 날짜:2024-01-01 종료날짜:2024-01-31`",
                        ephemeral=True
                    )
                    return

                try:
                    datetime.datetime.strptime(날짜, '%Y-%m-%d')
                    datetime.datetime.strptime(종료날짜, '%Y-%m-%d')
                except ValueError:
                    await interaction.followup.send("올바른 날짜 형식을 입력해주세요. (YYYY-MM-DD)", ephemeral=True)
                    return

                export_path = log_manager.export_logs(날짜, 종료날짜, 'json')

                if export_path:
                    embed = discord.Embed(
                        title="📦 로그 내보내기 완료",
                        description=f"**기간:** {날짜} ~ {종료날짜}\n"
                                f"**파일:** `{os.path.basename(export_path)}`\n"
                                f"**경로:** `{export_path}`",
                        color=0x00ff00
                    )

                    # 파일 크기 확인
                    try:
                        file_size = os.path.getsize(export_path)
                        size_mb = file_size / (1024 * 1024)
                        embed.add_field(
                            name="📁 파일 정보",
                            value=f"크기: {size_mb:.2f} MB",
                            inline=False
                        )
                    except:
                        pass

                    embed.set_footer(text=f"처리자: {interaction.user.name}")
                    embed.timestamp = datetime.datetime.now()

                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 로그 내보내기에 실패했습니다.", ephemeral=True)

            elif 기능 == "백업":
                # 현재 로그 백업
                today = datetime.datetime.now().strftime('%Y-%m-%d')
                backup_path = log_manager.export_logs(today, today, 'json')

                if backup_path:
                    # 백업 디렉토리로 이동
                    backup_dir = os.path.join(log_manager.log_dir, "backups")
                    if not os.path.exists(backup_dir):
                        os.makedirs(backup_dir)

                    backup_filename = f"backup_{today}_{datetime.datetime.now().strftime('%H%M%S')}.json"
                    final_backup_path = os.path.join(backup_dir, backup_filename)

                    shutil.move(backup_path, final_backup_path)

                    embed = discord.Embed(
                        title="💾 로그 백업 완료",
                        description=f"**날짜:** {today}\n"
                                f"**파일:** `{backup_filename}`\n"
                                f"**경로:** `{final_backup_path}`",
                        color=0x00ff00
                    )
                    embed.set_footer(text=f"처리자: {interaction.user.name}")
                    embed.timestamp = datetime.datetime.now()

                    await interaction.followup.send(embed=embed, ephemeral=True)

                    # 로그 기록
                    bot_logger.log_system_event(f"로그 백업 생성: {backup_filename}")
                else:
                    await interaction.followup.send("❌ 로그 백업에 실패했습니다.", ephemeral=True)

            # 작업 로그 기록
            bot_logger.log_system_event(
                f"로그 관리 작업 실행: {기능}",
                details=f"사용자: {interaction.user.name}, 날짜: {날짜}, 종료날짜: {종료날짜}"
            )

        except ImportError:
            await interaction.followup.send("❌ 로그 관리 시스템이 로드되지 않았습니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 로그 관리 중 오류가 발생했습니다: {str(e)}", ephemeral=True)

    # 에러 핸들러
    @로그관리.error
    async def 로그관리_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
