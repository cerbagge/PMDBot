# commands/admin/callsigns/callsign_setting.py
# /콜사인설정 명령어 - 콜사인 설정 관리 (관리자 전용)

import discord
from discord import app_commands
from typing import Literal
import os
import json
import datetime
import asyncio

# 안전한 import 처리
try:
    from callsign_manager import callsign_manager
    CALLSIGN_ENABLED = True
except ImportError:
    callsign_manager = None
    CALLSIGN_ENABLED = False

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None


# 관리자 권한 체크 함수
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


def setup(bot):
    """봇에 /콜사인설정 명령어 등록"""

    @bot.tree.command(name="콜사인설정", description="콜사인 역할 양식 및 백업 설정을 관리합니다")
    @app_commands.describe(
        기능="실행할 기능 선택",
        역할="역할 양식 설정 대상 역할",
        텍스트="양식 텍스트 또는 백업 파일명"
    )
    @app_commands.check(is_admin)
    async def 콜사인설정(
        interaction: discord.Interaction,
        기능: Literal["역할_양식", "역할_양식_목록", "역할_양식_제거", "데이터_백업", "백업_목록", "데이터_복구", "백업파일_업로드"],
        역할: discord.Role = None,
        텍스트: str = None
    ):
        """콜사인 설정 관리 - 관리자 전용"""

        if not CALLSIGN_ENABLED:
            embed = discord.Embed(
                title="⌛ 기능 비활성화",
                description="콜사인 기능이 비활성화되어 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed)
            return

        if 기능 == "역할_양식":
            if not 역할:
                await interaction.response.send_message("역할을 지정해주세요.", ephemeral=True)
                return

            if not 텍스트:
                await interaction.response.send_message("양식 텍스트를 입력해주세요.", ephemeral=True)
                return

            success, message = callsign_manager.set_role_format(역할.id, 텍스트)

            embed = discord.Embed(
                title="🎭 역할 닉네임 양식 설정" if success else "❌ 양식 설정 실패",
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                embed.add_field(
                    name="🎯 대상 역할",
                    value=f"{역할.mention} (`{역할.name}`)",
                    inline=False
                )
                embed.add_field(
                    name="📝 설정된 양식",
                    value=f"`{텍스트}`",
                    inline=False
                )
                embed.add_field(
                    name="📚 사용 가능한 변수",
                    value="• `{MF}` 또는 `{MC}` - 마인크래프트 닉네임 (없으면 ❌)\n"
                          "• `{NN}` - PlanetEarth 국가 이름 (없으면 ❌)\n"
                          "• `{TT}` - PlanetEarth 마을 이름 (없으면 ❌)\n"
                          "• `{CC}` - 콜사인 (없으면 빈 값)\n"
                          "• `{NN/TT}` - 국가가 있으면 국가, 없으면 `[ T ] 마을` (둘 다 없으면 ❌)",
                    inline=False
                )

                example = callsign_manager.apply_format_to_nickname(
                    텍스트,
                    mc_id="Steve",
                    nation="Korea",
                    town="Seoul",
                    callsign="Leader"
                )
                embed.add_field(
                    name="💡 예시",
                    value=f"`{example}`",
                    inline=False
                )

                embed.add_field(
                    name="ℹ️ 안내",
                    value=f"• 이 역할을 가진 사용자가 콜사인을 설정하면 자동으로 이 양식이 적용됩니다.\n"
                          f"• 여러 역할을 가진 경우 **가장 우선순위가 높은 역할**의 양식이 적용됩니다.\n"
                          f"• 역할 우선순위는 Discord 서버 설정에서 확인할 수 있습니다.",
                    inline=False
                )
            else:
                embed.description = message

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)

        elif 기능 == "역할_양식_목록":
            all_formats = callsign_manager.get_all_role_formats()

            if not all_formats:
                embed = discord.Embed(
                    title="📋 역할 닉네임 양식 목록",
                    description="설정된 역할 양식이 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📋 역할 닉네임 양식 목록",
                    description=f"총 {len(all_formats)}개의 역할 양식이 설정되어 있습니다.",
                    color=0x00bfff
                )

                for i, (role_id, format_data) in enumerate(list(all_formats.items())[:15], 1):
                    try:
                        role = interaction.guild.get_role(int(role_id))
                        role_name = role.name if role else f"Unknown Role ({role_id})"
                        role_mention = role.mention if role else f"<삭제된 역할>"
                    except:
                        role_name = f"Unknown ({role_id})"
                        role_mention = f"<삭제된 역할>"

                    format_string = format_data.get("format", "알 수 없음")
                    set_date = "알 수 없음"
                    if "set_at" in format_data:
                        set_date = format_data["set_at"][:10]

                    embed.add_field(
                        name=f"{i}. {role_name}",
                        value=f"**역할:** {role_mention}\n"
                              f"**양식:** `{format_string}`\n"
                              f"**설정일:** {set_date}",
                        inline=False
                    )

                if len(all_formats) > 15:
                    embed.set_footer(text=f"... 외 {len(all_formats) - 15}개")

            await interaction.response.send_message(embed=embed)

        elif 기능 == "역할_양식_제거":
            if not 역할:
                await interaction.response.send_message("제거할 역할을 지정해주세요.", ephemeral=True)
                return

            success, message = callsign_manager.remove_role_format(역할.id)

            embed = discord.Embed(
                title="🗑️ 역할 양식 제거" if success else "⚠️ 양식 제거 실패",
                description=f"**대상 역할:** {역할.mention}\n\n{message}",
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                embed.add_field(
                    name="ℹ️ 안내",
                    value=f"• 이제 이 역할을 가진 사용자는 기본 양식으로 닉네임이 설정됩니다.\n"
                          f"• 기존 사용자의 닉네임은 변경되지 않습니다.",
                    inline=False
                )

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.response.send_message(embed=embed)

        elif 기능 == "데이터_백업":
            await interaction.response.defer()

            if bot_logger:
                bot_logger.log_command("콜사인설정", interaction.user.id, interaction.user.name,
                                       source="admin_command", category=LogCategory.CALLSIGN,
                                       details={"기능": 기능})

            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.followup.send(embed=embed)
                    return

            success, result = backup_manager.create_backup("manual")

            embed = discord.Embed(
                title="💾 수동 백업" if success else "❌ 백업 실패",
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                backup_file = os.path.basename(result)
                file_size = os.path.getsize(result) / 1024

                embed.add_field(
                    name="✅ 백업 완료",
                    value=f"**파일명:** `{backup_file}`\n"
                          f"**크기:** {file_size:.2f} KB\n"
                          f"**경로:** `{result}`",
                    inline=False
                )

                with open(result, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    callsign_count = len(data.get("data", data))

                embed.add_field(
                    name="📊 백업 통계",
                    value=f"**저장된 콜사인:** {callsign_count}개\n"
                          f"**백업 시간:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    inline=False
                )

                try:
                    discord_file = discord.File(result, filename=backup_file)
                    embed.add_field(
                        name="📎 첨부 파일",
                        value="백업 파일이 이 메시지에 첨부되었습니다.",
                        inline=False
                    )
                    embed.set_footer(text=f"처리자: {interaction.user.name}")
                    await interaction.followup.send(embed=embed, file=discord_file)
                    return
                except Exception as e:
                    print(f"⚠️ 백업 파일 업로드 실패: {e}")
                    embed.add_field(
                        name="⚠️ 파일 업로드 실패",
                        value=f"파일은 서버에 저장되었으나 Discord 업로드에 실패했습니다.\n오류: {str(e)[:100]}",
                        inline=False
                    )
            else:
                embed.description = result

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.followup.send(embed=embed)

        elif 기능 == "백업_목록":
            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed)
                    return

            backups = backup_manager.list_backups(15)

            if not backups:
                embed = discord.Embed(
                    title="📁 백업 목록",
                    description="저장된 백업이 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📁 백업 목록",
                    description=f"총 {len(backups)}개의 백업이 있습니다.",
                    color=0x00bfff
                )

                for i, backup in enumerate(backups[:10], 1):
                    backup_type = "🔄 자동" if backup["type"] == "auto" else "👤 수동" if backup["type"] == "manual" else "📤 업로드"

                    embed.add_field(
                        name=f"{i}. {backup_type} 백업",
                        value=f"**파일:** `{backup['filename']}`\n"
                              f"**시간:** {backup['created'].strftime('%Y-%m-%d %H:%M')}\n"
                              f"**크기:** {backup['size_kb']} KB | **콜사인:** {backup['callsign_count']}개",
                        inline=False
                    )

                if len(backups) > 10:
                    embed.set_footer(text=f"... 외 {len(backups) - 10}개 백업")

            await interaction.response.send_message(embed=embed)

        elif 기능 == "데이터_복구":
            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed)
                    return

            if not 텍스트:
                backups = backup_manager.list_backups(5)

                if not backups:
                    await interaction.response.send_message("저장된 백업이 없습니다.")
                    return

                embed = discord.Embed(
                    title="🔄 백업 복구",
                    description="복구할 백업 파일명을 `텍스트` 매개변수에 입력해주세요.\n\n**최근 백업 목록:**",
                    color=0xffff00
                )

                for backup in backups:
                    embed.add_field(
                        name=backup['filename'],
                        value=f"생성: {backup['created'].strftime('%Y-%m-%d %H:%M')} | 콜사인: {backup['callsign_count']}개",
                        inline=False
                    )

                await interaction.response.send_message(embed=embed)
                return

            await interaction.response.defer()

            if bot_logger:
                bot_logger.log_command("콜사인설정", interaction.user.id, interaction.user.name,
                                       source="admin_command", category=LogCategory.CALLSIGN,
                                       details={"기능": 기능})

            backup_path = os.path.join(backup_manager.backup_dir, 텍스트)
            success, message = backup_manager.restore_backup(backup_path)

            embed = discord.Embed(
                title="✅ 복구 완료" if success else "❌ 복구 실패",
                description=message,
                color=0x00ff00 if success else 0xff0000
            )

            if success:
                embed.add_field(
                    name="⚠️ 주의사항",
                    value="기존 데이터는 `.pre_restore_` 파일로 백업되었습니다.\n"
                          "복구 후 문제가 있다면 해당 파일로 재복구 가능합니다.",
                    inline=False
                )

            embed.set_footer(text=f"처리자: {interaction.user.name}")
            await interaction.followup.send(embed=embed)

        elif 기능 == "백업파일_업로드":
            backup_manager = None
            if hasattr(bot, 'backup_manager'):
                backup_manager = bot.backup_manager
            else:
                try:
                    from callsign_backup import CallsignBackupManager
                    backup_manager = CallsignBackupManager()
                except ImportError:
                    embed = discord.Embed(
                        title="❌ 백업 기능 비활성화",
                        description="callsign_backup.py 모듈을 찾을 수 없습니다.",
                        color=0xff0000
                    )
                    await interaction.response.send_message(embed=embed)
                    return

            embed = discord.Embed(
                title="📤 백업 파일 업로드",
                description="백업 파일을 업로드하려면 다음 단계를 따라주세요:\n\n"
                           "1. 이 메시지에 답장으로 백업 JSON 파일을 첨부\n"
                           "2. 10초 이내에 파일을 업로드해주세요\n"
                           "3. 업로드된 파일로 자동 복구됩니다\n\n"
                           "⚠️ **주의:** 현재 데이터가 모두 교체됩니다!",
                color=0xffff00
            )

            await interaction.response.send_message(embed=embed)

            def check(m):
                return m.author == interaction.user and m.attachments and m.channel == interaction.channel

            try:
                message = await bot.wait_for('message', timeout=10.0, check=check)

                if message.attachments:
                    attachment = message.attachments[0]

                    if not attachment.filename.endswith('.json'):
                        await interaction.followup.send("❌ JSON 파일만 업로드 가능합니다.")
                        return

                    file_content = await attachment.read()

                    success, result = backup_manager.restore_from_upload(file_content)

                    embed = discord.Embed(
                        title="✅ 업로드 복구 완료" if success else "❌ 업로드 복구 실패",
                        description=result,
                        color=0x00ff00 if success else 0xff0000
                    )

                    if success:
                        embed.add_field(
                            name="📁 백업 저장",
                            value="업로드된 파일은 백업 디렉토리에 저장되었습니다.",
                            inline=False
                        )

                    await interaction.followup.send(embed=embed)

                    try:
                        await message.delete()
                    except:
                        pass

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ 시간 초과: 10초 내에 파일을 업로드해주세요.")

    # 에러 핸들러
    @콜사인설정.error
    async def 콜사인설정_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
