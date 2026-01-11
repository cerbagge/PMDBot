# commands/admin/setting/town_role.py
# /마을역할 명령어 - 마을과 역할을 연동

import discord
from discord import app_commands
from typing import Literal, List
import os
import aiohttp
import time

# 환경 변수
MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")
BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")

# 안전한 import 처리
try:
    from town_role_manager import town_role_manager
    TOWN_ROLE_ENABLED = True
except ImportError:
    town_role_manager = None
    TOWN_ROLE_ENABLED = False

# 관리자 권한 체크
def is_admin(interaction: discord.Interaction) -> bool:
    CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359
    if interaction.user.guild_permissions.administrator:
        return True
    if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
        return True
    return False


# 마을이 국가에 속하는지 확인하는 함수
async def get_towns_in_nation(nation_name: str):
    """대체 함수: town_role_manager가 없을 때 기본 마을 목록 반환"""
    print(f"⚠️ town_role_manager가 없어서 대체 함수 사용: {nation_name}")
    try:
        api_base = MC_API_BASE or "https://api.planetearth.kr"

        async with aiohttp.ClientSession() as session:
            url = f"{api_base}/nation?name={nation_name}"
            print(f"🔍 대체 API 호출: {url}")

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                if response.status != 200:
                    print(f"❌ API 응답 오류: HTTP {response.status}")
                    return ["Seoul", "Busan", "Incheon"]  # 기본 테스트 마을

                data = await response.json()
                if not data.get('data') or not data['data']:
                    print(f"❌ 국가 데이터 없음: {nation_name}")
                    return ["Seoul", "Busan", "Incheon"]  # 기본 테스트 마을

                nation_data = data['data'][0]
                towns = nation_data.get('towns', [])

                if not towns:
                    print(f"ℹ️ {nation_name}에 마을이 없습니다.")
                    return ["Seoul", "Busan", "Incheon"]  # 기본 테스트 마을

                print(f"✅ {nation_name} 마을 목록: {len(towns)}개")
                return towns

    except Exception as e:
        print(f"❌ 대체 함수에서 오류: {e}")
        # 최후의 대체 마을 목록
        return ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju", "Ulsan"]


async def verify_town_in_nation(town_name: str, nation_name: str) -> bool:
    """마을이 특정 국가에 속하는지 확인하는 함수"""
    try:
        towns = await get_towns_in_nation(nation_name)
        return town_name in towns
    except Exception as e:
        print(f"❌ 마을 검증 오류: {e}")
        return False


# 자동완성 함수
async def town_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """마을 이름 자동완성 - 개선된 버전"""
    try:
        print(f"🔍 자동완성 요청: current='{current}', user={interaction.user.display_name}")

        if not TOWN_ROLE_ENABLED:
            print("⚠️ TOWN_ROLE_ENABLED가 False입니다.")
            return [app_commands.Choice(name="마을 역할 기능이 비활성화됨", value="disabled")]

        # 캐시된 마을 목록이 있다면 사용 (빠른 응답을 위해)
        if hasattr(town_autocomplete, '_cached_towns') and hasattr(town_autocomplete, '_cache_time'):
            current_time = time.time()
            # 캐시가 5분 이내라면 사용
            if current_time - town_autocomplete._cache_time < 300:
                print(f"📦 캐시된 마을 목록 사용: {len(town_autocomplete._cached_towns)}개")
                towns = town_autocomplete._cached_towns
            else:
                towns = None
        else:
            towns = None

        # 캐시가 없거나 만료된 경우 새로 가져오기
        if towns is None:
            print(f"🌐 API에서 마을 목록 가져오는 중... (국가: {BASE_NATION})")
            try:
                # 타임아웃을 짧게 설정 (자동완성은 3초 제한)
                towns = await get_towns_in_nation(BASE_NATION)
                print(f"✅ API에서 {len(towns) if towns else 0}개 마을 가져옴")

                # 캐시 저장
                if towns:
                    town_autocomplete._cached_towns = towns
                    town_autocomplete._cache_time = time.time()
                    print(f"💾 마을 목록 캐시됨")

            except Exception as api_error:
                print(f"❌ API 호출 실패: {api_error}")
                # API 실패 시 기본 안내 메시지
                return [app_commands.Choice(name="마을 목록을 불러올 수 없습니다", value="api_error")]

        if not towns:
            print(f"⚠️ {BASE_NATION}에 마을이 없습니다.")
            return [app_commands.Choice(name=f"{BASE_NATION}에 마을이 없습니다", value="no_towns")]

        print(f"🏘️ 총 {len(towns)}개 마을 발견")

        # 현재 입력값으로 필터링
        if current:
            # 대소문자 구분 없이 검색
            current_lower = current.lower()
            filtered_towns = []

            for town in towns:
                town_lower = town.lower()
                # 시작하는 마을을 먼저, 포함하는 마을을 나중에
                if town_lower.startswith(current_lower):
                    filtered_towns.insert(0, town)
                elif current_lower in town_lower:
                    filtered_towns.append(town)

            print(f"🔍 '{current}' 검색 결과: {len(filtered_towns)}개 마을")
        else:
            # 입력이 없으면 처음 25개 마을 반환
            filtered_towns = towns[:25]
            print(f"📋 전체 마을 목록에서 처음 {len(filtered_towns)}개 반환")

        # Discord 제한인 25개까지만 반환
        limited_towns = filtered_towns[:25]

        # Choice 객체 생성
        choices = []
        for town in limited_towns:
            # 마을 이름이 너무 길면 잘라서 표시
            display_name = town if len(town) <= 100 else town[:97] + "..."
            choices.append(app_commands.Choice(name=display_name, value=town))

        print(f"✅ 자동완성 완료: {len(choices)}개 선택지 반환")
        return choices

    except Exception as e:
        print(f"💥 자동완성 함수에서 예외 발생: {e}")
        import traceback
        traceback.print_exc()

        # 오류 시 기본 안내 메시지 반환
        return [app_commands.Choice(name="오류가 발생했습니다. 관리자에게 문의하세요", value="error")]


# TownRoleConfirmView 클래스
class TownRoleConfirmView(discord.ui.View):
    """마을 역할 연동 확인 버튼 뷰"""

    def __init__(self, town_name: str, role_id: int, role_obj: discord.Role, is_valid_town: bool):
        super().__init__(timeout=180.0)  # 180초 (3분) 타임아웃으로 연장
        self.town_name = town_name
        self.role_id = role_id
        self.role_obj = role_obj
        self.is_valid_town = is_valid_town
        self.result = None
        self.message = None  # 메시지 저장용

    async def on_timeout(self):
        """타임아웃 시 호출"""
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        title="⏱️ 시간 초과",
                        description=f"**{self.town_name}** 마을 역할 연동이 시간 초과로 취소되었습니다.\n다시 시도하려면 `/마을역할` 명령어를 사용하세요.",
                        color=0xff6600
                    ),
                    view=None
                )
            except:
                pass  # 메시지 편집 실패 시 무시

    @discord.ui.button(label="✅ 연동하기", style=discord.ButtonStyle.green)
    async def confirm_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        """연동 확인 버튼"""
        try:
            # 먼저 defer로 응답 시작
            await interaction.response.defer()

            self.result = "confirm"

            # 매핑 추가 - UUID 정보 먼저 가져오기
            if TOWN_ROLE_ENABLED and town_role_manager:
                # API에서 마을 정보 조회하여 UUID 가져오기
                town_uuid = None
                nation_uuid = None
                nation_name = None

                try:
                    async with aiohttp.ClientSession() as session:
                        # 마을 정보 조회
                        url = f"{MC_API_BASE}/town?name={self.town_name}"
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get('status') == 'SUCCESS' and data.get('data'):
                                    town_data = data['data'][0]
                                    town_uuid = town_data.get('uuid')
                                    nation_name = town_data.get('nation')

                                    # 국가 정보 조회하여 nation_uuid 가져오기
                                    if nation_name:
                                        url2 = f"{MC_API_BASE}/nation?name={nation_name}"
                                        async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as response2:
                                            if response2.status == 200:
                                                data2 = await response2.json()
                                                if data2.get('status') == 'SUCCESS' and data2.get('data'):
                                                    nation_data = data2['data'][0]
                                                    nation_uuid = nation_data.get('uuid')

                    # UUID를 모두 가져온 경우에만 매핑 추가
                    if town_uuid and nation_uuid and nation_name:
                        town_role_manager.add_mapping(
                            nation_uuid=nation_uuid,
                            town_uuid=town_uuid,
                            role_id=self.role_id,
                            nation_name=nation_name,
                            town_name=self.town_name
                        )
                    else:
                        raise ValueError(f"마을 또는 국가 UUID를 가져올 수 없습니다. town_uuid={town_uuid}, nation_uuid={nation_uuid}")

                except Exception as api_error:
                    print(f"❌ API 조회 오류: {api_error}")
                    raise api_error

            embed = discord.Embed(
                title="✅ 마을-역할 연동 완료",
                description=f"**{self.town_name}** 마을이 {self.role_obj.mention} 역할과 연동되었습니다.",
                color=0x00ff00
            )

            embed.add_field(
                name="📋 연동 정보",
                value=f"• **마을:** {self.town_name}\n• **역할:** {self.role_obj.mention}\n• **역할 ID:** {self.role_id}",
                inline=False
            )

            if not self.is_valid_town:
                embed.add_field(
                    name="⚠️ 참고사항",
                    value=f"이 마을은 **{BASE_NATION}** 소속이 아닐 수 있습니다.\n관리자가 수동으로 연동을 승인했습니다.",
                    inline=False
                )

            # 버튼 비활성화
            for item in self.children:
                item.disabled = True

            # defer 후에는 edit_original_response 사용
            await interaction.edit_original_response(embed=embed, view=self)
            self.stop()

        except Exception as e:
            print(f"❌ 연동하기 버튼 오류: {e}")
            try:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 오류 발생",
                        description=f"연동 처리 중 오류가 발생했습니다.\n{str(e)[:100]}",
                        color=0xff0000
                    ),
                    ephemeral=True
                )
            except:
                pass

    @discord.ui.button(label="❌ 취소하기", style=discord.ButtonStyle.red)
    async def cancel_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        """연동 취소 버튼"""
        try:
            # 먼저 defer로 응답 시작
            await interaction.response.defer()

            self.result = "cancel"

            embed = discord.Embed(
                title="❌ 마을-역할 연동 취소",
                description=f"**{self.town_name}** 마을과 {self.role_obj.mention} 역할의 연동이 취소되었습니다.",
                color=0xff6600
            )

            # 버튼 비활성화
            for item in self.children:
                item.disabled = True

            # defer 후에는 edit_original_response 사용
            await interaction.edit_original_response(embed=embed, view=self)
            self.stop()

        except Exception as e:
            print(f"❌ 취소하기 버튼 오류: {e}")
            try:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 오류 발생",
                        description=f"취소 처리 중 오류가 발생했습니다.\n{str(e)[:100]}",
                        color=0xff0000
                    ),
                    ephemeral=True
                )
            except:
                pass


def setup(bot):
    """봇에 /마을역할 명령어 등록"""

    @bot.tree.command(name="마을역할", description="마을과 역할을 연동합니다")
    @app_commands.describe(
        기능="수행할 작업을 선택하세요",
        역할="(추가 시만) 연동할 역할을 멘션하거나 역할 ID 입력",
        마을="(추가 시만) 연동할 마을 이름 (정확한 이름 입력)"
    )
    @app_commands.autocomplete(마을=town_autocomplete)
    @app_commands.check(is_admin)
    async def 마을역할(
        interaction: discord.Interaction,
        기능: Literal["추가", "제거", "목록", "마을목록"],
        역할: str = None,
        마을: str = None
    ):
        """마을과 역할 연동 관리"""

        # 마을 역할 기능이 비활성화된 경우
        if not TOWN_ROLE_ENABLED:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ 기능 비활성화",
                    description="마을 역할 기능이 비활성화되어 있습니다.\n"
                              "`town_role_manager.py` 파일이 필요합니다.",
                    color=0xff0000
                ),
                ephemeral=True
            )
            return

        if 기능 == "마을목록":
            # BASE_NATION의 마을 목록 표시 - 간단한 안내 메시지로 변경
            embed = discord.Embed(
                title=f"🏘️ {BASE_NATION} 마을 목록 확인 방법",
                description=f"API 호출을 줄이기 위해 마을 목록을 자동으로 가져오지 않습니다.",
                color=0x00bfff
            )

            embed.add_field(
                name="📋 마을 확인 방법",
                value=f"1. **웹사이트 확인**: {MC_API_BASE}/nation?name={BASE_NATION}\n"
                      f"2. **마을 추가 시**: 정확한 마을 이름을 입력하면 자동으로 검증됩니다\n"
                      f"3. **잘못된 마을**: {BASE_NATION} 소속이 아닌 경우 오류 메시지가 표시됩니다",
                inline=False
            )

            # 현재 매핑된 마을들 표시
            if TOWN_ROLE_ENABLED and town_role_manager:
                try:
                    mapped_towns = town_role_manager.get_mapped_towns()
                    if mapped_towns:
                        # 10개씩 나누어서 표시
                        for i in range(0, len(mapped_towns), 10):
                            chunk = mapped_towns[i:i+10]
                            field_name = f"✅ 이미 연동된 마을 ({i+1}-{min(i+10, len(mapped_towns))} / {len(mapped_towns)})"
                            embed.add_field(
                                name=field_name,
                                value="\n".join([f"• {town}" for town in chunk]),
                                inline=False
                            )
                    else:
                        embed.add_field(
                            name="ℹ️ 연동된 마을",
                            value="아직 연동된 마을이 없습니다.",
                            inline=False
                        )
                except:
                    embed.add_field(
                        name="ℹ️ 연동된 마을",
                        value="마을 정보를 가져올 수 없습니다.",
                        inline=False
                    )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        elif 기능 == "목록":
            # 현재 연동된 마을-역할 목록 표시
            try:
                mappings = town_role_manager.get_all_mappings_flat()

                embed = discord.Embed(
                    title="📋 마을-역할 연동 목록",
                    color=0x00bfff
                )

                if not mappings:
                    embed.description = "현재 연동된 마을-역할이 없습니다."
                else:
                    embed.description = f"총 **{len(mappings)}개**의 마을-역할이 연동되어 있습니다."

                    # 10개씩 나누어서 표시
                    for i in range(0, len(mappings), 10):
                        chunk = mappings[i:i+10]
                        field_items = []

                        for mapping in chunk:
                            town_name = mapping['town_name']
                            role_id = mapping['role_id']
                            nation_name = mapping.get('nation_name', 'Unknown')

                            # 역할이 존재하는지 확인
                            role = interaction.guild.get_role(role_id)
                            if role:
                                field_items.append(f"• **{town_name}** ({nation_name}) → {role.mention}")
                            else:
                                field_items.append(f"• **{town_name}** ({nation_name}) → ⚠️ 역할 없음 (ID: {role_id})")

                        embed.add_field(
                            name=f"연동 목록 ({i+1}-{min(i+10, len(mappings))})",
                            value="\n".join(field_items),
                            inline=False
                        )
            except Exception as e:
                embed = discord.Embed(
                    title="❌ 오류",
                    description=f"마을-역할 목록을 가져오는 중 오류가 발생했습니다.\n{str(e)}",
                    color=0xff0000
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 추가/제거 시 매개변수 검증
        if 기능 == "추가":
            if not 역할 or not 마을:
                await interaction.response.send_message(
                    "❌ 추가 기능을 사용할 때는 역할과 마을을 모두 입력해야 합니다.\n"
                    "예: `/마을역할 기능:추가 역할:@마을역할 마을:Seoul`",
                    ephemeral=True
                )
                return

            # 역할 ID 추출
            role_clean = 역할.replace('<@&', '').replace('>', '').replace('<@', '').replace('!', '')
            try:
                role_id = int(role_clean)
            except ValueError:
                await interaction.response.send_message(
                    "❌ 올바른 역할 ID 또는 멘션을 입력해주세요.\n"
                    "예: `@역할이름` 또는 `123456789`",
                    ephemeral=True
                )
                return

            # 역할 존재 확인
            guild = interaction.guild
            role_obj = guild.get_role(role_id)
            if not role_obj:
                await interaction.response.send_message(
                    f"❌ 역할을 찾을 수 없습니다. (ID: {role_id})",
                    ephemeral=True
                )
                return

            # 마을이 BASE_NATION에 존재하는지 확인 - 버튼 선택 방식
            await interaction.response.defer(thinking=True)

            try:
                print(f"🔍 마을 검증 시작: {마을} in {BASE_NATION}")
                is_valid_town = await verify_town_in_nation(마을, BASE_NATION)

                # 검증 결과에 따른 임베드 생성
                if is_valid_town:
                    embed = discord.Embed(
                        title="✅ 마을 검증 완료",
                        description=f"**{마을}**은(는) **{BASE_NATION}** 소속 마을입니다.",
                        color=0x00ff00
                    )
                    embed.add_field(
                        name="🏘️ 연동 정보",
                        value=f"• **마을:** {마을}\n• **역할:** {role_obj.mention}\n• **상태:** ✅ 검증됨",
                        inline=False
                    )
                else:
                    embed = discord.Embed(
                        title="⚠️ 마을 검증 경고",
                        description=f"**{마을}**은(는) **{BASE_NATION}** 소속이 아니거나 존재하지 않는 마을입니다.",
                        color=0xff9900
                    )
                    embed.add_field(
                        name="🏘️ 연동 정보",
                        value=f"• **마을:** {마을}\n• **역할:** {role_obj.mention}\n• **상태:** ⚠️ 미검증",
                        inline=False
                    )
                    embed.add_field(
                        name="💡 안내",
                        value="마을이 검증되지 않았지만 수동으로 연동할 수 있습니다.\n"
                              "연동을 진행하시겠습니까?",
                        inline=False
                    )

                # 공통 추가 정보
                embed.add_field(
                    name="🔧 다음 단계",
                    value="아래 버튼을 클릭하여 연동을 진행하거나 취소하세요.\n"
                          "3분 후 자동으로 취소됩니다.",
                    inline=False
                )

                # 버튼 뷰 생성
                view = TownRoleConfirmView(마을, role_id, role_obj, is_valid_town)

                # 메시지 전송 후 뷰에 메시지 저장
                message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                view.message = message
                return

            except Exception as e:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 오류 발생",
                        description=f"마을 확인 중 오류가 발생했습니다.\n{str(e)}",
                        color=0xff0000
                    ),
                    ephemeral=True
                )
                return

        elif 기능 == "제거":
            if not 마을:
                await interaction.response.send_message(
                    "❌ 제거 기능을 사용할 때는 마을 이름을 입력해야 합니다.\n"
                    "예: `/마을역할 기능:제거 마을:Seoul`",
                    ephemeral=True
                )
                return

            # 매핑 제거
            try:
                if town_role_manager.remove_mapping(마을):
                    embed = discord.Embed(
                        title="✅ 마을-역할 연동 해제",
                        description=f"**{마을}** 마을의 역할 연동이 해제되었습니다.",
                        color=0x00ff00
                    )
                else:
                    embed = discord.Embed(
                        title="⚠️ 연동되지 않은 마을",
                        description=f"**{마을}**은(는) 연동되지 않은 마을입니다.",
                        color=0xffaa00
                    )
            except Exception as e:
                embed = discord.Embed(
                    title="❌ 오류 발생",
                    description=f"마을 연동 해제 중 오류가 발생했습니다.\n{str(e)}",
                    color=0xff0000
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

    # 에러 핸들러
    @마을역할.error
    async def 마을역할_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ 권한 없음",
                description="이 명령어는 관리자만 사용할 수 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
