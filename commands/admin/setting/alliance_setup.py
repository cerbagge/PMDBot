# commands/admin/setting/alliance_setup.py
# /동맹설정 명령어 - 동맹 관리 시스템 (국가/마을 자동 감지)

import discord
from discord import app_commands
from typing import Literal, Optional
import datetime

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
    """봇에 /동맹설정 명령어 등록"""

    @bot.tree.command(name="동맹설정", description="동맹 관리 시스템 (국가/마을 자동 감지)")
    @app_commands.describe(
        기능="수행할 기능 선택",
        이름="국가 또는 마을 이름",
        역할="동맹 국가/마을에 부여할 역할 (선택)"
    )
    @app_commands.check(is_admin)
    async def 동맹설정(
        interaction: discord.Interaction,
        기능: Literal["추가", "제거", "목록", "역할설정"],
        이름: Optional[str] = None,
        역할: Optional[discord.Role] = None
    ):
        """동맹 관리 명령어 - PE API 기반 UUID 관리"""

        if 기능 == "추가":
            if not 이름:
                await interaction.response.send_message(
                    "❌ 추가할 국가 또는 마을 이름을 입력해주세요.",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # PE API로 국가/마을 자동 감지
            from pe_api_utils import pe_api
            from alliance_manager import add_alliance_by_name

            # 먼저 국가로 시도
            nation_data = await pe_api.get_nation_by_name(이름)

            if nation_data:
                # 국가로 감지됨
                result = await add_alliance_by_name(이름, 'nation')
                if not result:
                    await interaction.followup.send(
                        f"❌ 국가 \"{이름}\" 추가에 실패했습니다.",
                        ephemeral=True
                    )
                    return

                entity_type = "국가"
                entity_uuid = result['uuid']
                entity_name = result['name']
                all_names = result.get('names', [])
            else:
                # 마을로 시도
                town_data = await pe_api.get_town_by_name(이름)
                if town_data:
                    result = await add_alliance_by_name(이름, 'town')
                    if not result:
                        await interaction.followup.send(
                            f"❌ 마을 \"{이름}\" 추가에 실패했습니다.",
                            ephemeral=True
                        )
                        return

                    entity_type = "마을"
                    entity_uuid = result['uuid']
                    entity_name = result['name']
                    all_names = result.get('names', [])
                else:
                    await interaction.followup.send(
                        f"❌ \"{이름}\"을(를) 국가 또는 마을에서 찾을 수 없습니다.",
                        ephemeral=True
                    )
                    return

            # 중복 체크
            from alliance_manager import alliance_manager
            if alliance_manager.is_alliance_uuid(entity_uuid):
                await interaction.followup.send(
                    f"❌ {entity_name}은(는) 이미 동맹으로 추가되어 있습니다.",
                    ephemeral=True
                )
                return

            # 확인 임베드 생성
            embed = discord.Embed(
                title=f"🤝 동맹 {entity_type} 추가 완료",
                description=f"**{entity_name}**이(가) 동맹으로 추가되었습니다.",
                color=0x00AE86,
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="📋 타입", value=entity_type, inline=True)
            embed.add_field(name="🔑 UUID", value=f"`{entity_uuid[:8]}...`", inline=True)
            embed.add_field(name="🌐 모든 이름", value=", ".join(all_names[:5]), inline=False)

            # 역할 설정
            if 역할:
                # nation_role_manager에 역할 매핑 저장
                try:
                    from nation_role_manager import nation_role_manager
                    nation_role_manager.set_nation_role(entity_name, 역할.id)
                    embed.add_field(name="👤 역할", value=f"{역할.mention}", inline=True)
                except ImportError:
                    pass

            await interaction.followup.send(embed=embed)

        elif 기능 == "제거":
            if not 이름:
                await interaction.response.send_message(
                    "❌ 제거할 국가 또는 마을 이름을 입력해주세요.",
                    ephemeral=True
                )
                return

            from alliance_manager import alliance_manager

            # 이름으로 UUID 찾기
            uuid_to_remove = alliance_manager.get_alliance_uuid_by_name(이름)

            if not uuid_to_remove:
                await interaction.response.send_message(
                    f"❌ \"{이름}\"은(는) 동맹 목록에 없습니다.",
                    ephemeral=True
                )
                return

            # 제거
            alliance_data = alliance_manager.get_alliance_data(uuid_to_remove)
            removed = alliance_manager.remove_alliance_by_uuid(uuid_to_remove)

            if removed:
                await interaction.response.send_message(
                    f"✅ **{alliance_data.get('name', 이름)}**이(가) 동맹에서 제거되었습니다.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ 제거에 실패했습니다.",
                    ephemeral=True
                )

        elif 기능 == "목록":
            from alliance_manager import alliance_manager

            alliances_list = alliance_manager.get_alliances_list()

            if not alliances_list:
                await interaction.response.send_message(
                    "📋 현재 등록된 동맹이 없습니다.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🤝 동맹 목록",
                description=f"총 **{len(alliances_list)}**개의 동맹",
                color=0x00AE86,
                timestamp=datetime.datetime.now()
            )

            for i, alliance in enumerate(alliances_list, 1):
                entity_type = alliance.get('type', 'unknown')
                entity_name = alliance.get('name', 'Unknown')
                entity_uuid = alliance.get('uuid', 'N/A')
                added_date = alliance.get('added_at', '')

                if added_date:
                    try:
                        added_date = datetime.datetime.fromisoformat(added_date).strftime("%Y-%m-%d")
                    except:
                        added_date = "Unknown"

                type_emoji = "🌍" if entity_type == "nation" else "🏘️"

                embed.add_field(
                    name=f"{i}. {type_emoji} {entity_name}",
                    value=f"타입: {entity_type} | UUID: `{entity_uuid[:8]}...` | 추가: {added_date}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        elif 기능 == "역할설정":
            if not 이름:
                await interaction.response.send_message(
                    "❌ 설정할 국가 또는 마을 이름을 입력해주세요.",
                    ephemeral=True
                )
                return

            if not 역할:
                await interaction.response.send_message(
                    "❌ 부여할 역할을 멘션으로 지정해주세요.",
                    ephemeral=True
                )
                return

            from alliance_manager import alliance_manager

            # 이름으로 UUID 찾기
            alliance_uuid = alliance_manager.get_alliance_uuid_by_name(이름)

            if not alliance_uuid:
                await interaction.response.send_message(
                    f"❌ \"{이름}\"은(는) 동맹 목록에 없습니다.",
                    ephemeral=True
                )
                return

            alliance_data = alliance_manager.get_alliance_data(alliance_uuid)

            # nation_role_manager에 역할 매핑 저장
            try:
                from nation_role_manager import nation_role_manager
                nation_role_manager.set_nation_role(alliance_data['name'], 역할.id)

                await interaction.response.send_message(
                    f"✅ **{alliance_data['name']}** 동맹에 {역할.mention} 역할이 설정되었습니다.",
                    ephemeral=True
                )
            except ImportError:
                await interaction.response.send_message(
                    f"❌ nation_role_manager를 찾을 수 없습니다. 역할 설정에 실패했습니다.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ 역할 설정에 실패했습니다: {str(e)}",
                    ephemeral=True
                )
