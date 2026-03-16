# commands/admin/setting/alliance_check.py
# /동맹확인 명령어 - 모든 멤버의 동맹 역할을 재확인

import discord
from discord import app_commands
import datetime
import json
import os

# 동맹 데이터 경로
ALLIANCE_DATA_PATH = "data/alliances.json"
ROLE_DATA_PATH = "data/alliance_roles.json"

# 동맹 관련 함수들
def load_alliance_data():
    """동맹 데이터 로드"""
    try:
        with open(ALLIANCE_DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"alliances": []}

def load_role_data():
    """역할 데이터 로드"""
    try:
        with open(ROLE_DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"roles": {}}

# 안전한 import 처리
try:
    from database_manager import db_manager as database_manager
    DATABASE_ENABLED = True
except ImportError:
    database_manager = None
    DATABASE_ENABLED = False

try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None

# 관리자 권한 체크 함수
def is_admin(interaction: discord.Interaction) -> bool:
    """관리자 권한이 있거나 특정 역할을 가진 경우 허용"""
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359

    # 관리자 권한 체크
    if interaction.user.guild_permissions.administrator:
        return True

    # 콜사인 관리자 역할 체크
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True

    return False


def setup(bot):
    """봇에 /동맹확인 명령어 등록"""

    @bot.tree.command(name="동맹확인", description="모든 멤버의 동맹 역할을 재확인합니다")
    @app_commands.check(is_admin)
    async def 동맹확인(interaction: discord.Interaction):
        """모든 멤버의 동맹 역할 재확인 (데이터베이스 기반)"""
        await interaction.response.defer()

        if bot_logger:
            bot_logger.log_command("동맹확인", interaction.user.id, interaction.user.name,
                                   source="admin_command", category=LogCategory.ALLIANCE)

        alliance_data = load_alliance_data()
        role_data = load_role_data()

        updated_count = 0
        removed_count = 0
        checked_count = 0

        # 모든 멤버 확인
        for member in interaction.guild.members:
            if member.bot:
                continue  # 봇 제외

            # 데이터베이스에서 현재 국가 정보 조회
            if not DATABASE_ENABLED or not database_manager:
                continue

            nation_info = database_manager.get_current_nation(member.id)

            if nation_info and nation_info.get('nation_name'):
                user_country = nation_info['nation_name']
                checked_count += 1

                # 동맹 국가인지 확인
                alliance = next((a for a in alliance_data["alliances"]
                               if a["name"].lower() == user_country.lower() and a.get("has_role")), None)

                if alliance:
                    role_id = role_data["roles"].get(alliance["name"])
                    if role_id:
                        role = interaction.guild.get_role(role_id)
                        if role and role not in member.roles:
                            try:
                                await member.add_roles(role)
                                updated_count += 1
                                print(f"✅ {member.display_name}: {alliance['name']} 역할 부여")
                            except Exception as e:
                                print(f"⚠️ 역할 부여 실패 ({member.display_name}): {e}")
                else:
                    # 동맹이 아닌데 역할을 가지고 있는 경우 제거
                    for alliance_name, role_id in role_data["roles"].items():
                        role = interaction.guild.get_role(role_id)
                        if role and role in member.roles:
                            try:
                                await member.remove_roles(role)
                                removed_count += 1
                                print(f"❌ {member.display_name}: {alliance_name} 역할 제거")
                            except Exception as e:
                                print(f"⚠️ 역할 제거 실패 ({member.display_name}): {e}")

        embed = discord.Embed(
            title="🔍 동맹 역할 확인 완료",
            description="모든 멤버의 동맹 역할을 확인했습니다.",
            color=0x00AE86,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="✅ 역할 부여", value=f"{updated_count}명", inline=True)
        embed.add_field(name="❌ 역할 제거", value=f"{removed_count}명", inline=True)
        embed.add_field(name="📊 확인된 멤버", value=f"{checked_count}명", inline=True)
        embed.add_field(name="👥 전체 멤버", value=f"{len([m for m in interaction.guild.members if not m.bot])}명", inline=True)

        await interaction.followup.send(embed=embed)
