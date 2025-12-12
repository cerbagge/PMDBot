import discord
from discord import app_commands
from discord.ext import commands
from typing import Literal, List, Optional
import aiohttp
import os
import json
import time
import datetime

# 안전한 import 처리
try:
    from queue_manager import queue_manager
    print("✅ queue_manager 로드 성공")
except ImportError as e:
    print(f"❌ queue_manager 로드 실패: {e}")
    # 더미 queue_manager 클래스 생성
    class DummyQueueManager:
        def get_queue_size(self): return 0
        def is_processing(self): return False
        def add_user(self, user_id): pass
        def clear_queue(self): return 0
    queue_manager = DummyQueueManager()

try:
    from exception_manager import exception_manager
    print("✅ exception_manager 로드 성공")
except ImportError as e:
    print(f"❌ exception_manager 로드 실패: {e}")
    # 더미 exception_manager 클래스 생성
    class DummyExceptionManager:
        def get_exceptions(self): return []
        def add_exception(self, user_id): return True
        def remove_exception(self, user_id): return True
    exception_manager = DummyExceptionManager()

# database_manager 안전하게 import
try:
    from database_manager import db_manager
    print("✅ database_manager 모듈 로드됨 (commands.py)")
    DATABASE_ENABLED = True
except ImportError as e:
    print(f"⚠️ database_manager 모듈을 로드할 수 없습니다 (commands.py): {e}")
    print("📝 데이터베이스 기능이 비활성화됩니다.")
    db_manager = None
    DATABASE_ENABLED = False

# callsign_manager 안전하게 import
try:
    from callsign_manager import callsign_manager, validate_callsign, get_user_display_info
    print("✅ callsign_manager 모듈 로드됨 (commands.py)")
    CALLSIGN_ENABLED = True
except ImportError as e:
    print(f"⚠️ callsign_manager 모듈을 로드할 수 없습니다 (commands.py): {e}")
    print("📝 콜사인 기능이 비활성화됩니다.")
    callsign_manager = None
    CALLSIGN_ENABLED = False

    # 대체 함수 정의
    def validate_callsign(callsign: str):
        return False, "콜사인 기능이 비활성화됨"

    def get_user_display_info(user_id: int, mc_id: str = None, nation: str = None):
        if nation:
            return f"{mc_id} ㅣ {nation}"
        return mc_id or 'Unknown'

# town_role_manager 안전하게 import
try:
    from town_role_manager import town_role_manager, get_towns_in_nation
    print("✅ town_role_manager 모듈 로드됨 (commands.py)")
    TOWN_ROLE_ENABLED = True
except ImportError as e:
    print(f"⚠️ town_role_manager 모듈을 로드할 수 없습니다 (commands.py): {e}")
    print("📝 마을 역할 기능이 비활성화됩니다.")
    town_role_manager = None
    TOWN_ROLE_ENABLED = False

# 동맹 시스템 설정 (town_role_manager와 독립적)
ALLIANCE_DATA_PATH = "data/alliances.json"
ROLE_DATA_PATH = "data/alliance_roles.json"

# 데이터 디렉토리 생성
os.makedirs("data", exist_ok=True)

# 동맹 관련 함수들
def load_alliance_data():
    """동맹 데이터 로드"""
    try:
        with open(ALLIANCE_DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"alliances": []}

def save_alliance_data(data):
    """동맹 데이터 저장"""
    with open(ALLIANCE_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_role_data():
    """역할 데이터 로드"""
    try:
        with open(ROLE_DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"roles": {}}

def save_role_data(data):
    """역할 데이터 저장"""
    with open(ROLE_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def get_country_info(country_name):
    """PE API에서 국가 정보 가져오기 (UUID 기반)"""
    try:
        from pe_api_utils import pe_api, PEApiError

        # PE API로 국가 정보 조회
        nation_data = await pe_api.get_nation_by_name(country_name)

        if nation_data:
            # PE API 응답 구조에 맞게 변환
            return {
                "name": nation_data.get("name", country_name),
                "uuid": nation_data.get("uuid"),
                "native_name": nation_data.get("name", country_name),
                "capital": nation_data.get("capital", "정보 없음"),
                "population": f"{nation_data.get('residents', 0):,}",
                "region": "Planet Earth",
                "subregion": nation_data.get("board", "정보 없음"),
                "languages": ", ".join(nation_data.get("names", [])) if nation_data.get("names") else nation_data.get("name", "정보 없음"),
                "flag": "🌍",  # PE에는 국기 이모지가 없으므로 기본값
                "flag_url": None,
                "all_names": nation_data.get("names", [nation_data.get("name", country_name)])
            }

        print(f"❌ 국가 정보를 찾을 수 없음: {country_name}")
        return None

    except PEApiError as e:
        # PE API 서버 연결 에러 - 사용자에게 명확한 메시지 전달
        print(f"🔴 PE API 에러: {e}")
        raise  # 호출자에게 다시 던져서 처리하도록
    except Exception as e:
        print(f"❌ 국가 정보 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        return None

# 대체 함수 정의 - 개선된 버전
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

# 환경변수 로드 - 기본값 설정
MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")
BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")
SUCCESS_ROLE_ID = int(os.getenv("SUCCESS_ROLE_ID", "0"))
SUCCESS_ROLE_ID_OUT = int(os.getenv("SUCCESS_ROLE_ID_OUT", "0"))
SUCCESS_CHANNEL_ID = int(os.getenv("SUCCESS_CHANNEL_ID", "0"))
FAILURE_CHANNEL_ID = int(os.getenv("FAILURE_CHANNEL_ID", "0"))

# 콜사인 쿨타임 저장소 (실제로는 파일이나 DB에 저장해야 함)
callsign_cooldowns = {}

async def send_log_message(bot, channel_id: int, embed: discord.Embed):
    """로그 메시지를 지정된 채널에 전송"""
    try:
        if channel_id == 0:
            print("⚠️ 채널 ID가 설정되지 않았습니다.")
            return

        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"⚠️ 채널을 찾을 수 없습니다: {channel_id}")
            return

        await channel.send(embed=embed)
        print(f"📨 로그 메시지 전송됨: {channel.name}")

    except Exception as e:
        print(f"❌ 로그 메시지 전송 실패: {e}")

def check_callsign_cooldown(user_id: int) -> tuple[bool, int]:
    """
    콜사인 쿨타임 확인
    Returns: (can_use, remaining_days)
    """
    if user_id not in callsign_cooldowns:
        return True, 0
    
    last_used = callsign_cooldowns[user_id]
    now = datetime.datetime.now()
    
    # 15일 = 15 * 24 * 60 * 60 초
    cooldown_period = datetime.timedelta(days=15)
    time_passed = now - last_used
    
    if time_passed >= cooldown_period:
        return True, 0
    else:
        remaining = cooldown_period - time_passed
        remaining_days = remaining.days
        if remaining.seconds > 0:
            remaining_days += 1
        return False, remaining_days

def set_callsign_cooldown(user_id: int):
    """콜사인 쿨타임 설정"""
    callsign_cooldowns[user_id] = datetime.datetime.now()

# verify_town_in_nation 함수 추가
async def verify_town_in_nation(town_name: str, nation_name: str) -> bool:
    """마을이 특정 국가에 속하는지 확인하는 함수"""
    try:
        towns = await get_towns_in_nation(nation_name)
        return town_name in towns
    except Exception as e:
        print(f"❌ 마을 검증 오류: {e}")
        return False

# 자동완성 함수를 독립적으로 정의 - 개선된 버전
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

# AllianceConfirmView 클래스 추가
class AllianceConfirmView(discord.ui.View):
    """동맹 추가 확인 뷰"""
    def __init__(self, country_info, enable_role, timeout=60):
        super().__init__(timeout=timeout)
        self.country_info = country_info
        self.enable_role = enable_role
        self.value = None

    @discord.ui.button(label="추가", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await self.process_alliance_add(interaction)
        self.stop()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(
            content="❌ 동맹 추가가 취소되었습니다.",
            embed=None,
            view=None
        )
        self.stop()

    async def process_alliance_add(self, interaction: discord.Interaction):
        """동맹 추가 처리"""
        alliance_data = load_alliance_data()
        
        new_alliance = {
            "name": self.country_info["name"],
            "capital": self.country_info["capital"],
            "flag": self.country_info["flag"],
            "has_role": self.enable_role,
            "added_at": datetime.datetime.now().isoformat()
        }
        
        alliance_data["alliances"].append(new_alliance)
        save_alliance_data(alliance_data)
        
        # 역할 생성 (필요한 경우)
        if self.enable_role:
            try:
                role = await interaction.guild.create_role(
                    name=f"🤝 {self.country_info['name']}",
                    color=discord.Color(0x00AE86),
                    reason=f"동맹 국가 {self.country_info['name']} 역할 생성"
                )
                
                role_data = load_role_data()
                role_data["roles"][self.country_info["name"]] = role.id
                save_role_data(role_data)
                
                await interaction.response.edit_message(
                    content=f"✅ **{self.country_info['name']}**이(가) 동맹에 추가되었습니다! (역할 생성됨)",
                    embed=None,
                    view=None
                )
            except Exception as e:
                await interaction.response.edit_message(
                    content=f"✅ **{self.country_info['name']}**이(가) 동맹에 추가되었습니다! (역할 생성 실패: {str(e)})",
                    embed=None,
                    view=None
                )
        else:
            await interaction.response.edit_message(
                content=f"✅ **{self.country_info['name']}**이(가) 동맹에 추가되었습니다!",
                embed=None,
                view=None
            )

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
                import aiohttp
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
    
    async def on_timeout(self):
        """타임아웃 시 호출"""
        # 버튼 비활성화
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        title="⏱️ 시간 초과",
                        description=f"**{self.town_name}** 마을 역할 연동이 시간 초과로 취소되었습니다.\n다시 시도하려면 `/마을역할` 명령어를 사용하세요.",
                        color=0xff6600
                    ),
                    view=self
                )
            except Exception as e:
                print(f"⚠️ 타임아웃 메시지 편집 실패: {e}")

class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def is_admin(interaction: discord.Interaction) -> bool:
        # 관리자 권한이 있거나 특정 역할을 가진 경우 허용
        CALLSIGN_MANAGER_ROLE_ID = 1448131353890783359

        # 관리자 권한 체크
        if interaction.user.guild_permissions.administrator:
            return True

        # 콜사인 관리자 역할 체크
        if any(role.id == CALLSIGN_MANAGER_ROLE_ID for role in interaction.user.roles):
            return True

        return False

    async def send_long_message_via_webhook(self, interaction: discord.Interaction, embeds_data):
        """웹훅을 통해 긴 메시지를 여러 개로 나누어 전송"""
        try:
            # 웹훅 생성
            webhook = await interaction.channel.create_webhook(name="국민확인봇")
            
            # 각 임베드 데이터를 개별 메시지로 전송
            for embed_data in embeds_data:
                embed = discord.Embed(
                    title=embed_data["title"],
                    color=embed_data["color"]
                )
                
                for field in embed_data["fields"]:
                    embed.add_field(
                        name=field["name"],
                        value=field["value"],
                        inline=field.get("inline", False)
                    )
                
                await webhook.send(embed=embed)
            
            # 웹훅 삭제
            await webhook.delete()
            
        except Exception as e:
            # 웹훅 실패 시 기존 방식으로 폴백
            print(f"웹훅 전송 실패: {e}")
            embed = discord.Embed(
                title="🛡️ 국민 확인 결과 (요약)",
                description="전체 결과가 너무 길어서 요약본만 표시됩니다.",
                color=0x00bfff
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    # 동맹 관련 헬퍼 메서드들
    async def check_and_assign_role(self, member, country_name):
        """동맹 역할 확인 및 부여"""
        alliance_data = load_alliance_data()
        role_data = load_role_data()
        
        # 해당 국가가 동맹인지 확인
        alliance = next((a for a in alliance_data["alliances"] 
                       if a["name"].lower() == country_name.lower() and a.get("has_role")), None)
        
        if alliance:
            role_id = role_data["roles"].get(alliance["name"])
            if role_id:
                role = member.guild.get_role(role_id)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                        print(f"✅ {member.display_name}에게 {alliance['name']} 동맹 역할 부여")
                    except Exception as e:
                        print(f"역할 부여 실패: {e}")
    
    async def remove_alliance_role(self, member, country_name):
        """동맹 역할 제거"""
        alliance_data = load_alliance_data()
        role_data = load_role_data()
        
        alliance = next((a for a in alliance_data["alliances"] 
                       if a["name"].lower() == country_name.lower()), None)
        
        if alliance:
            role_id = role_data["roles"].get(alliance["name"])
            if role_id:
                role = member.guild.get_role(role_id)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role)
                        print(f"❌ {member.display_name}에게서 {alliance['name']} 동맹 역할 제거")
                    except Exception as e:
                        print(f"역할 제거 실패: {e}")

    @app_commands.command(name="도움말", description="봇의 모든 명령어를 확인합니다")
    async def 도움말(self, interaction: discord.Interaction):
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
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
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
        total_commands = len(self.bot.tree.get_commands())
        embed.set_footer(
            text=f"🤖 {self.bot.user.name} • 총 {total_commands}개 명령어 • 권한: {'관리자' if is_admin else '일반 사용자'}",
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None
        )
        
        # 현재 시간 추가
        embed.timestamp = datetime.datetime.now()
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="동맹설정", description="동맹 관리 시스템 (국가/마을 자동 감지)")
    @app_commands.describe(
        기능="수행할 기능 선택",
        이름="국가 또는 마을 이름",
        역할="동맹 국가/마을에 부여할 역할 (선택)"
    )
    @app_commands.check(is_admin)
    async def 동맹설정(
        self,
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
    
    @app_commands.command(name="국가설정", description="[관리자] 디스코드 봇이 관리할 기본 국가(BASE_NATION)를 설정합니다")
    @app_commands.describe(국가="설정할 국가 이름")
    @app_commands.check(is_admin)
    async def 국가설정(self, interaction: discord.Interaction, 국가: str):
        """[관리자] 서버 BASE_NATION 설정"""
        await interaction.response.defer()

        try:
            from config import config

            # config의 set_base_nation 메소드 사용
            success, message, uuid = await config.set_base_nation(국가)

            if success:
                embed = discord.Embed(
                    title="✅ 서버 국가 설정 완료",
                    description=message,
                    color=0x00ff00,
                    timestamp=datetime.datetime.now()
                )

                embed.add_field(
                    name="📍 설정된 국가",
                    value=f"**{config.BASE_NATION}**",
                    inline=True
                )

                embed.add_field(
                    name="🆔 UUID",
                    value=f"`{uuid}`",
                    inline=False
                )

                embed.set_footer(text=f"관리자: {interaction.user.name}")

            else:
                embed = discord.Embed(
                    title="❌ 국가 설정 실패",
                    description=message,
                    color=0xff0000,
                    timestamp=datetime.datetime.now()
                )
                embed.set_footer(text="정확한 국가명을 입력해주세요")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            error_embed = discord.Embed(
                title="❌ 오류 발생",
                description=f"국가 설정 중 오류가 발생했습니다:\n```{str(e)}```",
                color=0xff0000
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)

    @app_commands.command(name="콜사인", description="개인 콜사인(별명)을 설정합니다 (15일 쿨타임)")
    @app_commands.describe(텍스트="설정할 콜사인 (최대 20자)")
    async def 콜사인(self, interaction: discord.Interaction, 텍스트: str):
        """사용자 콜사인 설정 - 15일 쿨타임 적용"""

        if not CALLSIGN_ENABLED:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⌛ 기능 비활성화",
                    description="콜사인 기능이 비활성화되어 있습니다.\n"
                              "`callsign_manager.py` 파일이 필요합니다.",
                    color=0xff0000
                ),
                ephemeral=True
            )
            return

        # 권한 체크 추가 - 금지된 사용자인지 확인
        if callsign_manager.is_banned(interaction.user.id):
            ban_info = callsign_manager.get_ban_info(interaction.user.id)
            embed = discord.Embed(
                title="🚫 콜사인 사용 금지",
                description=f"콜사인 기능을 사용할 수 없습니다.\n\n"
                           f"**사유:** {ban_info.get('reason', '관리자 결정')}\n"
                           f"**금지 일시:** {ban_info.get('banned_at', '알 수 없음')[:19] if ban_info.get('banned_at') else '알 수 없음'}",
                color=0xff0000
            )
            embed.set_footer(text="문의사항은 관리자에게 연락해주세요.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 콜사인 유효성 검증
        is_valid, error_msg = validate_callsign(텍스트)
        if not is_valid:
            await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
            return

        # defer를 먼저 호출 (API 조회 및 닉네임 변경에 시간이 걸릴 수 있음)
        await interaction.response.defer(ephemeral=True)

        # 콜사인 설정
        success, message = callsign_manager.set_callsign(interaction.user.id, 텍스트)

        if not success:
            # 쿨타임 등으로 실패한 경우
            embed = discord.Embed(
                title="⏰ 쿨타임 중",
                description=message,
                color=0xff6600
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 콜사인 설정 성공 시 즉시 닉네임 적용
        member = interaction.user
        discord_id = member.id
        nickname_updated = False
        nickname_error = None
        mc_id = None
        nation = None

        try:
            # API를 통해 마크 ID와 국가 정보 조회
            import aiohttp
            import time

            async with aiohttp.ClientSession() as session:
                # 1단계: 디스코드 ID → 마크 ID
                url1 = f"{MC_API_BASE}/discord?discord={discord_id}"
                async with session.get(url1, timeout=aiohttp.ClientTimeout(total=10)) as r1:
                    if r1.status == 200:
                        data1 = await r1.json()
                        if data1.get('data') and data1['data']:
                            mc_id = data1['data'][0].get('name')
                            mc_uuid = data1['data'][0].get('uuid')

                            # 데이터베이스에 저장 (UUID와 Minecraft 닉네임)
                            if DATABASE_ENABLED and db_manager and mc_id and mc_uuid:
                                try:
                                    db_manager.add_or_update_user(
                                        discord_id=discord_id,
                                        minecraft_uuid=mc_uuid,
                                        minecraft_name=mc_id
                                    )
                                    print(f"  💾 데이터베이스 저장: {mc_id} (UUID: {mc_uuid[:8]}...)")
                                except Exception as db_error:
                                    print(f"  ⚠️ 데이터베이스 저장 실패: {db_error}")

                            if mc_id:
                                time.sleep(2)

                                # 2단계: 마크 ID → 마을
                                url2 = f"{MC_API_BASE}/resident?name={mc_id}"
                                async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                                    if r2.status == 200:
                                        data2 = await r2.json()
                                        if data2.get('data') and data2['data']:
                                            town = data2['data'][0].get('town')
                                            if town:
                                                time.sleep(2)

                                                # 3단계: 마을 → 국가
                                                url3 = f"{MC_API_BASE}/town?name={town}"
                                                async with session.get(url3, timeout=aiohttp.ClientTimeout(total=10)) as r3:
                                                    if r3.status == 200:
                                                        data3 = await r3.json()
                                                        if data3.get('data') and data3['data']:
                                                            nation = data3['data'][0].get('nation')

                                                            # BASE_NATION 국민인 경우에만 콜사인 적용
                                                            if nation == BASE_NATION:
                                                                new_nickname = f"{mc_id} ㅣ {텍스트}"

                                                                # 닉네임 변경 시도
                                                                try:
                                                                    await member.edit(nick=new_nickname)
                                                                    nickname_updated = True
                                                                    print(f"✅ 콜사인 적용으로 닉네임 변경: {new_nickname}")
                                                                except discord.Forbidden:
                                                                    nickname_error = "닉네임 변경 권한이 없습니다."
                                                                    print(f"⚠️ 닉네임 변경 권한 없음")
                                                                except Exception as e:
                                                                    nickname_error = f"닉네임 변경 실패: {str(e)[:50]}"
                                                                    print(f"⚠️ 닉네임 변경 실패: {e}")
                                                            else:
                                                                nickname_error = f"{BASE_NATION} 국민만 콜사인을 사용할 수 있습니다."
        except Exception as e:
            print(f"⚠️ 콜사인 즉시 적용 중 오류: {e}")
            nickname_error = "마인크래프트 계정 정보를 확인할 수 없습니다."

        # 결과 메시지 생성
        embed = discord.Embed(
            title="✅ 콜사인 설정 완료",
            description=f"콜사인이 **{텍스트}**로 설정되었습니다.",
            color=0x00ff00
        )

        # 쿨타임 정보
        embed.add_field(
            name="⏰ 쿨타임 적용",
            value="15일 후에 다시 변경할 수 있습니다.",
            inline=False
        )

        # 닉네임 변경 결과
        if nickname_updated:
            if mc_id:
                new_nickname = f"{mc_id} ㅣ {텍스트}"
                embed.add_field(
                    name="🔄 닉네임 변경",
                    value=f"• 닉네임이 **``{new_nickname}``**로 즉시 변경됨",
                    inline=False
                )
                embed.add_field(
                    name="💡 안내",
                    value=f"• {BASE_NATION} 국민이므로 콜사인이 즉시 적용되었습니다.\n• 마인크래프트 정보가 변경되면 `/확인` 명령어를 사용하세요.",
                    inline=False
                )
                embed.add_field(
                    name="🏷️ 적용된 닉네임 형식",
                    value=f"**형식:** `{mc_id} ㅣ {텍스트}`",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🔄 닉네임 변경",
                    value=f"• 닉네임이 **``{텍스트}``** 콜사인으로 즉시 변경됨",
                    inline=False
                )
                embed.add_field(
                    name="💡 안내",
                    value=f"• {BASE_NATION} 국민이므로 콜사인이 즉시 적용되었습니다.\n• 마인크래프트 정보가 변경되면 `/확인` 명령어를 사용하세요.",
                    inline=False
                )
        elif nickname_error:
            embed.add_field(
                name="⚠️ 닉네임 변경 실패",
                value=f"{nickname_error}\n`/확인` 명령어를 사용하여 수동으로 적용해주세요.",
                inline=False
            )
            embed.add_field(
                name="ℹ️ 안내",
                value="다음 변경은 15일 후에 가능합니다.",
                inline=False
            )
        else:
            embed.add_field(
                name="ℹ️ 안내",
                value="다음 변경은 15일 후에 가능합니다.",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="동맹확인", description="모든 멤버의 동맹 역할을 재확인합니다")
    @app_commands.check(is_admin)
    async def 동맹확인(self, interaction: discord.Interaction):
        """모든 멤버의 동맹 역할 재확인 (데이터베이스 기반)"""
        await interaction.response.defer()

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
    

    @app_commands.command(name="콜사인관리", description="사용자 콜사인을 관리합니다")
    @app_commands.describe(
        기능="실행할 기능 선택",
        유저="대상 사용자 (쿨타임_초기화: 비어있으면 전체, 멘션하면 해당 유저만)",
        텍스트="콜사인 텍스트 또는 사유"
    )
    @app_commands.check(is_admin)
    async def 콜사인관리(
        self,
        interaction: discord.Interaction,
        기능: Literal["사용자_조회", "콜사인_변경", "전체_목록", "권한박탈", "권한복구", "권한박탈_목록", "쿨타임_초기화", "데이터_백업", "백업_목록", "데이터_복구", "백업파일_업로드"],
        유저: discord.Member = None,
        텍스트: str = None
    ):
        """사용자 콜사인 관리 - 관리자 전용"""
        # ======================================
        #
        #             기본 사유 지정
        #
        # ======================================
        
        COLLSIGN_BASE_REASON = "사유 없음"
        COLLSIGN_BASE_BAN_REASON = "관리자가 박탈"

        # ======================================
        if not CALLSIGN_ENABLED:
            embed = discord.Embed(
                title="⌛ 기능 비활성화",
                description="콜사인 기능이 비활성화되어 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # 기능별 처리
        if 기능 == "사용자_조회":  # 기존: 콜사인_조회
            if not 유저:
                await interaction.response.send_message("조회할 사용자를 지정해주세요.")
                return
            
            callsign = callsign_manager.get_callsign(유저.id)
            is_banned = callsign_manager.is_banned(유저.id)
            
            embed = discord.Embed(
                title="🔍 콜사인 조회",
                color=0x00ff00 if not is_banned else 0xff0000
            )
            
            if is_banned:
                ban_info = callsign_manager.get_ban_info(유저.id)
                embed.add_field(
                    name="⛔ 상태",
                    value="콜사인 사용 권한 없음",
                    inline=False
                )
                embed.add_field(
                    name="📅 권한 박탈 일시",
                    value=ban_info.get("banned_at", "알 수 없음")[:19],
                    inline=True
                )
                embed.add_field(
                    name="📝 사유",
                    value=ban_info.get("reason", COLLSIGN_BASE_REASON ),
                    inline=True
                )
            elif callsign:
                embed.add_field(
                    name="✅ 현재 콜사인",
                    value=f"`{callsign}`",
                    inline=False
                )
                callsign_info = callsign_manager.get_callsign_info(유저.id)
                if callsign_info and "set_at" in callsign_info:
                    embed.add_field(
                        name="📅 설정 일시",
                        value=callsign_info["set_at"][:19],
                        inline=False
                    )
            else:
                embed.add_field(
                    name="ℹ️ 상태",
                    value="설정된 콜사인 없음",
                    inline=False
                )
            
            embed.set_footer(text=f"대상: {유저.name} ({유저.id})")
            await interaction.response.send_message(embed=embed)
        
        elif 기능 == "콜사인_변경":  # 기존: 콜사인_설정
            if not 유저 or not 텍스트:
                await interaction.response.send_message("사용자와 콜사인 텍스트를 모두 입력해주세요.", ephemeral=True)
                return
            
            # 콜사인 유효성 검증
            from callsign_manager import validate_callsign
            is_valid, error_msg = validate_callsign(텍스트)
            if not is_valid:
                embed = discord.Embed(
                    title="❌ 콜사인 유효성 검증 실패",
                    description=f"**오류:** {error_msg}",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # 기존 콜사인 확인
            old_callsign = callsign_manager.get_callsign(유저.id)
            
            # 권한 박탈 상태 확인
            is_banned = callsign_manager.is_banned(유저.id)
            ban_info = None
            if is_banned:
                ban_info = callsign_manager.get_ban_info(유저.id)
            
            # 관리자 권한으로 콜사인 설정 (모든 제약 무시)
            success, message = callsign_manager.admin_set_callsign(
                user_id=유저.id,
                callsign=텍스트,
                admin_id=interaction.user.id
            )
            
            if success:
                # defer 호출 먼저 (API 조회 시간이 필요)
                await interaction.response.defer(ephemeral=True)

                # 닉네임 업데이트 시도
                nick_changed = False
                new_nick = ""
                nick_error = None
                mc_id = None

                try:
                    # API를 통해 마인크래프트 ID 조회
                    import aiohttp
                    import time

                    async with aiohttp.ClientSession() as session:
                        # 1단계: 디스코드 ID → 마크 ID
                        url1 = f"{MC_API_BASE}/discord?discord={유저.id}"
                        async with session.get(url1, timeout=aiohttp.ClientTimeout(total=10)) as r1:
                            if r1.status == 200:
                                data1 = await r1.json()
                                if data1.get('data') and data1['data']:
                                    mc_id = data1['data'][0].get('name')

                    # 마크 ID가 있으면 사용, 없으면 현재 닉네임 사용
                    if mc_id:
                        base_name = mc_id
                    else:
                        # 마크 ID를 가져올 수 없으면 현재 닉네임에서 추출
                        current_nick = 유저.display_name
                        if 'ㅣ' in current_nick:
                            base_name = current_nick.split('ㅣ')[0].strip()
                        elif '|' in current_nick:
                            base_name = current_nick.split('|')[0].strip()
                        else:
                            base_name = current_nick

                    # 새 닉네임 생성
                    new_nick = f"{base_name} ㅣ {텍스트}"

                    # 닉네임 길이 제한 (32자)
                    if len(new_nick) > 32:
                        # 콜사인을 우선 보존하고 이름 부분을 줄임
                        max_name_len = 32 - len(f" ㅣ {텍스트}")
                        if max_name_len > 0:
                            truncated_name = base_name[:max_name_len]
                            new_nick = f"{truncated_name} ㅣ {텍스트}"
                        else:
                            # 콜사인이 너무 길어서 이름을 넣을 공간이 없는 경우
                            new_nick = f"User ㅣ {텍스트[:27]}"  # 강제로 줄임

                    # 닉네임 변경 시도
                    await 유저.edit(nick=new_nick, reason=f"관리자 콜사인 설정: {interaction.user.name}")
                    nick_changed = True

                except discord.Forbidden:
                    nick_changed = False
                    nick_error = "권한 없음 (관리자 역할보다 높음)"
                except discord.HTTPException as e:
                    nick_changed = False
                    nick_error = f"Discord API 오류: {str(e)}"
                except Exception as e:
                    nick_changed = False
                    nick_error = f"알 수 없는 오류: {str(e)}"
                
                # 성공 임베드 생성
                embed = discord.Embed(
                    title="✅ 관리자 콜사인 설정 완료",
                    description=f"**대상:** {유저.mention}\n"
                            f"**설정된 콜사인:** `{텍스트}`",
                    color=0x00ff00
                )
                
                # 이전 콜사인 정보
                if old_callsign and old_callsign != 텍스트:
                    embed.add_field(
                        name="📋 이전 콜사인",
                        value=f"`{old_callsign}` → `{텍스트}`",
                        inline=True
                    )
                
                # 닉네임 변경 결과
                if nick_changed:
                    embed.add_field(
                        name="👤 닉네임 변경",
                        value=f"✅ `{new_nick}`로 자동 변경됨",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="⚠️ 닉네임 변경 실패",
                        value=f"❌ {nick_error}\n💡 수동으로 닉네임을 `{new_nick}`로 변경해주세요.",
                        inline=False
                    )
                
                # 권한 박탈 상태 경고
                if is_banned:
                    embed.add_field(
                        name="⚠️ 중요 안내",
                        value=f"🚫 **이 사용자는 콜사인 사용이 금지된 상태입니다.**\n"
                            f"**금지 사유:** {ban_info.get('reason', '사유 없음')}\n"
                            f"**금지 일시:** {ban_info.get('banned_at', '알 수 없음')[:19] if ban_info.get('banned_at') else '알 수 없음'}\n"
                            f"✅ 관리자 권한으로 설정되었습니다.",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📌 안내",
                        value="• 관리자 권한으로 설정되어 쿨타임이 적용되지 않습니다.\n"
                            "• 콜사인이 즉시 적용되었습니다.",
                        inline=False
                    )
                
                embed.set_footer(text=f"처리자: {interaction.user.name}")
                embed.timestamp = datetime.datetime.now()

                # followup으로 응답 전송
                await interaction.followup.send(embed=embed, ephemeral=True)

            else:
                # 실패 임베드
                embed = discord.Embed(
                    title="❌ 콜사인 설정 실패",
                    description=f"**대상:** {유저.mention}\n"
                            f"**시도한 콜사인:** `{텍스트}`\n"
                            f"**실패 사유:** {message}",
                    color=0xff0000
                )
                embed.set_footer(text=f"처리자: {interaction.user.name}")
                embed.timestamp = datetime.datetime.now()

                # response로 응답 전송
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # 로그 채널에 기록 (성공한 경우만)
            if success:
                try:
                    from config import config
                    if hasattr(config, 'LOG_CHANNEL_ID') and config.LOG_CHANNEL_ID:
                        log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                        if log_channel:
                            log_embed = discord.Embed(
                                title="🔧 관리자 콜사인 변경",
                                description=f"**대상:** {유저.mention} ({유저.id})\n"
                                        f"**이전 콜사인:** `{old_callsign or '없음'}`\n"
                                        f"**새 콜사인:** `{텍스트}`\n"
                                        f"**처리자:** {interaction.user.mention}\n"
                                        f"**닉네임 변경:** {'성공' if nick_changed else '실패'}\n"
                                        f"**권한 박탈 상태:** {'예' if is_banned else '아니오'}",
                                color=0xffa500 if is_banned else 0x00ff00,
                                timestamp=datetime.datetime.now()
                            )
                            
                            if is_banned and ban_info:
                                log_embed.add_field(
                                    name="⚠️ 금지 정보",
                                    value=f"**사유:** {ban_info.get('reason', '사유 없음')}\n"
                                        f"**금지 일시:** {ban_info.get('banned_at', '알 수 없음')[:19] if ban_info.get('banned_at') else '알 수 없음'}",
                                    inline=False
                                )
                            
                            await log_channel.send(embed=log_embed)
                except Exception as e:
                    print(f"로그 채널 기록 실패: {e}")
                    if LOG_ENABLED and bot_logger:
                        bot_logger.log_error(f"로그 채널 기록 실패: {str(e)}")
        
        elif 기능 == "권한박탈":
            # 관리자 권한 체크
            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ 권한 없음",
                    description="이 기능은 서버 관리자만 사용할 수 있습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if not 유저:
                await interaction.response.send_message("대상 사용자를 지정해주세요.", ephemeral=True)
                return

            reason = 텍스트 or COLLSIGN_BASE_BAN_REASON

            success, message = callsign_manager.ban_user(
                user_id=유저.id,
                banned_by=interaction.user.id,
                reason=reason
            )

            embed = discord.Embed(
                title="⛔ 콜사인 권한 박탈" if success else "⚠️ 권한 박탈 실패",
                description=f"**대상:** {유저.mention}\n**결과:** {message}",
                color=0xff0000 if success else 0xffa500
            )

            if success:
                embed.add_field(
                    name="📝 사유",
                    value=reason,
                    inline=False
                )

                # 현재 콜사인 확인
                current_callsign = callsign_manager.get_callsign(유저.id)
                if current_callsign:
                    embed.add_field(
                        name="ℹ️ 참고",
                        value=f"• 현재 콜사인 `{current_callsign}`은 유지됩니다.\n"
                              f"• 대상 사용자는 더 이상 `/콜사인` 명령어로 콜사인을 변경할 수 없습니다.\n"
                              f"• 관리자는 `/콜사인관리 기능:콜사인_변경`으로 강제 변경할 수 있습니다.",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="ℹ️ 참고",
                        value=f"• 대상 사용자는 `/콜사인` 명령어를 사용할 수 없습니다.\n"
                              f"• 관리자는 `/콜사인관리 기능:콜사인_변경`으로 강제 설정할 수 있습니다.",
                        inline=False
                    )

            embed.set_footer(text=f"처리자: {interaction.user.name}")

            await interaction.response.send_message(embed=embed)

            # 로그 채널에 기록
            try:
                from config import config
                if success and hasattr(config, 'LOG_CHANNEL_ID') and config.LOG_CHANNEL_ID:
                    log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                    if log_channel:
                        current_callsign = callsign_manager.get_callsign(유저.id)
                        log_embed = discord.Embed(
                            title="⛔ 콜사인 권한 박탈",
                            description=f"**대상:** {유저.mention} ({유저.id})\n"
                                       f"**처리자:** {interaction.user.mention}\n"
                                       f"**사유:** {reason}",
                            color=0xff0000,
                            timestamp=datetime.datetime.now()
                        )

                        if current_callsign:
                            log_embed.add_field(
                                name="현재 콜사인",
                                value=f"`{current_callsign}` (유지됨)",
                                inline=False
                            )

                        await log_channel.send(embed=log_embed)
            except:
                pass

        elif 기능 == "권한복구":  # 기존: 권한복구
            # 관리자 권한 체크
            if not interaction.user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ 권한 없음",
                    description="이 기능은 서버 관리자만 사용할 수 있습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if not 유저:
                await interaction.response.send_message("대상 사용자를 지정해주세요.", ephemeral=True)
                return

            success, message = callsign_manager.unban_user(유저.id)
            
            embed = discord.Embed(
                title="✅ 콜사인 권한 복구" if success else "⚠️ 권한 복구 실패",
                description=f"**대상:** {유저.mention}\n**결과:** {message}",
                color=0x00ff00 if success else 0xff0000
            )
            embed.set_footer(text=f"처리자: {interaction.user.name}")
            
            await interaction.response.send_message(embed=embed)
            
            # 로그 채널에 기록
            try:
                from config import config
                if success and hasattr(config, 'LOG_CHANNEL_ID') and config.LOG_CHANNEL_ID:
                    log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="✅ 콜사인 권한 복구",
                            description=f"**대상:** {유저.mention} ({유저.id})\n"
                                       f"**처리자:** {interaction.user.mention}",
                            color=0x00ff00,
                            timestamp=datetime.datetime.now()
                        )
                        await log_channel.send(embed=log_embed)
            except:
                pass
        
        elif 기능 == "권한박탈_목록":  # 기존: 권한박탈_목록
            banned_users = callsign_manager.get_banned_users_list()
            
            if not banned_users:
                embed = discord.Embed(
                    title="📋 콜사인 사용 금지 목록",
                    description="현재 금지된 사용자가 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📋 콜사인 사용 금지 목록",
                    description=f"총 {len(banned_users)}명의 사용자가 금지되어 있습니다.",
                    color=0xff6600
                )
                
                for i, ban_info in enumerate(banned_users[:10], 1):
                    try:
                        user = interaction.guild.get_member(int(ban_info["user_id"]))
                        user_name = user.name if user else f"Unknown ({ban_info['user_id']})"
                    except:
                        user_name = f"Unknown ({ban_info['user_id']})"
                    
                    embed.add_field(
                        name=f"{i}. {user_name}",
                        value=f"**사유:** {ban_info['reason']}\n"
                              f"**일시:** {ban_info['banned_at'][:10] if ban_info.get('banned_at') else '알 수 없음'}",
                        inline=False
                    )
                
                if len(banned_users) > 10:
                    embed.set_footer(text=f"... 외 {len(banned_users) - 10}명")
            
            await interaction.response.send_message(embed=embed)

        elif 기능 == "쿨타임_초기화":
            # 쿨타임 초기화
            if 유저:
                # 특정 유저의 쿨타임만 초기화
                success, message = callsign_manager.reset_cooldown(유저.id)

                embed = discord.Embed(
                    title="⏰ 쿨타임 초기화" if success else "⚠️ 쿨타임 초기화 실패",
                    description=f"**대상:** {유저.mention}\n\n{message}",
                    color=0x00ff00 if success else 0xff9900
                )

                if success:
                    embed.add_field(
                        name="✅ 안내",
                        value=f"{유저.name}님은 이제 즉시 콜사인을 변경할 수 있습니다.",
                        inline=False
                    )
            else:
                # 모든 유저의 쿨타임 초기화
                count = callsign_manager.reset_all_cooldowns()

                embed = discord.Embed(
                    title="⏰ 전체 쿨타임 초기화",
                    description=f"총 **{count}명**의 쿨타임이 초기화되었습니다.",
                    color=0x00ff00
                )

                embed.add_field(
                    name="✅ 안내",
                    value="모든 사용자가 즉시 콜사인을 변경할 수 있습니다.",
                    inline=False
                )

                embed.set_footer(text=f"관리자: {interaction.user.name}")

            await interaction.response.send_message(embed=embed)

        elif 기능 == "전체_목록":  # 기존: 목록
            # 전체 콜사인 목록 표시 - callsigns 속성을 직접 사용
            all_callsigns = {}
            for user_id, info in callsign_manager.callsigns.items():
                if isinstance(info, dict) and "callsign" in info:
                    all_callsigns[user_id] = info["callsign"]
            
            if not all_callsigns:
                embed = discord.Embed(
                    title="📋 전체 콜사인 목록",
                    description="설정된 콜사인이 없습니다.",
                    color=0x2f3136
                )
            else:
                embed = discord.Embed(
                    title="📋 전체 콜사인 목록",
                    description=f"총 {len(all_callsigns)}명이 콜사인을 설정했습니다.",
                    color=0x00bfff
                )
                
                # 페이지네이션을 위해 20개까지만 표시
                display_count = min(20, len(all_callsigns))
                for i, (user_id, callsign) in enumerate(list(all_callsigns.items())[:display_count], 1):
                    try:
                        user = interaction.guild.get_member(int(user_id))
                        user_name = user.name if user else f"Unknown"
                    except:
                        user_name = "Unknown"
                    
                    # 콜사인 정보 가져오기
                    callsign_info = callsign_manager.get_callsign_info(user_id)
                    set_date = "알 수 없음"
                    if callsign_info and "set_at" in callsign_info:
                        set_date = callsign_info["set_at"][:10]  # YYYY-MM-DD만 표시
                    
                    embed.add_field(
                        name=f"{i}. {user_name}",
                        value=f"**콜사인:** `{callsign}`\n**설정일:** {set_date}",
                        inline=True
                    )
                
                if len(all_callsigns) > display_count:
                    embed.set_footer(text=f"... 외 {len(all_callsigns) - display_count}명")
            
            await interaction.response.send_message(embed=embed)
        
        # 백업 관련 기능들
        elif 기능 == "데이터_백업":  # 기존: 백업생성
            await interaction.response.defer()
            
            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(self.bot, 'backup_manager'):
                backup_manager = self.bot.backup_manager
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

                # 백업 파일을 Discord 파일로 업로드
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
        
        elif 기능 == "백업_목록":  # 기존: 백업목록
            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(self.bot, 'backup_manager'):
                backup_manager = self.bot.backup_manager
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
        
        elif 기능 == "데이터_복구":  # 기존: 백업복구
            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(self.bot, 'backup_manager'):
                backup_manager = self.bot.backup_manager
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
        
        elif 기능 == "백업파일_업로드":  # 기존: 백업백업파일_업로드
            # 백업 관리자 가져오기
            backup_manager = None
            if hasattr(self.bot, 'backup_manager'):
                backup_manager = self.bot.backup_manager
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
            
            # 파일 업로드 대기
            def check(m):
                return m.author == interaction.user and m.attachments and m.channel == interaction.channel
            
            try:
                message = await self.bot.wait_for('message', timeout=10.0, check=check)
                
                if message.attachments:
                    attachment = message.attachments[0]
                    
                    if not attachment.filename.endswith('.json'):
                        await interaction.followup.send("❌ JSON 파일만 업로드 가능합니다.")
                        return
                    
                    # 파일 다운로드
                    file_content = await attachment.read()
                    
                    # 복구 실행
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
                    
                    # 업로드된 메시지 삭제
                    try:
                        await message.delete()
                    except:
                        pass
            
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ 시간 초과: 10초 내에 파일을 업로드해주세요.")

    @app_commands.command(name="마을역할", description="마을과 역할을 연동합니다")
    @app_commands.describe(
        기능="수행할 작업을 선택하세요",
        역할="(추가 시만) 연동할 역할을 멘션하거나 역할 ID 입력",
        마을="(추가 시만) 연동할 마을 이름 (정확한 이름 입력)"
    )
    @app_commands.autocomplete(마을=town_autocomplete)
    @app_commands.check(is_admin)
    async def 마을역할(
        self,
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

    @app_commands.command(name="확인", description="자신의 국적을 확인하고 역할을 받습니다")
    async def 확인(self, interaction: discord.Interaction):
        """사용자 본인의 국적 확인 및 역할 부여 - scheduler의 process_single_user 사용"""
        await interaction.response.defer(thinking=True)

        member = interaction.user
        discord_id = member.id

        print(f"🔍 /확인 명령어 시작 - 사용자: {member.display_name} (ID: {discord_id})")

        # scheduler의 process_single_user 함수 import
        try:
            from scheduler import process_single_user
        except ImportError:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ 오류",
                    description="scheduler 모듈을 로드할 수 없습니다.",
                    color=0xff0000
                ),
                ephemeral=True
            )
            return

        # aiohttp 세션 생성 및 처리
        try:
            async with aiohttp.ClientSession() as session:
                result = await process_single_user(interaction.client, session, discord_id)

            # 결과 확인 및 사용자별 메시지 생성
            if result and result.get('success'):
                nation = result.get('nation', 'Unknown')
                town = result.get('town', 'Unknown')
                mc_id = result.get('mc_id', 'Unknown')
                role_changes = result.get('role_changes', [])

                # 국가에 따른 메시지 생성
                if nation == BASE_NATION:
                    embed = discord.Embed(
                        title="✅ 국민 확인 완료",
                        description=f"**``{BASE_NATION}``** 국민으로 확인되었습니다!",
                        color=0x00ff00
                    )
                else:
                    embed = discord.Embed(
                        title="⚠️ 다른 국가 소속",
                        description=f"**``{nation}``** 국가에 소속되어 있습니다.",
                        color=0xff9900
                    )

                # 마인크래프트 정보
                embed.add_field(
                    name="🎮 마인크래프트 정보",
                    value=f"**닉네임:** ``{mc_id}``\n**마을:** ``{town}``\n**국가:** ``{nation}``",
                    inline=False
                )

                # 변경 사항
                if role_changes:
                    changes_text = "\n".join(role_changes[:10])  # 최대 10개
                    embed.add_field(
                        name="🔄 변경 사항",
                        value=changes_text,
                        inline=False
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)
                print(f"🏁 /확인 처리 완료 - {member.display_name}: {nation}/{town}")
            else:
                # 처리 실패
                error_msg = result.get('error', '알 수 없는 오류') if result else '처리 실패'
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ 확인 실패",
                        description=f"{error_msg}",
                        color=0xff0000
                    ),
                    ephemeral=True
                )
                print(f"❌ /확인 처리 실패 - {member.display_name}: {error_msg}")

        except Exception as e:
            print(f"💥 /확인 예외 발생: {e}")
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ 오류 발생",
                    description=f"처리 중 오류가 발생했습니다.\n{str(e)[:100]}",
                    color=0xff0000
                ),
                ephemeral=True
            )

    # /확인 명령어 리팩토링 완료 - 이제 scheduler.process_single_user 사용
    # 이전 코드는 모두 삭제됨

    @app_commands.command(name="마을테스트", description="[관리자] 마을 검증 기능을 테스트합니다")
    @app_commands.describe(마을="테스트할 마을 이름")
    @app_commands.check(is_admin)
    async def 마을테스트(self, interaction: discord.Interaction, 마을: str = None):
        """마을 검증 기능 디버깅"""
        await interaction.response.defer(thinking=True)

        embed = discord.Embed(
            title="🧪 마을 검증 테스트",
            color=0x00ff00
        )

        # (여기에 마을테스트 코드가 계속됨 - 중복 제거를 위해 아래 마을테스트만 유지)
        await interaction.followup.send(embed=discord.Embed(
            title="⚠️ 중복 명령어",
            description="이 명령어는 중복되어 제거될 예정입니다.",
            color=0xffaa00
        ), ephemeral=True)

    @app_commands.command(name="마을테스트", description="[관리자] 마을 검증 기능을 테스트합니다")
    @app_commands.describe(마을="테스트할 마을 이름")
    @app_commands.check(is_admin)
    async def 마을테스트(self, interaction: discord.Interaction, 마을: str = None):
        """마을 검증 기능 디버깅"""
        await interaction.response.defer(thinking=True)
        
        embed = discord.Embed(
            title="🧪 마을 검증 테스트",
            color=0x00ff00
        )
        
        # 기본 정보
        embed.add_field(
            name="🔧 환경 설정",
            value=f"• **TOWN_ROLE_ENABLED**: {TOWN_ROLE_ENABLED}\n"
                  f"• **BASE_NATION**: {BASE_NATION}\n"
                  f"• **MC_API_BASE**: {MC_API_BASE}",
            inline=False
        )
        
        # town_role_manager 상태
        if TOWN_ROLE_ENABLED and town_role_manager:
            try:
                mapping_count = town_role_manager.get_mapping_count()
                embed.add_field(
                    name="🏘️ town_role_manager 상태",
                    value=f"• **상태**: 정상 로드됨\n• **매핑된 마을**: {mapping_count}개",
                    inline=False
                )
            except:
                embed.add_field(
                    name="🏘️ town_role_manager 상태",
                    value="• **상태**: 로드됨 (일부 메서드 사용 불가)",
                    inline=False
                )
        else:
            embed.add_field(
                name="🏘️ town_role_manager 상태",
                value="• **상태**: 로드되지 않음 또는 비활성화",
                inline=False
            )
        
        # 마을 검증 테스트
        if 마을:
            try:
                print(f"🧪 마을 검증 테스트 시작: {마을}")
                is_valid = await verify_town_in_nation(마을, BASE_NATION)
                
                if is_valid:
                    embed.add_field(
                        name="✅ 마을 검증 결과",
                        value=f"• **마을**: {마을}\n"
                              f"• **결과**: **{BASE_NATION}** 소속 ✅\n"
                              f"• **상태**: 연동 가능",
                        inline=False
                    )
                    embed.color = 0x00ff00
                else:
                    embed.add_field(
                        name="❌ 마을 검증 결과",
                        value=f"• **마을**: {마을}\n"
                              f"• **결과**: **{BASE_NATION}** 소속 아님 ❌\n"
                              f"• **상태**: 연동 불가",
                        inline=False
                    )
                    embed.color = 0xff0000
                    
            except Exception as e:
                embed.add_field(
                    name="❌ 마을 검증 실패",
                    value=f"• **마을**: {마을}\n• **오류**: {str(e)[:100]}",
                    inline=False
                )
                embed.color = 0xff0000
        else:
            # 샘플 마을들로 테스트
            test_towns = ["Seoul", "NonExistentTown", "TestTown"]
            test_results = []
            
            for test_town in test_towns:
                try:
                    is_valid = await verify_town_in_nation(test_town, BASE_NATION)
                    status = "✅ 유효" if is_valid else "❌ 무효"
                    test_results.append(f"• **{test_town}**: {status}")
                except Exception as e:
                    test_results.append(f"• **{test_town}**: ❌ 오류 - {str(e)[:30]}")
            
            embed.add_field(
                name="🔍 샘플 마을 테스트",
                value="\n".join(test_results),
                inline=False
            )
        
        # API 테스트
        try:
            async with aiohttp.ClientSession() as session:
                # API 연결 테스트
                url = f"{MC_API_BASE}/nation?name={BASE_NATION}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as response:
                    if response.status == 200:
                        embed.add_field(
                            name="🌐 API 연결 테스트",
                            value=f"• **상태**: ✅ 정상 연결\n• **응답 코드**: HTTP {response.status}",
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="🌐 API 연결 테스트",
                            value=f"• **상태**: ⚠️ 응답 코드 이상\n• **응답 코드**: HTTP {response.status}",
                            inline=False
                        )
        except Exception as e:
            embed.add_field(
                name="🌐 API 연결 테스트",
                value=f"• **상태**: ❌ 연결 실패\n• **오류**: {str(e)[:50]}",
                inline=False
            )
        
        # 해결 방법 제안
        embed.add_field(
            name="💡 사용 방법",
            value="1. `/마을역할 기능:추가 역할:@역할이름 마을:정확한마을이름`\n"
                  "2. 마을 이름은 정확히 입력해야 합니다 (대소문자 구분)\n"
                  "3. 검증 후 **버튼**으로 연동 진행/취소 선택\n"
                  "4. 미검증 마을도 수동 연동 가능\n"
                  "5. 특정 마을 테스트: `/마을테스트 마을:마을이름`",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="테스트", description="봇의 기본 기능을 테스트합니다")
    @app_commands.check(is_admin)
    async def 테스트(self, interaction: discord.Interaction):
        """봇 테스트 명령어"""
        await interaction.response.defer(thinking=True)
        
        embed = discord.Embed(
            title="🧪 봇 테스트 결과",
            color=0x00ff00
        )
        
        # 기본 정보
        embed.add_field(
            name="🤖 봇 정보",
            value=f"**봇 이름:** {self.bot.user.name}\n**핑:** {round(self.bot.latency * 1000)}ms",
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

    @app_commands.command(name="스케줄확인", description="자동 실행 스케줄 정보를 확인합니다")
    @app_commands.check(is_admin)
    async def 스케줄확인(self, interaction: discord.Interaction):
        """스케줄러 상태 확인"""
        try:
            from scheduler import get_scheduler_info
            
            info = get_scheduler_info()
            
            embed = discord.Embed(
                title="📅 자동 실행 스케줄 정보",
                color=0x00ff00 if info["running"] else 0xff0000
            )
            
            # 스케줄러 상태
            status = "🟢 실행 중" if info["running"] else "🔴 중지됨"
            embed.add_field(
                name="⚙️ 스케줄러 상태",
                value=status,
                inline=False
            )
            
            # 자동 실행 설정
            day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            day_name = day_names[info["auto_execution_day"]]
            
            embed.add_field(
                name="🕒 자동 실행 스케줄",
                value=f"**매주 {day_name}** {info['auto_execution_hour']:02d}:{info['auto_execution_minute']:02d}",
                inline=False
            )
            
            # 등록된 작업들
            if info["jobs"]:
                job_list = []
                for job in info["jobs"]:
                    job_list.append(f"• **{job['name']}**\n  다음 실행: {job['next_run']}")
                
                embed.add_field(
                    name="📋 등록된 작업",
                    value="\n\n".join(job_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📋 등록된 작업",
                    value="등록된 작업이 없습니다.",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="scheduler 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 오류 발생",
                description=f"스케줄 정보를 가져오는 중 오류가 발생했습니다.\n{str(e)}",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="자동실행시작", description="자동 역할 부여를 수동으로 시작합니다")
    @app_commands.check(is_admin)
    async def 자동실행시작(self, interaction: discord.Interaction):
        """자동 역할 부여를 수동으로 실행"""
        await interaction.response.defer(thinking=True)
        
        try:
            from scheduler import manual_execute_auto_roles
            
            # 현재 대기열 상태 확인
            current_queue_size = queue_manager.get_queue_size()
            
            embed = discord.Embed(
                title="🚀 자동 역할 실행 시작",
                description="auto_roles.txt 파일의 역할 멤버들을 대기열에 추가하고 있습니다...",
                color=0xffaa00
            )
            
            embed.add_field(
                name="📋 현재 상태",
                value=f"기존 대기열: **{current_queue_size}명**",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # 자동 역할 실행
            result = await manual_execute_auto_roles(self.bot)
            
            if result["success"]:
                embed = discord.Embed(
                    title="✅ 자동 역할 실행 완료",
                    description=result["message"],
                    color=0x00ff00
                )
                
                new_queue_size = queue_manager.get_queue_size()
                
                embed.add_field(
                    name="📊 결과",
                    value=f"• 추가된 사용자: **{result.get('added_count', 0)}명**\n• 현재 대기열: **{new_queue_size}명**",
                    inline=False
                )
                
                if new_queue_size > 0:
                    estimated_time = new_queue_size * 36  # 대략 배치당 36초 추정
                    minutes = estimated_time // 60
                    seconds = estimated_time % 60
                    
                    if minutes > 0:
                        time_str = f"약 {minutes}분 {seconds}초"
                    else:
                        time_str = f"약 {seconds}초"
                    
                    embed.add_field(
                        name="⏰ 예상 완료 시간",
                        value=time_str,
                        inline=False
                    )
            else:
                embed = discord.Embed(
                    title="❌ 자동 역할 실행 실패",
                    description=result["message"],
                    color=0xff0000
                )
            
            # 새로운 메시지로 결과 전송
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except ImportError:
            embed = discord.Embed(
                title="❌ 오류",
                description="scheduler 모듈을 로드할 수 없습니다.",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ 오류 발생",
                description=f"자동 역할 실행 중 오류가 발생했습니다.\n{str(e)}",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="예외설정", description="자동실행 예외 대상을 관리합니다")
    @app_commands.describe(
        기능="수행할 작업을 선택하세요",
        대상="(추가/제거 시만) 유저 멘션 또는 유저 ID"
    )
    @app_commands.check(is_admin)
    async def 예외설정(
        self,
        interaction: discord.Interaction,
        기능: Literal["추가", "제거", "목록"],
        대상: str = None
    ):
        """자동실행 예외 대상 관리"""
        
        if 기능 == "목록":
            # 예외 목록 표시
            exceptions = exception_manager.get_exceptions()
            
            embed = discord.Embed(
                title="📋 자동실행 예외 목록",
                color=0x00bfff
            )
            
            if not exceptions:
                embed.description = "현재 예외 설정된 사용자가 없습니다."
            else:
                embed.description = f"총 **{len(exceptions)}명**이 예외 설정되어 있습니다."
                
                # 10명씩 나누어서 표시
                for i in range(0, len(exceptions), 10):
                    chunk = exceptions[i:i+10]
                    mentions = [f"<@{user_id}>" for user_id in chunk]
                    
                    embed.add_field(
                        name=f"예외 대상 ({i+1}-{min(i+10, len(exceptions))})",
                        value="\n".join(mentions),
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # 추가/제거 시 대상이 필요함
        if not 대상:
            await interaction.response.send_message(
                "❌ 추가/제거 기능을 사용할 때는 대상을 입력해야 합니다.\n"
                "예: `/예외설정 기능:추가 대상:@사용자` 또는 `/예외설정 기능:추가 대상:123456789`",
                ephemeral=True
            )
            return
        
        # 멘션 형식 처리 (< > 제거)
        target_clean = 대상.replace('<@', '').replace('>', '').replace('!', '')
        
        try:
            user_id = int(target_clean)
        except ValueError:
            await interaction.response.send_message(
                "❌ 올바른 사용자 ID 또는 멘션을 입력해주세요.\n"
                "예: `@사용자` 또는 `123456789`",
                ephemeral=True
            )
            return
        
        # 사용자 존재 확인
        guild = interaction.guild
        member = guild.get_member(user_id)
        if not member:
            await interaction.response.send_message(
                f"❌ 사용자를 찾을 수 없습니다. (ID: {user_id})",
                ephemeral=True
            )
            return
        
        if 기능 == "추가":
            if exception_manager.add_exception(user_id):
                embed = discord.Embed(
                    title="✅ 예외 추가 완료",
                    description=f"{member.mention}님을 자동실행 예외 목록에 추가했습니다.",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="⚠️ 이미 예외 설정됨",
                    description=f"{member.mention}님은 이미 예외 목록에 있습니다.",
                    color=0xffaa00
                )
        
        elif 기능 == "제거":
            if exception_manager.remove_exception(user_id):
                embed = discord.Embed(
                    title="✅ 예외 제거 완료",
                    description=f"{member.mention}님을 자동실행 예외 목록에서 제거했습니다.",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title="⚠️ 예외 목록에 없음",
                    description=f"{member.mention}님은 예외 목록에 없습니다.",
                    color=0xffaa00
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="대기열추가", description="유저 또는 역할의 멤버들을 대기열에 추가합니다")
    @app_commands.describe(
        대상="유저 또는 역할을 선택하세요 (자동 감지)"
    )
    @app_commands.check(is_admin)
    async def 대기열추가(
        self,
        interaction: discord.Interaction,
        대상: str
    ):
        """유저 또는 역할을 자동으로 감지하여 대기열에 추가"""
        guild = interaction.guild
        members = []
        target_name = None
        target_type = None

        # 멘션 형식 처리 (< > 제거)
        input_clean = 대상.replace('<@', '').replace('<@&', '').replace('>', '').replace('!', '')

        try:
            input_id = int(input_clean)
        except ValueError:
            await interaction.response.send_message(
                "❌ 올바른 형식을 입력해주세요.\n"
                "**사용법**: `/대기열추가 대상:@유저` 또는 `/대기열추가 대상:@역할`",
                ephemeral=True
            )
            return

        # 유저인지 확인
        member = guild.get_member(input_id)
        if member:
            members.append(member)
            target_name = member.display_name
            target_type = "유저"
        else:
            # 역할인지 확인
            role = guild.get_role(input_id)
            if role:
                members.extend(role.members)
                target_name = role.name
                target_type = "역할"
            else:
                await interaction.response.send_message(
                    "❌ 유저 또는 역할을 찾을 수 없습니다.\n"
                    "올바른 멘션을 사용했는지 확인해주세요.",
                    ephemeral=True
                )
                return

        # 대기열로 처리
        await self._handle_queue_processing(interaction, members, target_type, target_name)

    async def _handle_queue_processing(self, interaction: discord.Interaction, members: list, target_type: str, target_name: str):
        """대기열을 통한 처리"""
        await interaction.response.defer(thinking=True)
        
        added_count = 0
        already_in_queue = 0
        
        # 대기열에 사용자 추가
        for member in members:
            try:
                queue_manager.add_user(member.id)
                added_count += 1
            except:
                already_in_queue += 1
        
        # 결과 메시지 생성
        embed = discord.Embed(
            title="🔄 대기열 추가 완료",
            color=0x00ff00
        )
        
        if target_type == "유저":
            embed.description = f"**{target_name}** 사용자 처리"
        else:
            embed.description = f"**{target_name}** 역할 멤버 {len(members)}명 처리"
        
        embed.add_field(
            name="📋 처리 현황",
            value=f"• 새로 추가: **{added_count}명**\n• 이미 대기 중: **{already_in_queue}명**",
            inline=False
        )
        
        current_queue_size = queue_manager.get_queue_size()
        processing_status = "처리 중" if queue_manager.is_processing() else "대기 중"
        
        embed.add_field(
            name="🎯 대기열 상태",
            value=f"• 총 대기 인원: **{current_queue_size}명**\n• 현재 상태: **{processing_status}**",
            inline=False
        )
        
        if added_count > 0:
            embed.add_field(
                name="⏰ 예상 처리 시간",
                value="1분마다 자동으로 처리되며, 완료 시 결과가 해당 채널에 전송됩니다.",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _handle_immediate_processing(self, interaction: discord.Interaction, members: list, target_type: str, target_name: str):
        """기존 즉시 처리 방식 (API 제한 위험)"""
        await interaction.response.defer(thinking=True)

        not_base_nation = []
        errors = []

        print(f"🔍 /국민확인 명령어 시작 - 대상: {target_type} '{target_name}', 총 {len(members)}명")

        async with aiohttp.ClientSession() as session:
            for idx, member in enumerate(members, 1):
                discord_id = member.id
                print(f"📋 [{idx}/{len(members)}] 처리 중: {member.display_name} (ID: {discord_id})")

                try:
                    # 1단계: 디스코드 ID → 마크 ID
                    url1 = f"{MC_API_BASE}/discord?discord={discord_id}"
                    print(f"  🔗 1단계 API 호출: {url1}")
                    
                    async with session.get(url1, timeout=aiohttp.ClientTimeout(total=10)) as r1:
                        print(f"  📥 1단계 응답: HTTP {r1.status}")
                        if r1.status != 200:
                            error_msg = f"마크ID 조회 실패 ({r1.status})"
                            errors.append(f"{member.mention} - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                        
                        data1 = await r1.json()
                        print(f"  📋 1단계 데이터: {data1}")
                        
                        if not data1.get('data') or not data1['data']:
                            error_msg = "마크ID 데이터 없음"
                            errors.append(f"{member.mention} - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                            
                        mc_id = data1['data'][0].get('name')
                        if not mc_id:
                            error_msg = "마크ID 없음"
                            errors.append(f"{member.mention} - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                        
                        print(f"  ✅ 마크 ID 획득: {mc_id}")
                        time.sleep(5)

                    # 2단계: 마크 ID → 마을
                    url2 = f"{MC_API_BASE}/resident?name={mc_id}"
                    print(f"  🔗 2단계 API 호출: {url2}")
                    
                    async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                        print(f"  📥 2단계 응답: HTTP {r2.status}")
                        if r2.status != 200:
                            error_msg = f"마을 조회 실패 ({r2.status})"
                            errors.append(f"{member.mention} (마크: {mc_id}) - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                            
                        data2 = await r2.json()
                        print(f"  📋 2단계 데이터: {data2}")
                        
                        if not data2.get('data') or not data2['data']:
                            error_msg = "마을 데이터 없음"
                            errors.append(f"{member.mention} (마크: {mc_id}) - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                            
                        town = data2['data'][0].get('town')
                        if not town:
                            error_msg = "마을 없음"
                            errors.append(f"{member.mention} (마크: {mc_id}) - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                        
                        print(f"  ✅ 마을 획득: {town}")
                        time.sleep(5)

                    # 3단계: 마을 → 국가
                    url3 = f"{MC_API_BASE}/town?name={town}"
                    print(f"  🔗 3단계 API 호출: {url3}")
                    
                    async with session.get(url3, timeout=aiohttp.ClientTimeout(total=10)) as r3:
                        print(f"  📥 3단계 응답: HTTP {r3.status}")
                        if r3.status != 200:
                            error_msg = f"국가 조회 실패 ({r3.status})"
                            errors.append(f"{member.mention} (마을: {town}) - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                            
                        data3 = await r3.json()
                        print(f"  📋 3단계 데이터: {data3}")
                        
                        if not data3.get('data') or not data3['data']:
                            error_msg = "국가 데이터 없음"
                            errors.append(f"{member.mention} (마을: {town}) - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                            
                        nation = data3['data'][0].get('nation')
                        if not nation:
                            error_msg = "국가 없음"
                            errors.append(f"{member.mention} (마을: {town}) - {error_msg}")
                            print(f"  ❌ {error_msg}")
                            continue
                        
                        print(f"  ✅ 국가 획득: {nation}")
                        time.sleep(5)

                        if nation != BASE_NATION:
                            not_base_nation.append(f"{member.mention} (국가: {nation}, 마크: {mc_id})")
                            print(f"  ⚠️ 다른 국가 소속: {nation}")
                        else:
                            print(f"  ✅ {BASE_NATION} 국민 확인")

                except Exception as e:
                    error_msg = f"오류 발생: {str(e)[:50]}"
                    errors.append(f"{member.mention} - {error_msg}")
                    print(f"  💥 예외 발생: {e}")

        print(f"🏁 /국민확인 처리 완료 - 총 {len(members)}명 중 다른국가: {len(not_base_nation)}명, 오류: {len(errors)}명")

        # 메시지를 여러 개의 임베드로 분할하여 준비
        embeds_data = []
        
        # 첫 번째 임베드 (기본 응답)
        main_embed = {
            "title": f"🛡️ 국민 확인 결과",
            "color": 0x00bfff,
            "fields": []
        }

        # 대상 정보 추가
        if target_type == "유저":
            description = f"**{target_name}** 사용자 확인 완료"
        else:
            description = f"**{target_name}** 역할 ({len(members)}명) 확인 완료"
        
        main_embed["description"] = description

        # not_base_nation이 있으면 일부를 첫 번째 임베드에 추가
        if not_base_nation:
            display_count = min(10, len(not_base_nation))
            value = "\n".join(not_base_nation[:display_count])
            if len(not_base_nation) > 10:
                value += f"\n...그리고 {len(not_base_nation) - 10}명 더"
            
            main_embed["fields"].append({
                "name": f"⚠️ 다른 국가 소속 ({len(not_base_nation)}명)",
                "value": value,
                "inline": False
            })

        # errors가 있으면 일부를 첫 번째 임베드에 추가
        if errors:
            display_count = min(10, len(errors))
            value = "\n".join(errors[:display_count])
            if len(errors) > 10:
                value += f"\n...그리고 {len(errors) - 10}개 더"
                
            main_embed["fields"].append({
                "name": f"⚠️ 오류 또는 실패 ({len(errors)}명)",
                "value": value,
                "inline": False
            })

        if not main_embed["fields"]:
            main_embed["fields"].append({
                "name": f"✅ {BASE_NATION} 국민 확인 완료",
                "value": f"모든 {len(members)}명이 {BASE_NATION} 소속입니다!",
                "inline": False
            })

        # 첫 번째 응답 전송
        embed = discord.Embed(
            title=main_embed["title"],
            color=main_embed["color"]
        )
        
        if "description" in main_embed:
            embed.description = main_embed["description"]
            
        for field in main_embed["fields"]:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False)
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # 추가 데이터가 있으면 웹훅으로 전송
        # not_base_nation 추가 페이지들
        if len(not_base_nation) > 10:
            for i in range(10, len(not_base_nation), 15):
                chunk = not_base_nation[i:i+15]
                embed_data = {
                    "title": f"⚠️ 다른 국가 소속 (추가 {(i-10)//15 + 1}페이지)",
                    "color": 0xff9900,
                    "fields": [
                        {
                            "name": f"멤버 목록 ({i+1}-{min(i+15, len(not_base_nation))} / {len(not_base_nation)})",
                            "value": "\n".join(chunk),
                            "inline": False
                        }
                    ]
                }
                embeds_data.append(embed_data)

        # errors 추가 페이지들
        if len(errors) > 10:
            for i in range(10, len(errors), 15):
                chunk = errors[i:i+15]
                embed_data = {
                    "title": f"⚠️ 오류 또는 실패 (추가 {(i-10)//15 + 1}페이지)",
                    "color": 0xff0000,
                    "fields": [
                        {
                            "name": f"오류 목록 ({i+1}-{min(i+15, len(errors))} / {len(errors)})",
                            "value": "\n".join(chunk),
                            "inline": False
                        }
                    ]
                }
                embeds_data.append(embed_data)

        # 추가 임베드가 있으면 웹훅으로 전송
        if embeds_data:
            await self.send_long_message_via_webhook(interaction, embeds_data)

    @app_commands.command(name="대기열상태", description="현재 대기열 상태를 확인합니다")
    @app_commands.check(is_admin)
    async def 대기열상태(self, interaction: discord.Interaction):
        """대기열 상태 확인 명령어"""
        queue_size = queue_manager.get_queue_size()
        is_processing = queue_manager.is_processing()
        
        embed = discord.Embed(
            title="📋 대기열 상태",
            color=0x00ff00 if queue_size == 0 else 0xffaa00
        )
        
        embed.add_field(
            name="🎯 현재 대기열",
            value=f"**{queue_size}명** 대기 중",
            inline=True
        )
        
        status_text = "🔄 처리 중" if is_processing else "⏸️ 대기 중"
        embed.add_field(
            name="📊 처리 상태",
            value=status_text,
            inline=True
        )
        
        if queue_size > 0:
            estimated_time = queue_size * 36  # 대략 배치당 36초 추정
            minutes = estimated_time // 60
            seconds = estimated_time % 60
            hours = minutes // 60
            
            if hours > 0:
                minutes = minutes % 60
                time_str = f"약 {hours}시간 {minutes}분 {seconds}초"
            elif minutes > 0:
                time_str = f"약 {minutes}분 {seconds}초"
            else:
                time_str = f"약 {seconds}초"

            embed.add_field(
                name="⏰ 예상 완료 시간",
                value=time_str,
                inline=True
            )
        else:
            embed.add_field(
                name="⏰ 예상 완료 시간",
                value="대기열이 비어있습니다",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="대기열초기화", description="대기열을 모두 비웁니다")
    @app_commands.check(is_admin)
    async def 대기열초기화(self, interaction: discord.Interaction):
        """대기열 초기화 명령어"""
        cleared_count = queue_manager.clear_queue()
        
        embed = discord.Embed(
            title="🧹 대기열 초기화 완료",
            description=f"**{cleared_count}명**이 대기열에서 제거되었습니다.",
            color=0xff6600
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="자동실행", description="자동 등록할 역할을 설정")
    @app_commands.describe(역할id="역할 ID")
    @app_commands.check(is_admin)
    async def 자동실행(self, interaction: discord.Interaction, 역할id: str):
        try:
            # 역할 ID 검증
            try:
                role_id_int = int(역할id)
            except ValueError:
                await interaction.response.send_message("❌ 유효하지 않은 역할 ID입니다. 숫자를 입력해주세요.", ephemeral=True)
                return

            # 역할 존재 확인
            role = interaction.guild.get_role(role_id_int)
            if not role:
                await interaction.response.send_message(f"❌ 역할을 찾을 수 없습니다 (ID: {역할id})", ephemeral=True)
                return

            # auto_role_manager를 통해 추가
            from role_manager import auto_role_manager

            # 이미 추가되어 있는지 확인
            if auto_role_manager.has_role(role_id_int):
                await interaction.response.send_message(
                    f"⚠️ {role.mention}은(는) 이미 자동실행 목록에 있습니다.",
                    ephemeral=True
                )
                return

            # 역할 추가
            success = auto_role_manager.add_role(role_id_int)

            if success:
                embed = discord.Embed(
                    title="✅ 자동실행 역할 추가 완료",
                    description=f"**역할:** {role.mention}\n"
                               f"**역할 ID:** `{역할id}`\n"
                               f"**멤버 수:** {len(role.members)}명",
                    color=0x00ff00
                )
                embed.add_field(
                    name="📊 자동실행 목록 현황",
                    value=f"총 {auto_role_manager.get_count()}개 역할이 자동실행 목록에 있습니다.",
                    inline=False
                )
                embed.add_field(
                    name="💡 안내",
                    value="• 역할이 즉시 적용되었습니다. 재시작이 필요 없습니다.\n"
                         "• 다음 자동 스케줄 실행 시 이 역할의 멤버들이 자동으로 처리됩니다.\n"
                         "• `/자동실행시작` 명령어로 즉시 실행할 수 있습니다.",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ 역할 추가에 실패했습니다.", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {str(e)}", ephemeral=True)

    # 로그 관리 명령어들

    @app_commands.command(name="로그조회", description="시스템 로그를 조회합니다")
    @app_commands.describe(
        범위="조회할 로그 범위",
        카테고리="로그 카테고리 필터",
        사용자="특정 사용자의 로그만 조회",
        날짜="특정 날짜 (YYYY-MM-DD 형식)"
    )
    @app_commands.check(is_admin)
    async def 로그조회(
        self,
        interaction: discord.Interaction,
        범위: Literal["최근", "오늘", "어제", "특정날짜", "사용자활동"] = "최근",
        카테고리: Optional[Literal["콜사인", "대기열", "동맹", "역할", "예외처리", "스케줄러", "시스템", "관리자"]] = None,
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
            
            # 카테고리 매핑
            category_map = {
                "콜사인": LogCategory.CALLSIGN,
                "대기열": LogCategory.QUEUE,
                "동맹": LogCategory.ALLIANCE,
                "역할": LogCategory.ROLE,
                "예외처리": LogCategory.EXCEPTION,
                "스케줄러": LogCategory.SCHEDULER,
                "시스템": LogCategory.SYSTEM,
                "관리자": LogCategory.ADMIN
            }
            
            selected_category = category_map.get(카테고리) if 카테고리 else None
            
            # 로그 조회
            if 범위 == "최근":
                logs = log_manager.get_recent_logs(count=50, category=selected_category)
            elif 범위 == "오늘":
                today = datetime.now().strftime('%Y-%m-%d')
                logs = log_manager.get_logs_by_date(today, category=selected_category)
            elif 범위 == "어제":
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                logs = log_manager.get_logs_by_date(yesterday, category=selected_category)
            elif 범위 == "특정날짜":
                if not 날짜:
                    await interaction.followup.send("특정날짜를 선택한 경우 날짜를 입력해주세요. (예: 2024-01-15)", ephemeral=True)
                    return
                try:
                    datetime.strptime(날짜, '%Y-%m-%d')  # 날짜 형식 검증
                    logs = log_manager.get_logs_by_date(날짜, category=selected_category)
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
            current_page = 1
            
            def create_log_embed(page: int):
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                page_logs = logs[start_idx:end_idx]
                
                embed = discord.Embed(
                    title="📋 로그 조회 결과",
                    description=f"총 {len(logs)}개 로그 중 {start_idx + 1}-{min(end_idx, len(logs))}번째",
                    color=0x00AE86
                )
                
                for i, log in enumerate(page_logs, start_idx + 1):
                    # 레벨에 따른 이모지
                    level_emoji = {
                        "INFO": "ℹ️",
                        "WARNING": "⚠️",
                        "ERROR": "❌",
                        "ADMIN": "🔧",
                        "AUTO": "🤖",
                        "SYSTEM": "⚙️"
                    }
                    
                    emoji = level_emoji.get(log['level'], "📝")
                    
                    field_name = f"{emoji} {log['time']} | {log['category']}"
                    
                    field_value = f"**{log['message']}**\n"
                    if log['user_name']:
                        field_value += f"👤 {log['user_name']}"
                        if log['command']:
                            field_value += f" | 🔸 {log['command']}"
                    if log['target_user_name']:
                        field_value += f"\n🎯 대상: {log['target_user_name']}"
                    
                    embed.add_field(
                        name=field_name,
                        value=field_value,
                        inline=False
                    )
                
                embed.set_footer(text=f"페이지 {page}/{total_pages} | 조회자: {interaction.user.name}")
                embed.timestamp = datetime.now()
                
                return embed
            
            # 첫 번째 페이지 표시
            embed = create_log_embed(current_page)
            
            if total_pages > 1:
                # 페이지 네비게이션 버튼 추가
                view = LogPaginationView(logs, page_size, interaction.user.id)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except ImportError:
            await interaction.followup.send("❌ 로그 관리 시스템이 로드되지 않았습니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 로그 조회 중 오류가 발생했습니다: {str(e)}", ephemeral=True)

    @app_commands.command(name="로그관리", description="로그 시스템 관리 기능")
    @app_commands.describe(
        기능="수행할 관리 기능",
        날짜="시작 날짜 (YYYY-MM-DD)",
        종료날짜="종료 날짜 (YYYY-MM-DD)",
        보관기간="로그 보관 기간 (일)"
    )
    @app_commands.check(is_admin)
    async def 로그관리(
        self,
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
                today = datetime.now().strftime('%Y-%m-%d')
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                
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
                embed.timestamp = datetime.now()
                
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
                    datetime.strptime(날짜, '%Y-%m-%d')
                    datetime.strptime(종료날짜, '%Y-%m-%d')
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
                    embed.timestamp = datetime.now()
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ 로그 내보내기에 실패했습니다.", ephemeral=True)
                    
            elif 기능 == "백업":
                # 현재 로그 백업
                today = datetime.now().strftime('%Y-%m-%d')
                backup_path = log_manager.export_logs(today, today, 'json')
                
                if backup_path:
                    # 백업 디렉토리로 이동
                    backup_dir = os.path.join(log_manager.log_dir, "backups")
                    if not os.path.exists(backup_dir):
                        os.makedirs(backup_dir)
                    
                    backup_filename = f"backup_{today}_{datetime.now().strftime('%H%M%S')}.json"
                    final_backup_path = os.path.join(backup_dir, backup_filename)
                    
                    import shutil
                    shutil.move(backup_path, final_backup_path)
                    
                    embed = discord.Embed(
                        title="💾 로그 백업 완료",
                        description=f"**날짜:** {today}\n"
                                f"**파일:** `{backup_filename}`\n"
                                f"**경로:** `{final_backup_path}`",
                        color=0x00ff00
                    )
                    embed.set_footer(text=f"처리자: {interaction.user.name}")
                    embed.timestamp = datetime.now()
                    
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
                field_name = f"{emoji} {log['time']} | {log['category']}"
                
                field_value = f"**{log['message']}**\n"
                if log['user_name']:
                    field_value += f"👤 {log['user_name']}"
                    if log['command']:
                        field_value += f" | 🔸 {log['command']}"
                if log['target_user_name']:
                    field_value += f"\n🎯 대상: {log['target_user_name']}"
                
                embed.add_field(
                    name=field_name,
                    value=field_value,
                    inline=False
                )
            
            embed.set_footer(text=f"페이지 {page}/{self.total_pages}")
            embed.timestamp = datetime.now()
            
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

    # 데이터베이스 사용자 목록 페이지네이션 View
    class DatabasePaginationView(discord.ui.View):
        def __init__(self, all_users: list, guild: discord.Guild, user_id: int, page_size: int = 20):
            super().__init__(timeout=300)
            self.all_users = all_users
            self.guild = guild
            self.user_id = user_id
            self.page_size = page_size
            self.current_page = 1
            self.total_pages = (len(all_users) + page_size - 1) // page_size

            # 페이지가 1개면 버튼 비활성화
            if self.total_pages <= 1:
                self.clear_items()

        def create_embed(self, page: int):
            start_idx = (page - 1) * self.page_size
            end_idx = start_idx + self.page_size
            page_users = self.all_users[start_idx:end_idx]

            embed = discord.Embed(
                title="👥 전체 사용자 목록",
                description=f"총 {len(self.all_users)}명 중 {start_idx + 1}-{min(end_idx, len(self.all_users))}번째",
                color=0x3498db
            )

            for i, user in enumerate(page_users, start_idx + 1):
                member = self.guild.get_member(int(user['discord_id']))
                member_name = member.name if member else f"Unknown"

                embed.add_field(
                    name=f"{i}. {member_name}",
                    value=f"**MC:** `{user['current_minecraft_name']}`\n"
                          f"**UUID:** `{user['minecraft_uuid']}`\n"
                          f"**업데이트:** {user['last_updated'][:10]}",
                    inline=True
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
                cutoff_date = datetime.now() - timedelta(days=self.days_to_keep)
                
                for filename in os.listdir(log_dir):
                    if filename.startswith(('bot_', 'logs_')) and filename.endswith(('.log', '.json')):
                        try:
                            if filename.startswith('bot_'):
                                date_part = filename[4:14]
                            else:
                                date_part = filename[5:15]
                            
                            file_date = datetime.strptime(date_part, '%Y-%m-%d')
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
                embed.timestamp = datetime.now()
                
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

    # 에러 핸들러
    @확인.error
    @테스트.error
    @마을테스트.error
    @스케줄확인.error
    @자동실행시작.error
    @예외설정.error
    @대기열상태.error
    @대기열초기화.error
    @자동실행.error
    async def command_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """명령어 에러 처리"""
        try:
            if isinstance(error, app_commands.CheckFailure):
                embed = discord.Embed(
                    title="❌ 권한 없음",
                    description="이 명령어를 사용할 권한이 없습니다.",
                    color=discord.Color.red()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ 오류 발생",
                    description=f"명령어 실행 중 오류가 발생했습니다.\n```{str(error)}```",
                    color=discord.Color.red()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error handler failed: {e}")

    @app_commands.command(name="데이터베이스", description="데이터베이스 조회 및 관리 (관리자 전용)")
    @app_commands.describe(
        기능="실행할 기능 선택",
        유저="조회할 사용자 (선택)",
        닉네임="검색할 Minecraft 닉네임 (선택)"
    )
    @app_commands.check(is_admin)
    async def 데이터베이스(
        self,
        interaction: discord.Interaction,
        기능: Literal["사용자_조회", "닉네임_검색", "통계", "전체_사용자"],
        유저: discord.Member = None,
        닉네임: str = None
    ):
        """데이터베이스 조회 및 관리 - 관리자 전용"""

        if not DATABASE_ENABLED or not db_manager:
            embed = discord.Embed(
                title="❌ 기능 비활성화",
                description="데이터베이스 기능이 비활성화되어 있습니다.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if 기능 == "사용자_조회":
            if not 유저:
                await interaction.response.send_message("조회할 사용자를 지정해주세요.", ephemeral=True)
                return

            user_info = db_manager.get_user_info(유저.id)
            name_history = db_manager.get_name_history(유저.id, limit=10)

            if not user_info:
                embed = discord.Embed(
                    title="❌ 사용자 정보 없음",
                    description=f"{유저.mention}의 정보가 데이터베이스에 없습니다.",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            embed = discord.Embed(
                title=f"💾 사용자 데이터베이스 정보",
                description=f"**사용자:** {유저.mention}",
                color=0x00bfff
            )

            embed.add_field(
                name="🎮 Minecraft 정보",
                value=f"**현재 닉네임:** `{user_info['current_minecraft_name']}`\n"
                      f"**UUID:** `{user_info['minecraft_uuid']}`",
                inline=False
            )

            embed.add_field(
                name="📅 기록",
                value=f"**첫 기록:** {user_info['first_seen'][:19]}\n"
                      f"**최근 업데이트:** {user_info['last_updated'][:19]}",
                inline=False
            )

            if name_history:
                history_text = "\n".join([
                    f"{i+1}. `{h['minecraft_name']}` - {h['changed_at'][:19]}"
                    for i, h in enumerate(name_history[:5])
                ])
                embed.add_field(
                    name=f"📝 닉네임 히스토리 (최근 5개)",
                    value=history_text or "히스토리 없음",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)

        elif 기능 == "닉네임_검색":
            if not 닉네임:
                await interaction.response.send_message("검색할 Minecraft 닉네임을 입력해주세요.", ephemeral=True)
                return

            results = db_manager.search_by_minecraft_name(닉네임)

            if not results:
                embed = discord.Embed(
                    title="🔍 검색 결과 없음",
                    description=f"`{닉네임}`와(과) 일치하는 사용자를 찾을 수 없습니다.",
                    color=0xff6600
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # 검색 결과가 1명인 경우 - 사용자_조회처럼 자세한 정보 표시
            if len(results) == 1:
                user = results[0]
                member = interaction.guild.get_member(int(user['discord_id']))
                name_history = db_manager.get_name_history(int(user['discord_id']), limit=10)

                embed = discord.Embed(
                    title=f"💾 사용자 데이터베이스 정보",
                    description=f"**사용자:** {member.mention if member else f'Unknown ({user['discord_id']})'}",
                    color=0x00bfff
                )

                embed.add_field(
                    name="🎮 Minecraft 정보",
                    value=f"**현재 닉네임:** `{user['current_minecraft_name']}`\n"
                          f"**UUID:** `{user['minecraft_uuid']}`",
                    inline=False
                )

                embed.add_field(
                    name="📅 기록",
                    value=f"**첫 기록:** {user['first_seen'][:19] if user.get('first_seen') else 'N/A'}\n"
                          f"**최근 업데이트:** {user['last_updated'][:19] if user.get('last_updated') else 'N/A'}",
                    inline=False
                )

                if name_history:
                    history_text = "\n".join([
                        f"{i+1}. `{h['minecraft_name']}` - {h['changed_at'][:19]}"
                        for i, h in enumerate(name_history[:5])
                    ])
                    embed.add_field(
                        name=f"📝 닉네임 히스토리 (최근 5개)",
                        value=history_text or "히스토리 없음",
                        inline=False
                    )

                embed.set_footer(text=f"검색어: {닉네임}")
                await interaction.response.send_message(embed=embed)

            # 검색 결과가 여러 명인 경우 - 목록 형태로 표시
            else:
                embed = discord.Embed(
                    title=f"🔍 닉네임 검색 결과",
                    description=f"**검색어:** `{닉네임}`\n**발견:** {len(results)}명",
                    color=0x00ff00,
                    timestamp=datetime.datetime.now()
                )

                for i, user in enumerate(results[:10], 1):
                    member = interaction.guild.get_member(int(user['discord_id']))
                    member_name = member.mention if member else f"Unknown User"
                    discord_id = user['discord_id']

                    # 닉네임 히스토리 개수 확인
                    name_history = db_manager.get_name_history(int(discord_id), limit=1)
                    history_count = len(db_manager.get_name_history(int(discord_id), limit=100))

                    value_text = f"**Discord:** {member_name} (`{discord_id}`)\n"
                    value_text += f"**현재 닉네임:** `{user['current_minecraft_name']}`\n"
                    value_text += f"**UUID:** `{user['minecraft_uuid']}`\n"

                    if user.get('last_updated'):
                        value_text += f"**최근 업데이트:** {user['last_updated'][:19]}\n"

                    if history_count > 1:
                        value_text += f"**닉네임 변경:** {history_count}회"

                    embed.add_field(
                        name=f"{i}. 사용자 정보",
                        value=value_text,
                        inline=False
                    )

                if len(results) > 10:
                    embed.set_footer(text=f"10명까지 표시 중 (총 {len(results)}명)")
                else:
                    embed.set_footer(text=f"총 {len(results)}명")

                await interaction.response.send_message(embed=embed)

        elif 기능 == "통계":
            stats = db_manager.get_statistics()

            embed = discord.Embed(
                title="📊 데이터베이스 통계",
                description="Minecraft 사용자 데이터 통계",
                color=0x9b59b6
            )

            embed.add_field(
                name="📈 전체 통계",
                value=f"**총 사용자:** {stats['total_users']}명\n"
                      f"**총 닉네임 변경:** {stats['total_name_changes']}회\n"
                      f"**최근 24시간 업데이트:** {stats['recent_updates']}명",
                inline=False
            )

            if stats.get('top_changers'):
                top_text = []
                for i, changer in enumerate(stats['top_changers'][:5], 1):
                    member = interaction.guild.get_member(int(changer['discord_id']))
                    member_name = member.mention if member else f"Unknown"
                    top_text.append(f"{i}. {member_name} - {changer['change_count']}회")

                embed.add_field(
                    name="🏆 닉네임 변경 Top 5",
                    value="\n".join(top_text) or "데이터 없음",
                    inline=False
                )

            embed.timestamp = datetime.datetime.now()
            await interaction.response.send_message(embed=embed)

        elif 기능 == "전체_사용자":
            await interaction.response.defer()

            # 모든 사용자 조회 (limit 없이)
            all_users = db_manager.get_all_users()

            if not all_users:
                embed = discord.Embed(
                    title="❌ 데이터 없음",
                    description="데이터베이스에 사용자 정보가 없습니다.",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed)
                return

            # 페이지네이션 View 생성
            view = self.DatabasePaginationView(
                all_users=all_users,
                guild=interaction.guild,
                user_id=interaction.user.id,
                page_size=20
            )

            # 첫 페이지 임베드 생성
            embed = view.create_embed(page=1)

            await interaction.followup.send(embed=embed, view=view)

    @도움말.error
    @마을역할.error
    @콜사인.error
    @콜사인관리.error
    @동맹설정.error
    @국가설정.error
    @동맹확인.error
    @데이터베이스.error
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        # 이미 응답된 상호작용인지 확인
        if interaction.response.is_done():
            # 이미 응답된 경우 followup 사용
            try:
                if isinstance(error, app_commands.CheckFailure):
                    await interaction.followup.send("🚫 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
                else:
                    await interaction.followup.send(f"❗ 오류 발생: `{str(error)}`", ephemeral=True)
            except:
                # followup도 실패하면 콘솔에만 출력
                print(f"Error handling failed: {error}")
        else:
            # 아직 응답하지 않은 경우 response 사용
            try:
                if isinstance(error, app_commands.CheckFailure):
                    await interaction.response.send_message("🚫 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❗ 오류 발생: `{str(error)}`", ephemeral=True)
            except:
                print(f"Error response failed: {error}")

async def setup(bot):
    await bot.add_cog(SlashCommands(bot))