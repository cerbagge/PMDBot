from datetime import datetime, timezone, timedelta
import discord
from discord.ext import tasks
import aiohttp
import asyncio
import os
import time
import re
import csv

from queue_manager import queue_manager
from exception_manager import exception_manager
from utils import format_estimated_time, format_duration, format_time_until

# database_manager import (데이터베이스 기능)
try:
    from database_manager import db_manager
    print("✅ database_manager에서 db_manager 로드됨 (scheduler.py)")
    DATABASE_ENABLED = True
except ImportError:
    print("⚠️ database_manager를 찾을 수 없습니다. 데이터베이스 기능이 비활성화됩니다.")
    db_manager = None
    DATABASE_ENABLED = False

# auto_role_manager import (role_manager.py에서 가져오기 시도)
try:
    from role_manager import auto_role_manager
    print("✅ role_manager에서 auto_role_manager 로드됨 (scheduler.py)")
except ImportError:
    try:
        # auto_roles.txt 파일을 직접 읽는 방식으로 대체
        print("⚠️ auto_role_manager를 찾을 수 없어 기본 방식을 사용합니다.")
        
        class SimpleAutoRoleManager:
            def get_roles(self):
                try:
                    if os.path.exists("auto_roles.txt"):
                        with open("auto_roles.txt", 'r') as f:
                            roles = []
                            for line in f:
                                line = line.strip()
                                if line.isdigit():
                                    roles.append(int(line))
                            return roles
                    return []
                except Exception as e:
                    print(f"❌ 역할 파일 읽기 실패: {e}")
                    return []
        
        auto_role_manager = SimpleAutoRoleManager()
        print("✅ 간단한 자동역할 관리자 생성됨 (scheduler.py)")
        
    except Exception as e:
        print(f"❌ 자동역할 기능을 사용할 수 없습니다: {e}")
        auto_role_manager = None

# town_role_manager 안전하게 import
try:
    from town_role_manager import town_role_manager
    print("✅ town_role_manager 모듈 로드됨 (scheduler.py)")
    TOWN_ROLE_ENABLED = True
except ImportError as e:
    print(f"⚠️ town_role_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    print("📝 마을 역할 기능이 비활성화됩니다.")
    town_role_manager = None
    TOWN_ROLE_ENABLED = False

# callsign_manager 안전하게 import
try:
    from callsign_manager import callsign_manager
    print("✅ callsign_manager 모듈 로드됨 (scheduler.py)")
    CALLSIGN_ENABLED = True
except ImportError as e:
    print(f"⚠️ callsign_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    print("📝 콜사인 기능이 비활성화됩니다.")
    callsign_manager = None
    CALLSIGN_ENABLED = False

# config.py에서 환경변수 가져오기 - SUCCESS_ROLE_ID_OUT 추가
try:
    from config import config
    MC_API_BASE = config.MC_API_BASE
    BASE_NATION = config.BASE_NATION
    SUCCESS_ROLE_ID = config.SUCCESS_ROLE_ID
    SUCCESS_ROLE_ID_OUT = getattr(config, 'SUCCESS_ROLE_ID_OUT', 0)  # 외국인 역할 ID
    SUCCESS_CHANNEL_ID = config.SUCCESS_CHANNEL_ID
    FAILURE_CHANNEL_ID = config.FAILURE_CHANNEL_ID
    AUTO_EXECUTION_DAY = config.AUTO_EXECUTION_DAY
    AUTO_EXECUTION_HOUR = config.AUTO_EXECUTION_HOUR
    AUTO_EXECUTION_MINUTE = config.AUTO_EXECUTION_MINUTE
    print("✅ scheduler.py: config.py에서 환경변수 로드 완료")
    print(f"  - SUCCESS_ROLE_ID: {SUCCESS_ROLE_ID}")
    print(f"  - SUCCESS_ROLE_ID_OUT: {SUCCESS_ROLE_ID_OUT}")
except ImportError:
    # config.py가 없으면 직접 환경변수 로드
    print("⚠️ config.py를 찾을 수 없어 직접 환경변수를 로드합니다.")
    MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")
    BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")
    SUCCESS_ROLE_ID = int(os.getenv("SUCCESS_ROLE_ID", "0"))
    SUCCESS_ROLE_ID_OUT = int(os.getenv("SUCCESS_ROLE_ID_OUT", "0"))  # 외국인 역할 ID
    SUCCESS_CHANNEL_ID = int(os.getenv("SUCCESS_CHANNEL_ID", "0"))
    FAILURE_CHANNEL_ID = int(os.getenv("FAILURE_CHANNEL_ID", "0"))
    AUTO_EXECUTION_DAY = int(os.getenv("AUTO_EXECUTION_DAY", "2"))
    AUTO_EXECUTION_HOUR = int(os.getenv("AUTO_EXECUTION_HOUR", "3"))
    AUTO_EXECUTION_MINUTE = int(os.getenv("AUTO_EXECUTION_MINUTE", "24"))
    print(f"✅ scheduler.py: 직접 환경변수 로드 완료")
    print(f"  - SUCCESS_ROLE_ID: {SUCCESS_ROLE_ID}")
    print(f"  - SUCCESS_ROLE_ID_OUT: {SUCCESS_ROLE_ID_OUT}")

# 스케줄러 인스턴스
# 봇 인스턴스 참조 저장
_bot_instance = None

# 429 오류 관리를 위한 전역 변수들
rate_limit_detected = False  # 429 오류 감지 상태
rate_limit_until = None      # 제한 해제 예상 시간
retry_counts = {}            # 사용자별 재시도 횟수 추적
MAX_RETRY_COUNT = 3          # 최대 재시도 횟수

try:
    from alliance_manager import alliance_manager, is_friendly_nation, create_nation_role_if_needed
    print("✅ alliance_manager 모듈 로드됨 (scheduler.py)")
    ALLIANCE_ENABLED = True
except ImportError as e:
    print(f"⚠️ alliance_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    alliance_manager = None
    ALLIANCE_ENABLED = False

try:
    from nation_role_manager import nation_role_manager
    print("✅ nation_role_manager 모듈 로드됨 (scheduler.py)")
    NATION_ROLE_ENABLED = True
except ImportError as e:
    print(f"⚠️ nation_role_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    nation_role_manager = None
    NATION_ROLE_ENABLED = False

# update_user_info 함수 전체 (기존 함수를 완전히 대체)

async def update_user_info(member, mc_id, nation, guild, town=None, nation_uuid=None, town_uuid=None):
    """
    사용자 정보 업데이트 (역할, 닉네임) - UUID 기반 국가 역할 자동 생성 및 동맹 처리

    Args:
        member: Discord 멤버
        mc_id: Minecraft ID (닉네임)
        nation: 국가 이름
        guild: Discord 길드
        town: 마을 이름 (선택)
        nation_uuid: 국가 UUID (선택, 우선순위 높음)
        town_uuid: 마을 UUID (선택)
    """
    changes = []
    
    try:
        # 새 닉네임 생성 (기존 닉네임을 고려하여)
        current_nickname = member.display_name
        new_nickname = create_nickname(mc_id, nation, current_nickname)
        
        try:
            if current_nickname != new_nickname:
                await member.edit(nick=new_nickname)
                changes.append(f"• 닉네임이 **``{new_nickname}``**로 변경됨")
                print(f"  ✅ 닉네임 변경: {current_nickname} → {new_nickname}")
            else:
                print(f"  ℹ️ 닉네임 유지: {new_nickname}")
        except discord.Forbidden:
            changes.append("• ⚠️ 닉네임 변경 권한 없음")
            print(f"  ⚠️ 닉네임 변경 권한 없음")
        except Exception as e:
            changes.append(f"• ⚠️ 닉네임 변경 실패: {str(e)[:50]}")
            print(f"  ⚠️ 닉네임 변경 실패: {e}")

        # 매핑된 마을 역할 처리 (무소속 제외)
        if TOWN_ROLE_ENABLED and town_role_manager:
            try:
                # 1. 먼저 기존 마을 역할들을 모두 제거
                all_mapped_towns = town_role_manager.get_all_mappings()
                for mapped_town, mapped_role_id in all_mapped_towns.items():
                    if mapped_town != town:  # 현재 마을이 아닌 역할들만
                        mapped_role = guild.get_role(mapped_role_id)
                        if mapped_role and mapped_role in member.roles:
                            await member.remove_roles(mapped_role)
                            changes.append(f"• **`{mapped_town}`** 마을 역할 제거됨 (마을 변경)")
                            print(f"  ✅ 이전 마을 역할 제거: {mapped_town}")

                # 2. 새 마을 역할 부여 (무소속이 아닌 경우)
                if town and town != "무소속" and town != "❌":
                    role_id = town_role_manager.get_role_id(town)
                    if role_id:
                        town_role = guild.get_role(role_id)
                        if town_role:
                            if town_role not in member.roles:
                                await member.add_roles(town_role)
                                changes.append(f"• **`{town}`** 마을 역할 추가됨")
                                print(f"  ✅ 매핑된 마을 역할 부여: {town}")
                            else:
                                print(f"  ℹ️ 이미 마을 역할 보유: {town}")
                        else:
                            changes.append(f"• ⚠️ 마을 역할을 찾을 수 없음 (ID: {role_id})")
                            print(f"  ⚠️ 마을 역할 없음: {role_id}")
                    else:
                        print(f"  ℹ️ `{town}` 마을은 역할이 매핑되지 않음")
                elif town == "무소속" or town == "❌":
                    print(f"  ℹ️ 무소속/정보없음 사용자 - 마을 역할 모두 제거됨")

            except Exception as e:
                changes.append(f"• ⚠️ 마을 역할 처리 실패: {str(e)[:50]}")
                print(f"  ⚠️ 마을 역할 처리 실패: {e}")
        elif town and not TOWN_ROLE_ENABLED:
            print(f"  ℹ️ `{town}` 마을 - 마을 역할 기능 비활성화됨")

        # 국가별 역할 부여 (UUID 기반 로직)
        try:
            from config import config
            from alliance_manager import is_friendly_nation as check_friendly

            base_nation = getattr(config, 'BASE_NATION', 'Red_Mafia')
            base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)
        except:
            base_nation = 'Red_Mafia'
            base_nation_uuid = None

        # 우호 국가 확인 (UUID 우선, 이름 fallback)
        is_base_nation = False
        is_alliance_nation = False

        if nation_uuid and base_nation_uuid:
            # UUID 기반 비교 (우선)
            is_base_nation = (nation_uuid == base_nation_uuid)
            if ALLIANCE_ENABLED and alliance_manager:
                is_alliance_nation = alliance_manager.is_alliance_uuid(nation_uuid)
        else:
            # 이름 기반 비교 (fallback)
            is_base_nation = (nation == base_nation)
            if ALLIANCE_ENABLED and alliance_manager:
                is_alliance_nation = alliance_manager.is_alliance_name(nation)

        is_friendly = is_base_nation or is_alliance_nation

        # 디버그 로그
        if nation_uuid:
            print(f"  🔍 UUID 기반 국가 확인: {nation} (UUID: {nation_uuid[:8]}...)")
        else:
            print(f"  🔍 이름 기반 국가 확인: {nation} (UUID 없음)")
        
        if is_friendly:
            # 우호 국가 (기본 국가 또는 동맹 국가)
            if is_base_nation:
                print(f"  🏠 {base_nation} 기본 국가 국민 확인됨")
            else:
                print(f"  🤝 {nation} 동맹 국가 국민 확인됨")
            
            # 국민 역할 부여
            if SUCCESS_ROLE_ID != 0:
                success_role = guild.get_role(SUCCESS_ROLE_ID)
                if success_role:
                    if success_role not in member.roles:
                        try:
                            await member.add_roles(success_role)
                            changes.append(f"• **{success_role.name}** 역할 추가됨")
                            print(f"  ✅ 국민 역할 부여: {success_role.name}")
                        except Exception as e:
                            changes.append(f"• ⚠️ 국민 역할 부여 실패: {str(e)[:50]}")
                            print(f"  ⚠️ 국민 역할 부여 실패: {e}")
                    else:
                        print(f"  ℹ️ 이미 국민 역할 보유: {success_role.name}")
                else:
                    print(f"  ⚠️ 국민 역할을 찾을 수 없음 (ID: {SUCCESS_ROLE_ID})")
            
            # 외국인 역할 제거
            if SUCCESS_ROLE_ID_OUT != 0:
                out_role = guild.get_role(SUCCESS_ROLE_ID_OUT)
                if out_role and out_role in member.roles:
                    try:
                        await member.remove_roles(out_role)
                        changes.append(f"• **{out_role.name}** 역할 제거됨")
                        print(f"  ✅ 외국인 역할 제거: {out_role.name}")
                    except Exception as e:
                        changes.append(f"• ⚠️ 외국인 역할 제거 실패: {str(e)[:50]}")
                        print(f"  ⚠️ 외국인 역할 제거 실패: {e}")
            
            # 동맹 국가인 경우 국가별 역할도 부여
            if is_alliance_nation and nation != "무소속":
                try:
                    # 국가 역할이 없으면 자동 생성
                    nation_role = await create_nation_role_if_needed(guild, nation)
                    
                    if nation_role:
                        if nation_role not in member.roles:
                            await member.add_roles(nation_role)
                            changes.append(f"• **{nation_role.name}** 국가 역할 추가됨")
                            print(f"  ✅ 동맹 국가 역할 부여: {nation_role.name}")
                        else:
                            print(f"  ℹ️ 이미 국가 역할 보유: {nation_role.name}")
                    else:
                        changes.append(f"• ⚠️ {nation} 국가 역할 생성/부여 실패")
                        print(f"  ⚠️ {nation} 국가 역할 처리 실패")
                        
                except Exception as e:
                    changes.append(f"• ⚠️ 국가 역할 처리 실패: {str(e)[:50]}")
                    print(f"  ⚠️ 국가 역할 처리 실패 ({nation}): {e}")
            
            # 기본 국가인 경우에도 국가 역할 부여 (선택사항)
            elif is_base_nation and nation != "무소속":
                try:
                    # 기본 국가도 국가별 역할을 원한다면 이 부분 활성화
                    nation_role = await create_nation_role_if_needed(guild, nation)
                    
                    if nation_role:
                        if nation_role not in member.roles:
                            await member.add_roles(nation_role)
                            changes.append(f"• **{nation_role.name}** 기본 국가 역할 추가됨")
                            print(f"  ✅ 기본 국가 역할 부여: {nation_role.name}")
                        else:
                            print(f"  ℹ️ 이미 기본 국가 역할 보유: {nation_role.name}")
                            
                except Exception as e:
                    changes.append(f"• ⚠️ 기본 국가 역할 처리 실패: {str(e)[:50]}")
                    print(f"  ⚠️ 기본 국가 역할 처리 실패 ({nation}): {e}")
            
        else:
            # 외국인 또는 무소속
            if nation == "무소속":
                print(f"  🌍 무소속 사용자 확인됨 - 외국인 역할 부여")
            else:
                print(f"  🌍 외국인 확인됨: {nation}")
            
            # 외국인 역할 부여
            if SUCCESS_ROLE_ID_OUT != 0:
                out_role = guild.get_role(SUCCESS_ROLE_ID_OUT)
                if out_role:
                    if out_role not in member.roles:
                        try:
                            await member.add_roles(out_role)
                            if nation == "무소속":
                                changes.append(f"• **{out_role.name}** 역할 추가됨 (무소속)")
                            else:
                                changes.append(f"• **{out_role.name}** 역할 추가됨")
                            print(f"  ✅ 외국인 역할 부여: {out_role.name}")
                        except Exception as e:
                            changes.append(f"• ⚠️ 외국인 역할 부여 실패: {str(e)[:50]}")
                            print(f"  ⚠️ 외국인 역할 부여 실패: {e}")
                    else:
                        print(f"  ℹ️ 이미 외국인 역할 보유: {out_role.name}")
                else:
                    print(f"  ⚠️ 외국인 역할을 찾을 수 없음 (ID: {SUCCESS_ROLE_ID_OUT})")
            
            # 국민 역할 제거
            if SUCCESS_ROLE_ID != 0:
                success_role = guild.get_role(SUCCESS_ROLE_ID)
                if success_role and success_role in member.roles:
                    try:
                        await member.remove_roles(success_role)
                        changes.append(f"• **{success_role.name}** 역할 제거됨")
                        print(f"  ✅ 국민 역할 제거: {success_role.name}")
                    except Exception as e:
                        changes.append(f"• ⚠️ 국민 역할 제거 실패: {str(e)[:50]}")
                        print(f"  ⚠️ 국민 역할 제거 실패: {e}")
            
            # 외국인 국가에도 국가별 역할 부여 (선택사항)
            if nation != "무소속":
                try:
                    # 외국인도 국가별 역할을 원한다면 이 부분 활성화
                    nation_role = await create_nation_role_if_needed(guild, nation)
                    
                    if nation_role:
                        if nation_role not in member.roles:
                            await member.add_roles(nation_role)
                            changes.append(f"• **{nation_role.name}** 외국 국가 역할 추가됨")
                            print(f"  ✅ 외국 국가 역할 부여: {nation_role.name}")
                        else:
                            print(f"  ℹ️ 이미 외국 국가 역할 보유: {nation_role.name}")
                            
                except Exception as e:
                    changes.append(f"• ⚠️ 외국 국가 역할 처리 실패: {str(e)[:50]}")
                    print(f"  ⚠️ 외국 국가 역할 처리 실패 ({nation}): {e}")
        
        return changes
        
    except Exception as e:
        print(f"❌ 사용자 정보 업데이트 실패: {e}")
        return [f"• ❌ 업데이트 실패: {str(e)[:50]}"]


# process_single_user 함수의 성공 로그 부분에 동맹 국가 정보 추가하는 방법:

def create_success_embed(nation, base_nation):
    """성공 로그용 임베드 생성 (동맹 국가 정보 포함)"""
    if nation == base_nation:
        embed = discord.Embed(
            title="✅ 국민 확인 완료",
            description=f"**{base_nation}** 국민으로 확인되었습니다!",
            color=0x00ff00
        )
    elif ALLIANCE_ENABLED and alliance_manager and alliance_manager.is_alliance(nation):
        embed = discord.Embed(
            title="✅ 동맹 국가 국민 확인 완료",
            description=f"**{nation}** 동맹 국가 국민으로 확인되었습니다!",
            color=0x00ff00
        )
    else:
        embed = discord.Embed(
            title="⚠️ 다른 국가 소속",
            description=f"**{nation}** 국가에 소속되어 있습니다.",
            color=0xff9900
        )
    
    return embed

def is_exception_user(user_id: int) -> bool:
    """예외 사용자 확인 함수 (main.py에서 사용)"""
    try:
        return exception_manager.is_exception(user_id)
    except Exception as e:
        print(f"⚠️ 예외 사용자 확인 오류: {e}")
        return False

def setup_scheduler(bot):
    """스케줄러 설정 함수 (main.py에서 호출) - 누락된 함수 추가"""
    print("🔧 스케줄러 설정 시작...")
    start_scheduler(bot)

def get_scheduler_info():
    """백그라운드 태스크 상태 정보를 반환 (discord.ext.tasks 기반)"""
    try:
        # 백그라운드 루프 실행 상태
        queue_running = queue_processor_loop.is_running()
        auto_roles_running = auto_roles_checker.is_running()

        # 등록된 작업들
        jobs = []

        if queue_running:
            # 다음 실행까지 남은 시간 계산
            if queue_processor_loop.next_iteration:
                next_run = queue_processor_loop.next_iteration.strftime("%Y-%m-%d %H:%M:%S")
            else:
                next_run = "곧 실행"

            jobs.append({
                "id": "queue_processor",
                "name": "대기열 처리",
                "next_run": next_run,
                "interval": "1분마다"
            })

        if auto_roles_running:
            day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            day_name = day_names[AUTO_EXECUTION_DAY] if 0 <= AUTO_EXECUTION_DAY <= 6 else "알 수 없음"

            jobs.append({
                "id": "auto_roles_checker",
                "name": "자동 역할 실행",
                "next_run": f"매주 {day_name} {AUTO_EXECUTION_HOUR:02d}:{AUTO_EXECUTION_MINUTE:02d}",
                "interval": "1시간마다 체크"
            })

        # 상태 정보
        status_info = {
            "running": queue_running or auto_roles_running,
            "queue_loop_running": queue_running,
            "auto_roles_loop_running": auto_roles_running,
            "jobs": jobs,
            "auto_execution_day": AUTO_EXECUTION_DAY,
            "auto_execution_hour": AUTO_EXECUTION_HOUR,
            "auto_execution_minute": AUTO_EXECUTION_MINUTE,
            "rate_limit_detected": rate_limit_detected,
            "rate_limit_until": rate_limit_until.strftime("%Y-%m-%d %H:%M:%S") if rate_limit_until else None,
            "retry_queue_size": len(retry_counts)
        }

        return status_info
    except Exception as e:
        print(f"백그라운드 태스크 정보 조회 오류: {e}")
        return {
            "running": False,
            "queue_loop_running": False,
            "auto_roles_loop_running": False,
            "jobs": [],
            "auto_execution_day": AUTO_EXECUTION_DAY,
            "auto_execution_hour": AUTO_EXECUTION_HOUR,
            "auto_execution_minute": AUTO_EXECUTION_MINUTE,
            "rate_limit_detected": False,
            "rate_limit_until": None,
            "retry_queue_size": 0
        }
    


def handle_rate_limit():
    """429 오류 감지 시 호출되는 함수"""
    global rate_limit_detected, rate_limit_until

    rate_limit_detected = True
    rate_limit_until = datetime.now() + timedelta(minutes=5)
    rate_limit_unix = int(rate_limit_until.timestamp())

    print(f"🚨 API 속도 제한 감지! 5분간 대기 ({rate_limit_until.strftime('%H:%M:%S')}까지, Unix: {rate_limit_unix})")

def is_rate_limited() -> bool:
    """현재 API 속도 제한 상태인지 확인"""
    global rate_limit_detected, rate_limit_until
    
    if not rate_limit_detected:
        return False
    
    if datetime.now() >= rate_limit_until:
        # 제한 시간이 지났으면 상태 초기화
        rate_limit_detected = False
        rate_limit_until = None
        print("✅ API 속도 제한 해제")
        return False
    
    return True

def increment_retry_count(user_id: int) -> int:
    """사용자의 재시도 횟수를 증가시키고 반환"""
    retry_counts[user_id] = retry_counts.get(user_id, 0) + 1
    return retry_counts[user_id]

def clear_retry_count(user_id: int):
    """사용자의 재시도 횟수 초기화"""
    retry_counts.pop(user_id, None)

def should_retry(user_id: int) -> bool:
    """사용자가 재시도 가능한지 확인"""
    return retry_counts.get(user_id, 0) < MAX_RETRY_COUNT

def abbreviate_nation_name(nation_name: str) -> str:
    """국가 이름을 축약하는 함수"""
    # 언더스코어로 분리된 단어들의 첫 글자만 가져오기
    parts = nation_name.split('_')
    if len(parts) <= 1:
        # 언더스코어가 없으면 대문자만 추출 (CamelCase 처리)
        capital_letters = re.findall(r'[A-Z]', nation_name)
        if capital_letters:
            return '.'.join(capital_letters)
        else:
            # 대문자가 없으면 처음 5글자만
            return nation_name[:5]
    else:
        # 각 단어의 첫 글자를 점으로 연결
        abbreviated = '.'.join([part[0].upper() for part in parts if part])
        return abbreviated

def create_nickname(mc_id: str, nation: str, current_nickname: str = None, town: str = None) -> str:
    """닉네임 생성 함수 - 무소속 사용자 및 정보 없는 사용자 처리 포함"""
    # Discord 닉네임 최대 길이
    MAX_LENGTH = 32
    SEPARATOR = " ㅣ "

    # 국가 정보가 없는 경우 마을 이름 또는 ❌ 표시
    if nation == "❌":
        if town and town != "❌":
            callsign = town  # 국가는 없지만 마을이 있으면 마을 이름 사용
        else:
            callsign = "❌"  # 둘 다 없으면 ❌ 표시
    # 무소속 사용자 처리
    elif nation == "무소속":
        callsign = "무소속"
    elif nation == BASE_NATION:
        # BASE_NATION인 경우 기존 콜사인 유지 시도
        if current_nickname and " ㅣ " in current_nickname:
            # 현재 닉네임에서 콜사인 부분 추출
            parts = current_nickname.split(" ㅣ ")
            if len(parts) >= 2:
                current_callsign = parts[1]
                # 마크 닉네임이 현재 닉네임의 첫 부분과 일치하는지 확인
                if parts[0] == mc_id:
                    # 기존 콜사인 유지
                    new_nickname = f"{mc_id}{SEPARATOR}{current_callsign}"
                    if len(new_nickname) <= MAX_LENGTH:
                        return new_nickname

        # 기존 콜사인이 없거나 길이 초과인 경우 국가명 사용
        callsign = nation
    else:
        # 다른 국가인 경우 국가명 사용
        callsign = nation

    # 기본 닉네임 생성
    base_nickname = f"{mc_id}{SEPARATOR}{callsign}"

    # 길이 확인
    if len(base_nickname) <= MAX_LENGTH:
        return base_nickname

    # 길이 초과 시 국가명 축약 (무소속의 경우 "무소속" → "무", ❌는 그대로)
    if callsign == "무소속":
        abbreviated_nation = "무"
    elif callsign == "❌":
        abbreviated_nation = "❌"
    else:
        abbreviated_nation = abbreviate_nation_name(callsign)

    abbreviated_nickname = f"{mc_id}{SEPARATOR}{abbreviated_nation}"

    # 축약해도 길이 초과인 경우
    if len(abbreviated_nickname) > MAX_LENGTH:
        # 마크 닉네임을 우선시하고 국가 부분을 더 축약
        available_length = MAX_LENGTH - len(mc_id) - len(SEPARATOR)
        if available_length > 0:
            truncated_nation = abbreviated_nation[:available_length]
            return f"{mc_id}{SEPARATOR}{truncated_nation}"
        else:
            # 극단적인 경우 마크 닉네임만
            return mc_id[:MAX_LENGTH]

    return abbreviated_nickname

# 글로벌 CSV 데이터 수집 리스트
_csv_data_collection = []

def add_to_csv_collection(user_data: dict):
    """CSV 데이터 수집 리스트에 사용자 정보 추가"""
    global _csv_data_collection
    _csv_data_collection.append(user_data)

def save_csv_report():
    """수집된 데이터를 CSV 파일로 저장 (data/csv_exports 폴더)"""
    global _csv_data_collection

    try:
        if not _csv_data_collection:
            print("📋 CSV 저장: 데이터 없음")
            return None

        # data/csv_exports 폴더 생성
        csv_dir = "data/csv_exports"
        os.makedirs(csv_dir, exist_ok=True)

        # 파일명: auto_execution_YYYYMMDD_HHMMSS.csv
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"auto_execution_{timestamp}.csv"
        filepath = os.path.join(csv_dir, filename)

        # CSV 헤더
        fieldnames = [
            'discord_id',
            'discord_name',
            'minecraft_name',
            'minecraft_uuid',
            'nation',
            'town',
            'nation_ranks',
            'town_ranks',
            'last_online_timestamp',
            'last_online_date',
            'days_offline',
            'processed_at'
        ]

        # CSV 파일 생성
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(_csv_data_collection)

        print(f"✅ CSV 보고서 저장 완료: {filepath} ({len(_csv_data_collection)}건)")

        # 데이터 초기화
        _csv_data_collection = []

        return filepath

    except Exception as e:
        print(f"❌ CSV 저장 실패: {e}")
        return None

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

async def send_rate_limit_notification(bot):
    """429 오류 발생 시 알림 메시지 전송"""
    try:
        embed = discord.Embed(
            title="⏰ API 속도 제한 감지",
            description="API 속도 제한으로 인해 5분간 처리를 일시 중단합니다.",
            color=0xffaa00
        )

        # 남은 시간 계산
        remaining_time = format_time_until(rate_limit_until)
        rate_limit_unix = int(rate_limit_until.timestamp())

        embed.add_field(
            name="📊 현재 상황",
            value=f"• **제한 해제 시간**: {rate_limit_until.strftime('%H:%M:%S')}\n"
                  f"• **Unix 타임스탬프**: `{rate_limit_unix}`\n"
                  f"• **남은 시간**: {remaining_time}\n"
                  f"• **대기열 크기**: {queue_manager.get_queue_size()}명\n"
                  f"• **재시도 대상**: {len(retry_counts)}명",
            inline=False
        )

        embed.add_field(
            name="🔄 자동 처리",
            value="제한 해제 후 자동으로 처리가 재개됩니다.\n"
                  "실패한 사용자들은 자동으로 대기열에 다시 추가됩니다.",
            inline=False
        )

        embed.timestamp = datetime.now()

        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
        await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)

    except Exception as e:
        print(f"❌ 속도 제한 알림 전송 실패: {e}")

async def manual_execute_auto_roles(bot):
    """자동 역할 부여를 수동으로 실행 - 새로운 자동역할 관리자 사용"""
    try:
        print("🎯 수동 자동 역할 실행 시작")
        
        # 자동역할 관리자에서 역할 목록 가져오기
        role_ids = auto_role_manager.get_roles()
        
        if not role_ids:
            return {
                "success": False,
                "message": "자동처리로 설정된 역할이 없습니다. `/자동역할 기능:추가`로 역할을 추가해주세요."
            }
        
        added_count = 0
        processed_roles = []
        invalid_roles = []
        
        # 각 길드에서 역할 멤버들을 대기열에 추가
        for guild in bot.guilds:
            print(f"🏰 길드 처리: {guild.name}")
            
            for role_id in role_ids:
                try:
                    role = guild.get_role(role_id)
                    
                    if not role:
                        print(f"⚠️ 역할을 찾을 수 없음: {role_id}")
                        if role_id not in invalid_roles:
                            invalid_roles.append(role_id)
                        continue
                    
                    print(f"👥 역할 '{role.name}' 멤버 {len(role.members)}명 처리 중")
                    
                    role_added_count = 0
                    for member in role.members:
                        # 예외 목록 확인
                        if exception_manager.is_exception(member.id):
                            print(f"  ⏭️ 예외 대상 건너뜀: {member.display_name}")
                            continue
                        
                        # 대기열에 추가
                        if queue_manager.add_user(member.id):
                            added_count += 1
                            role_added_count += 1
                            print(f"  ➕ 대기열 추가: {member.display_name}")
                        else:
                            print(f"  ⏭️ 이미 대기열에 있음: {member.display_name}")
                    
                    # 처리된 역할 정보 저장
                    processed_roles.append({
                        'role': role,
                        'total_members': len(role.members),
                        'added_members': role_added_count
                    })
                    
                except Exception as e:
                    print(f"⚠️ 역할 처리 오류 ({role_id}): {e}")
                    if role_id not in invalid_roles:
                        invalid_roles.append(role_id)
                    continue
        
        print(f"✅ 자동 역할 실행 완료 - {added_count}명 대기열 추가")
        
        # 자동 역할 실행 완료 로그 전송
        embed = discord.Embed(
            title="🎯 자동 역할 실행 완료",
            description=f"**{added_count}명**이 대기열에 추가되었습니다.",
            color=0x00ff00
        )
        
        # 처리된 역할들 정보
        if processed_roles:
            role_info_lines = []
            for info in processed_roles[:5]:  # 최대 5개만 표시
                role_info_lines.append(
                    f"• {info['role'].mention}: {info['added_members']}/{info['total_members']}명 추가"
                )
            
            if len(processed_roles) > 5:
                role_info_lines.append(f"• ...그리고 {len(processed_roles) - 5}개 역할 더")
            
            embed.add_field(
                name="📋 처리된 역할",
                value="\n".join(role_info_lines),
                inline=False
            )
        
        # 무효한 역할이 있으면 표시
        if invalid_roles:
            embed.add_field(
                name="⚠️ 무효한 역할",
                value=f"{len(invalid_roles)}개의 역할을 찾을 수 없습니다.\n"
                      f"`/자동역할 기능:정리`로 무효한 역할들을 제거할 수 있습니다.",
                inline=False
            )
        
        current_queue_size = queue_manager.get_queue_size()
        embed.add_field(
            name="📊 대기열 현황",
            value=f"현재 대기 중: **{current_queue_size}명**",
            inline=False
        )
        
        if current_queue_size > 0:
            # 개선된 시간 표시 사용
            time_str = format_estimated_time(current_queue_size, 36)
            embed.add_field(
                name="⏰ 예상 완료 시간",
                value=time_str,
                inline=False
            )
        
        embed.timestamp = datetime.now()
        
        await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)
        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
        
        return {
            "success": True,
            "message": f"{added_count}명이 대기열에 추가되었습니다.",
            "added_count": added_count,
            "processed_roles": len(processed_roles),
            "invalid_roles": len(invalid_roles)
        }
        
    except Exception as e:
        print(f"❌ 자동 역할 실행 오류: {e}")
        
        # 자동 역할 실행 실패 로그 전송
        embed = discord.Embed(
            title="❌ 자동 역할 실행 실패",
            description="자동 역할 실행 중 오류가 발생했습니다.",
            color=0xff0000
        )
        
        embed.add_field(
            name="❌ 오류 내용",
            value=str(e)[:1000],
            inline=False
        )
        
        embed.timestamp = datetime.now()
        
        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
        
        return {
            "success": False,
            "message": f"실행 중 오류 발생: {str(e)}"
        }

# Discord.py tasks를 사용한 백그라운드 루프
@tasks.loop(minutes=1)
async def queue_processor_loop():
    """대기열 처리 루프 - 1분마다 실행 (완전히 비동기, 블로킹 없음)"""
    global _bot_instance

    if _bot_instance is None:
        print("⚠️ 봇 인스턴스가 없어 대기열 처리를 건너뜁니다")
        return

    try:
        await process_queue_batch(_bot_instance)
    except Exception as e:
        print(f"❌ 대기열 처리 루프 오류: {e}")
        import traceback
        traceback.print_exc()

@queue_processor_loop.before_loop
async def before_queue_processor():
    """대기열 처리 시작 전 봇 준비 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        print("✅ 대기열 처리 루프 준비 완료")

@tasks.loop(hours=1)
async def auto_roles_checker():
    """자동 역할 실행 체크 루프 - 매 시간마다 실행 시간 확인"""
    global _bot_instance

    if _bot_instance is None:
        return

    try:
        from config import config

        # 현재 시간 (한국 시간)
        now = datetime.now()

        # 설정된 실행 시간인지 확인
        if (now.weekday() == AUTO_EXECUTION_DAY and
            now.hour == AUTO_EXECUTION_HOUR and
            0 <= now.minute < 60):  # 해당 시간의 아무 분이나 (중복 실행 방지는 별도 처리)

            print(f"🎯 자동 역할 실행 시간 도달: {now.strftime('%Y-%m-%d %H:%M')}")

            # 백그라운드로 실행 (블로킹 방지)
            asyncio.create_task(execute_auto_roles(_bot_instance))

    except Exception as e:
        print(f"❌ 자동 역할 체크 루프 오류: {e}")

@auto_roles_checker.before_loop
async def before_auto_roles_checker():
    """자동 역할 체크 시작 전 봇 준비 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        print("✅ 자동 역할 체크 루프 준비 완료")

def start_scheduler(bot):
    """스케줄러 시작 - discord.ext.tasks 사용"""
    global _bot_instance

    try:
        print("🚀 백그라운드 태스크 시작")

        # 봇 인스턴스 저장
        _bot_instance = bot

        # 대기열 처리 루프 시작
        if not queue_processor_loop.is_running():
            queue_processor_loop.start()
            print("   ✅ 대기열 처리 루프 시작 (1분마다)")

        # 자동 역할 체크 루프 시작
        if not auto_roles_checker.is_running():
            auto_roles_checker.start()

            day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            day_name = day_names[AUTO_EXECUTION_DAY] if 0 <= AUTO_EXECUTION_DAY <= 6 else "알 수 없음"

            print(f"   ✅ 자동 역할 체크 루프 시작")
            print(f"   🎯 자동 역할 실행 예정: 매주 {day_name} {AUTO_EXECUTION_HOUR:02d}:{AUTO_EXECUTION_MINUTE:02d}")

        print("✅ 백그라운드 태스크 시작 완료 (명령어와 완전히 분리됨)")

    except Exception as e:
        print(f"❌ 백그라운드 태스크 시작 실패: {e}")
        import traceback
        traceback.print_exc()

def stop_scheduler():
    """스케줄러 중지"""
    try:
        print("🛑 백그라운드 태스크 중지")

        if queue_processor_loop.is_running():
            queue_processor_loop.cancel()
            print("   ✅ 대기열 처리 루프 중지")

        if auto_roles_checker.is_running():
            auto_roles_checker.cancel()
            print("   ✅ 자동 역할 체크 루프 중지")

        print("✅ 백그라운드 태스크 중지 완료")

    except Exception as e:
        print(f"❌ 백그라운드 태스크 중지 실패: {e}")

async def process_queue_batch(bot):
    """대기열에서 사용자들을 배치로 처리 - 429 오류 처리 추가"""
    try:
        # 속도 제한 상태 확인
        if is_rate_limited():
            remaining_time = (rate_limit_until - datetime.now()).total_seconds()
            print(f"⏸️ API 속도 제한 중 - 남은 시간: {remaining_time:.0f}초")
            return

        # 처리 전 대기열 크기 확인
        queue_size_before = queue_manager.get_queue_size()

        if queue_size_before == 0:
            return

        print("🔄 대기열 배치 처리 시작")
        queue_manager.processing = True

        # 배치 크기 (한 번에 처리할 사용자 수)
        batch_size = 3
        processed_users = []

        for _ in range(batch_size):
            user_id = queue_manager.get_next()
            if user_id is None:
                break
            processed_users.append(user_id)

        if not processed_users:
            queue_manager.processing = False
            return

        print(f"📋 배치 처리 대상: {len(processed_users)}명")

        # API 세션 생성
        async with aiohttp.ClientSession() as session:
            for user_id in processed_users:
                try:
                    # 속도 제한 재확인 (배치 중간에 발생할 수 있음)
                    if is_rate_limited():
                        print(f"⏸️ 배치 처리 중 속도 제한 감지 - 나머지 사용자 대기열에 재추가")
                        # 처리되지 않은 사용자들을 대기열에 다시 추가
                        queue_manager.add_user(user_id)
                        break

                    await process_single_user(bot, session, user_id)
                    await asyncio.sleep(10)  # API 제한을 위한 대기 (비블로킹)
                except Exception as e:
                    print(f"❌ 사용자 {user_id} 처리 실패: {e}")

        print(f"✅ 배치 처리 완료: {len(processed_users)}명")

        # 처리 후 대기열이 비었는지 확인하고 완료 메시지 전송
        queue_size_after = queue_manager.get_queue_size()

        # 대기열이 비어있고, 처리 전에는 비어있지 않았다면 완료 메시지 전송
        if queue_size_after == 0 and queue_size_before > 0:
            print("🎉 모든 대기열 처리 완료!")

            # CSV 보고서 저장
            csv_filepath = save_csv_report()

            # 완료 메시지 임베드 생성
            embed = discord.Embed(
                title="✅ 자동 실행 완료",
                description="모든 대기열 처리가 완료되었습니다.",
                color=0x00ff00
            )

            embed.add_field(
                name="📊 처리 결과",
                value="대기열에 있던 모든 사용자의 처리가 완료되었습니다.",
                inline=False
            )

            if csv_filepath:
                csv_filename = os.path.basename(csv_filepath)
                embed.add_field(
                    name="📄 CSV 보고서",
                    value=f"파일명: `{csv_filename}`\n자동 실행 결과가 CSV 파일로 저장되었습니다.",
                    inline=False
                )

            embed.timestamp = datetime.now()

            # 성공 채널과 실패 채널 모두에 전송 (CSV 파일 첨부)
            try:
                if SUCCESS_CHANNEL_ID and SUCCESS_CHANNEL_ID != 0:
                    success_channel = bot.get_channel(SUCCESS_CHANNEL_ID)
                    if success_channel:
                        if csv_filepath and os.path.exists(csv_filepath):
                            with open(csv_filepath, 'rb') as f:
                                discord_file = discord.File(f, filename=os.path.basename(csv_filepath))
                                await success_channel.send(embed=embed, file=discord_file)
                        else:
                            await success_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ 성공 채널 전송 실패: {e}")

            try:
                if FAILURE_CHANNEL_ID and FAILURE_CHANNEL_ID != 0:
                    failure_channel = bot.get_channel(FAILURE_CHANNEL_ID)
                    if failure_channel:
                        if csv_filepath and os.path.exists(csv_filepath):
                            with open(csv_filepath, 'rb') as f:
                                discord_file = discord.File(f, filename=os.path.basename(csv_filepath))
                                await failure_channel.send(embed=embed, file=discord_file)
                        else:
                            await failure_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ 실패 채널 전송 실패: {e}")

    except Exception as e:
        print(f"❌ 배치 처리 오류: {e}")
    finally:
        queue_manager.processing = False

async def process_single_user(bot, session, user_id):
    """단일 사용자 처리 - 429 오류 처리 및 재대기열 추가, 마지막 온라인 정보 포함"""
    member = None
    guild = None
    mc_id = None
    nation = None
    town = None
    nation_ranks = None
    town_ranks = None
    last_online = None
    last_online_formatted = None
    days_offline = None
    error_message = None

    try:
        print(f"👤 사용자 처리 시작: {user_id}")

        # 예외 사용자 확인 (최우선 체크)
        if exception_manager and exception_manager.is_exception(user_id):
            print(f"⏭️ 예외 사용자 건너뜀: {user_id}")
            return

        # 모든 길드에서 해당 사용자 찾기
        for g in bot.guilds:
            m = g.get_member(user_id)
            if m:
                member = m
                guild = g
                break

        if not member or not guild:
            error_message = "서버에서 사용자를 찾을 수 없습니다."
            print(f"⚠️ {error_message}: {user_id}")

            # 실패 로그 전송
            embed = discord.Embed(
                title="❌ 사용자 처리 실패",
                description=f"**사용자 ID:** {user_id}",
                color=0xff0000
            )
            embed.add_field(
                name="❌ 오류",
                value=error_message,
                inline=False
            )
            embed.timestamp = datetime.now()

            await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
            return

        # 데이터베이스에서 UUID 먼저 확인 (API 요청 최적화)
        cached_uuid = None
        cached_mc_name = None
        if DATABASE_ENABLED and db_manager:
            try:
                user_data = db_manager.get_user_info(user_id)
                if user_data:
                    cached_uuid = user_data.get('minecraft_uuid')
                    cached_mc_name = user_data.get('current_minecraft_name')
                    if cached_uuid and cached_mc_name:
                        print(f"  💾 데이터베이스에서 UUID 조회: {cached_mc_name} (UUID: {cached_uuid[:8]}...)")
                        uuid = cached_uuid
                        mc_id = cached_mc_name
            except Exception as db_error:
                print(f"  ⚠️ 데이터베이스 조회 실패: {db_error}")

        # 데이터베이스에 UUID가 없으면 API로 조회
        if not cached_uuid:
            print(f"  🔍 API를 통해 UUID 조회 중...")
            # 1단계: 디스코드 ID → UUID, MC Name
            url1 = f"{MC_API_BASE}/discord?discord={user_id}"

            async with session.get(url1, timeout=aiohttp.ClientTimeout(total=10)) as r1:
                if r1.status == 429:
                    # 429 오류 처리
                    print(f"🚨 API 속도 제한 감지 (1단계) - 사용자 {user_id} 재대기열 추가")
                    handle_rate_limit()
                    await send_rate_limit_notification(bot)

                    # 재시도 횟수 확인
                    retry_count = increment_retry_count(user_id)
                    if should_retry(user_id):
                        queue_manager.add_user(user_id)  # 재대기열에 추가
                        print(f"  🔄 재시도 {retry_count}/{MAX_RETRY_COUNT}: {member.display_name}")
                    else:
                        clear_retry_count(user_id)
                        print(f"  ❌ 최대 재시도 횟수 초과: {member.display_name}")

                        # 최대 재시도 초과 로그
                        embed = discord.Embed(
                            title="❌ 최대 재시도 횟수 초과",
                            description=f"사용자가 {MAX_RETRY_COUNT}회 재시도 후에도 처리되지 않았습니다.",
                            color=0xff0000
                        )
                        embed.add_field(
                            name="👤 사용자 정보",
                            value=f"**Discord:** {member.mention}\n**닉네임:** {member.display_name}",
                            inline=False
                        )
                        embed.add_field(
                            name="❌ 원인",
                            value="API 속도 제한으로 인한 반복적인 실패",
                            inline=False
                        )
                        embed.timestamp = datetime.now()
                        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
                    return
                elif r1.status != 200:
                    error_message = f"마인크래프트 계정 연동 정보를 찾을 수 없습니다 (HTTP {r1.status})"
                    print(f"  ❌ 1단계 실패: {r1.status}")
                    raise Exception(error_message)

                data1 = await r1.json()
                if not data1.get('data') or not data1['data']:
                    error_message = "마인크래프트 계정이 연동되지 않았습니다"
                    print(f"  ❌ 마크 계정 연동 데이터 없음")
                    raise Exception(error_message)

                uuid = data1['data'][0].get('uuid')
                mc_id = data1['data'][0].get('name')

                if not uuid or not mc_id:
                    error_message = "마인크래프트 계정 정보가 불완전합니다"
                    print(f"  ❌ UUID 또는 이름 없음")
                    raise Exception(error_message)

                print(f"  ✅ 마크 정보: {mc_id} (UUID: {uuid[:8]}...)")
                await asyncio.sleep(5)  # API 제한을 위한 대기 (비블로킹)
        else:
            # 데이터베이스에서 UUID를 가져온 경우, API 대기 시간 스킵
            print(f"  ⚡ 캐시된 UUID 사용 - API 대기 시간 스킵")

        # 2단계: UUID → 모든 게임 정보 (개선된 API 사용)
        url2 = f"{MC_API_BASE}/resident?uuid={uuid}"
        
        async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as r2:
            if r2.status == 429:
                # 429 오류 처리
                print(f"🚨 API 속도 제한 감지 (2단계) - 사용자 {user_id} 재대기열 추가")
                handle_rate_limit()
                await send_rate_limit_notification(bot)
                
                # 재시도 횟수 확인
                retry_count = increment_retry_count(user_id)
                if should_retry(user_id):
                    queue_manager.add_user(user_id)  # 재대기열에 추가
                    print(f"  🔄 재시도 {retry_count}/{MAX_RETRY_COUNT}: {member.display_name}")
                else:
                    clear_retry_count(user_id)
                    print(f"  ❌ 최대 재시도 횟수 초과: {member.display_name}")
                return
            elif r2.status != 200:
                error_message = f"게임 정보를 조회할 수 없습니다 (HTTP {r2.status})"
                print(f"  ❌ 2단계 실패: {r2.status}")
                raise Exception(error_message)
            
            data2 = await r2.json()
            if not data2.get('data') or not data2['data']:
                error_message = "게임 내 정보가 없습니다"
                print(f"  ❌ 게임 데이터 없음")
                raise Exception(error_message)
            
            game_info = data2['data'][0]

            # 모든 게임 정보 추출
            nation = game_info.get('nation')
            nation_uuid = game_info.get('nationUUID')  # UUID 추출 (camelCase)
            if not nation_uuid:
                nation_uuid = game_info.get('nationUuid')  # lowercase uuid도 시도

            town = game_info.get('town')
            town_uuid = game_info.get('townUUID')  # UUID 추출
            if not town_uuid:
                town_uuid = game_info.get('townUuid')

            nation_ranks = game_info.get('nationRanks', '')
            town_ranks = game_info.get('townRanks', '')
            last_online = game_info.get('lastOnline')

            # 국가 또는 마을 정보가 없는 경우 처리
            if not nation:
                nation = "❌"  # 국가 정보 없음
            if not town:
                town = "❌"  # 마을 정보 없음
            
            # 마지막 온라인 시간 처리
            if last_online:
                try:
                    # 밀리초 타임스탬프를 datetime으로 변환
                    last_online_dt = datetime.fromtimestamp(last_online / 1000)
                    last_online_formatted = last_online_dt.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 오늘 날짜와 비교하여 경과 일수 계산
                    now = datetime.now()
                    days_diff = (now - last_online_dt).days
                    
                    if days_diff == 0:
                        days_offline = "오늘"
                    elif days_diff == 1:
                        days_offline = "1일 전"
                    else:
                        days_offline = f"{days_diff}일 전"
                    
                    print(f"  ✅ 게임 정보: {nation}/{town}, 마지막 접속: {days_offline}")
                    
                except Exception as e:
                    print(f"  ⚠️ 마지막 온라인 시간 처리 오류: {e}")
                    last_online_formatted = "알 수 없음"
                    days_offline = "알 수 없음"
            else:
                last_online_formatted = "정보 없음"
                days_offline = "정보 없음"
                print(f"  ✅ 게임 정보: {nation}/{town}, 마지막 접속: 정보 없음")
        
        # 성공 시 재시도 횟수 초기화
        clear_retry_count(user_id)
        
        # 역할 부여 및 닉네임 변경 (마을 정보 및 UUID 포함)
        role_changes = await update_user_info(
            member, mc_id, nation, guild, town,
            nation_uuid=nation_uuid, town_uuid=town_uuid
        )

        # 데이터베이스에 사용자 정보 저장 (UUID, Minecraft 닉네임 히스토리)
        if DATABASE_ENABLED and db_manager:
            try:
                db_manager.add_or_update_user(
                    discord_id=user_id,
                    minecraft_uuid=uuid,
                    minecraft_name=mc_id
                )
                print(f"  💾 데이터베이스 저장 완료: {mc_id} (UUID: {uuid[:8]}...)")

                # 국가 히스토리 저장
                db_manager.add_nation_history(
                    discord_id=user_id,
                    nation_name=nation if nation and nation not in ["❌", "무소속"] else None,
                    nation_uuid=nation_uuid if nation_uuid else None,
                    town_name=town if town and town not in ["❌", "무소속"] else None,
                    town_uuid=town_uuid if town_uuid else None
                )
                print(f"  💾 국가 히스토리 저장 완료: {nation}/{town}")

            except Exception as e:
                print(f"  ⚠️ 데이터베이스 저장 실패: {e}")

        # CSV 데이터 수집 (자동 실행 시)
        try:
            csv_data = {
                'discord_id': str(user_id),
                'discord_name': member.display_name,
                'minecraft_name': mc_id,
                'minecraft_uuid': uuid if uuid else '',
                'nation': nation if nation else '',
                'town': town if town else '',
                'nation_ranks': nation_ranks if nation_ranks else '',
                'town_ranks': town_ranks if town_ranks else '',
                'last_online_timestamp': str(last_online) if last_online else '',
                'last_online_date': last_online_formatted if last_online_formatted else '',
                'days_offline': days_offline if days_offline else '',
                'processed_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            add_to_csv_collection(csv_data)
        except Exception as e:
            print(f"  ⚠️ CSV 데이터 수집 실패: {e}")

        print(f"✅ 사용자 처리 완료: {member.display_name} ({nation}, {town})")

        # 국가/마을이 없는 경우 실패 로그로 처리하되 역할은 부여
        if nation == "❌" or town == "❌" or nation == "무소속" or town == "무소속":
            # 실패 로그 전송 (하지만 외국인 역할은 부여됨)
            embed = discord.Embed(
                title="⚠️ 게임 정보 불완전",
                description="국가 또는 마을 정보가 없지만 외국인 역할을 부여했습니다.",
                color=0xff6600  # 주황색 (경고)
            )

            embed.add_field(
                name="👤 사용자 정보",
                value=f"**Discord:** {member.mention}\n**닉네임:** {member.display_name}",
                inline=False
            )

            # 마인크래프트 정보
            minecraft_info = f"**마인크래프트 닉네임:** ``{mc_id}``"
            if town == "❌" or town == "무소속":
                minecraft_info += f"\n**마을:** ❌ 정보 없음"
            else:
                minecraft_info += f"\n**마을:** {town}"

            if nation == "❌" or nation == "무소속":
                minecraft_info += f"\n**국가:** ❌ 정보 없음"
            else:
                minecraft_info += f"\n**국가:** {nation}"
            
            # 계급 정보 추가 (있는 경우)
            if nation_ranks:
                minecraft_info += f"\n**국가 계급:** {nation_ranks}"
            if town_ranks:
                minecraft_info += f"\n**마을 계급:** {town_ranks}"
            
            embed.add_field(
                name="🎮 마인크래프트 정보",
                value=minecraft_info,
                inline=False
            )
            
            # 마지막 온라인 정보 추가
            embed.add_field(
                name="🕒 마지막 온라인",
                value=f"**날짜:** {last_online_formatted}\n**경과:** {days_offline}",
                inline=True
            )
            
            # 처리 결과 안내
            if SUCCESS_ROLE_ID_OUT != 0:
                embed.add_field(
                    name="🔄 처리 결과",
                    value="외국인 역할이 자동으로 부여되었습니다.\n게임 내에서 국가/마을에 가입 후 다시 확인해주세요.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ 처리 결과", 
                    value="외국인 역할 ID가 설정되지 않아 역할을 부여할 수 없습니다.",
                    inline=False
                )
            
            if role_changes:
                embed.add_field(
                    name="🔄 변경 사항",
                    value="\n".join(role_changes),
                    inline=False
                )
            
            embed.timestamp = datetime.now()
            
            # 실패 채널에 전송
            await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
            return
        
        # 정상적인 성공 로그 전송 (마을 역할 정보 및 마지막 온라인 포함)
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
        
        embed.add_field(
            name="👤 사용자 정보",
            value=f"**Discord:** ``{member.mention}``\n**닉네임:** ``{member.display_name}``",
            inline=False
        )
        
        # 마인크래프트 정보 (계급 정보 포함)
        minecraft_info = f"**마인크래프트 닉네임:** ``{mc_id}``\n**마을:** ``{town}``\n**국가:** ``{nation}``"
        
        # 계급 정보 추가
        if nation_ranks:
            minecraft_info += f"\n**국가 계급:** ``{nation_ranks}``"
        if town_ranks:
            minecraft_info += f"\n**마을 계급:** ``{town_ranks}``"
        
        embed.add_field(
            name="🎮 마인크래프트 정보",
            value=minecraft_info,
            inline=False
        )
        
        # 마지막 온라인 정보 추가
        embed.add_field(
            name="🕒 마지막 온라인",
            value=f"**날짜:** {last_online_formatted}\n**경과:** {days_offline}",
            inline=True
        )
        
        # 재시도 정보 추가 (재시도가 있었던 경우)
        if user_id in retry_counts:
            embed.add_field(
                name="🔄 재시도 정보",
                value=f"**재시도 횟수:** {retry_counts[user_id]}회",
                inline=True
            )
        
        # 마을 역할 연동 상태 표시
        if TOWN_ROLE_ENABLED and town_role_manager:
            role_id = town_role_manager.get_role_id(town)
            if role_id:
                town_role = guild.get_role(role_id)
                if town_role:
                    embed.add_field(
                        name="🏘️ 마을 역할",
                        value=f"**``{town}``** → {town_role.mention}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🏘️ 마을 역할",
                        value=f"**``{town}``** → ⚠️ 역할 없음 (ID: {role_id})",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="🏘️ 마을 역할",
                    value=f"**``{town}``** → ℹ️ 역할 연동 안됨",
                    inline=False
                )
        
        if role_changes:
            # 너무 많은 변경사항이 있을 경우 요약
            if len("\n".join(role_changes)) > 1000:
                role_changes = role_changes[:8]  # 최대 8개만 표시
                role_changes.append("• ...")
            
            embed.add_field(
                name="🔄 변경 사항",
                value="\n".join(role_changes),
                inline=False
            )
        
        embed.timestamp = datetime.now()

        await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)

    except Exception as e:
        print(f"❌ 사용자 {user_id} 처리 중 오류: {e}")

        # 429 오류가 아닌 일반 오류의 경우 재시도 횟수 초기화
        clear_retry_count(user_id)

        # 마인크래프트 계정이 연동되지 않은 경우 모든 역할 제거 및 닉네임 초기화
        role_removal_changes = []
        if "마인크래프트 계정이 연동되지 않았습니다" in str(e) or "마인크래프트 계정 연동 정보를 찾을 수 없습니다" in str(e):
            print(f"  🗑️ 마크 계정 미연동 - 모든 관련 역할 제거 및 닉네임 초기화 시작")

            if member and guild:
                # 0. 닉네임 초기화 (원래 이름으로 복구)
                try:
                    if member.nick:  # 닉네임이 설정되어 있는 경우만
                        original_nick = member.nick
                        await member.edit(nick=None)
                        role_removal_changes.append(f"• 닉네임 초기화됨: `{original_nick}` → `{member.name}`")
                        print(f"  ✅ 닉네임 초기화: {original_nick} → {member.name}")
                except discord.Forbidden:
                    role_removal_changes.append(f"• ⚠️ 닉네임 초기화 권한 없음")
                    print(f"  ⚠️ 닉네임 초기화 권한 없음")
                except Exception as nick_error:
                    print(f"  ⚠️ 닉네임 초기화 실패: {nick_error}")

                # 1. 국민 역할 제거
                if SUCCESS_ROLE_ID != 0:
                    success_role = guild.get_role(SUCCESS_ROLE_ID)
                    if success_role and success_role in member.roles:
                        try:
                            await member.remove_roles(success_role)
                            role_removal_changes.append(f"• **{success_role.name}** 역할 제거됨")
                            print(f"  ✅ 국민 역할 제거: {success_role.name}")
                        except Exception as role_error:
                            print(f"  ⚠️ 국민 역할 제거 실패: {role_error}")

                # 2. 외국인 역할 제거
                if SUCCESS_ROLE_ID_OUT != 0:
                    out_role = guild.get_role(SUCCESS_ROLE_ID_OUT)
                    if out_role and out_role in member.roles:
                        try:
                            await member.remove_roles(out_role)
                            role_removal_changes.append(f"• **{out_role.name}** 역할 제거됨")
                            print(f"  ✅ 외국인 역할 제거: {out_role.name}")
                        except Exception as role_error:
                            print(f"  ⚠️ 외국인 역할 제거 실패: {role_error}")

                # 3. 모든 마을 역할 제거
                if TOWN_ROLE_ENABLED and town_role_manager:
                    try:
                        all_mapped_towns = town_role_manager.get_all_mappings()
                        for mapped_town, mapped_role_id in all_mapped_towns.items():
                            mapped_role = guild.get_role(mapped_role_id)
                            if mapped_role and mapped_role in member.roles:
                                await member.remove_roles(mapped_role)
                                role_removal_changes.append(f"• **`{mapped_town}`** 마을 역할 제거됨")
                                print(f"  ✅ 마을 역할 제거: {mapped_town}")
                    except Exception as role_error:
                        print(f"  ⚠️ 마을 역할 제거 실패: {role_error}")

                # 4. 모든 국가 역할 제거 (nation_role_manager에서 관리하는 역할들)
                if NATION_ROLE_ENABLED:
                    try:
                        from nation_role_manager import nation_role_manager
                        all_nation_roles = nation_role_manager.get_all_nation_roles()
                        for nation_name, role_info in all_nation_roles.items():
                            role_id = role_info.get('role_id')
                            if role_id:
                                nation_role = guild.get_role(role_id)
                                if nation_role and nation_role in member.roles:
                                    await member.remove_roles(nation_role)
                                    role_removal_changes.append(f"• **`{nation_name}`** 국가 역할 제거됨")
                                    print(f"  ✅ 국가 역할 제거: {nation_name}")
                    except Exception as role_error:
                        print(f"  ⚠️ 국가 역할 제거 실패: {role_error}")

                if role_removal_changes:
                    print(f"  🗑️ 총 {len(role_removal_changes)}개 역할 제거 완료")

        # 실패 로그 전송
        embed = discord.Embed(
            title="❌ 사용자 처리 실패",
            color=0xff0000
        )

        if member:
            embed.add_field(
                name="👤 사용자 정보",
                value=f"**Discord:** {member.mention}\n**닉네임:** {member.display_name}",
                inline=False
            )
        else:
            embed.add_field(
                name="👤 사용자 정보",
                value=f"**사용자 ID:** {user_id}",
                inline=False
            )
        
        if mc_id:
            minecraft_info = f"**마인크래프트 닉네임:** ``{mc_id}``"
            if town:
                minecraft_info += f"\n**마을:** {town}"
                # 마을 역할 연동 상태도 표시
                if TOWN_ROLE_ENABLED and town_role_manager:
                    role_id = town_role_manager.get_role_id(town)
                    if role_id:
                        town_role = guild.get_role(role_id) if guild else None
                        if town_role:
                            minecraft_info += f"\n**마을 역할:** {town_role.mention}"
                        else:
                            minecraft_info += f"\n**마을 역할:** ⚠️ 역할 없음 (ID: {role_id})"
                    else:
                        minecraft_info += f"\n**마을 역할:** ℹ️ 연동 안됨"
            if nation:
                minecraft_info += f"\n**국가:** {nation}"
                if nation_ranks:
                    minecraft_info += f"\n**국가 계급:** {nation_ranks}"
            if last_online_formatted:
                minecraft_info += f"\n**마지막 온라인:** {last_online_formatted} ({days_offline})"
            
            embed.add_field(
                name="🎮 마인크래프트 정보",
                value=minecraft_info,
                inline=False
            )

        embed.add_field(
            name="❌ 오류 내용",
            value=str(e)[:1000],  # 너무 긴 오류 메시지 제한
            inline=False
        )

        # 역할 제거 변경사항이 있으면 추가
        if role_removal_changes:
            embed.add_field(
                name="🗑️ 제거된 역할",
                value="\n".join(role_removal_changes),
                inline=False
            )

        embed.timestamp = datetime.now()

        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)

    except Exception as e:
        print(f"❌ 사용자 {user_id} 처리 중 오류: {e}")
        
        # 429 오류가 아닌 일반 오류의 경우 재시도 횟수 초기화
        clear_retry_count(user_id)
        
        # 실패 로그 전송
        embed = discord.Embed(
            title="❌ 사용자 처리 실패",
            color=0xff0000
        )
        
        if member:
            embed.add_field(
                name="👤 사용자 정보",
                value=f"**Discord:** {member.mention}\n**닉네임:** {member.display_name}",
                inline=False
            )
        else:
            embed.add_field(
                name="👤 사용자 정보",
                value=f"**사용자 ID:** {user_id}",
                inline=False
            )
        
        if mc_id:
            minecraft_info = f"**마인크래프트 닉네임:** ``{mc_id}``"
            if town:
                minecraft_info += f"\n**마을:** {town}"
                # 마을 역할 연동 상태도 표시
                if TOWN_ROLE_ENABLED and town_role_manager:
                    role_id = town_role_manager.get_role_id(town)
                    if role_id:
                        town_role = guild.get_role(role_id) if guild else None
                        if town_role:
                            minecraft_info += f"\n**마을 역할:** {town_role.mention}"
                        else:
                            minecraft_info += f"\n**마을 역할:** ⚠️ 역할 없음 (ID: {role_id})"
                    else:
                        minecraft_info += f"\n**마을 역할:** ℹ️ 연동 안됨"
            if nation:
                minecraft_info += f"\n**국가:** {nation}"
            
            embed.add_field(
                name="🎮 마인크래프트 정보",
                value=minecraft_info,
                inline=False
            )
        
        embed.add_field(
            name="❌ 오류 내용",
            value=str(e)[:1000],  # 너무 긴 오류 메시지 제한
            inline=False
        )
        
        embed.timestamp = datetime.now()
        
        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)

async def execute_auto_roles(bot):
    """자동 역할 실행 함수 - 새로운 자동역할 관리자 사용 (비블로킹)"""
    try:
        print("🎯 자동 역할 실행 시작")

        # 자동역할 관리자에서 역할 목록 가져오기
        role_ids = auto_role_manager.get_roles()

        if not role_ids:
            print("⚠️ 자동처리로 설정된 역할이 없습니다.")

            # 실패 로그 전송
            embed = discord.Embed(
                title="❌ 자동 역할 실행 실패",
                description="자동처리로 설정된 역할이 없습니다.",
                color=0xff0000
            )
            embed.add_field(
                name="💡 해결 방법",
                value="`/자동역할 기능:추가 역할:@역할이름` 명령어로 자동처리 역할을 추가해주세요.",
                inline=False
            )
            embed.timestamp = datetime.now()
            await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
            return

        added_count = 0
        processed_roles = []
        invalid_roles = []

        # 각 길드에서 역할 멤버들을 대기열에 추가
        for guild in bot.guilds:
            print(f"🏰 길드 처리: {guild.name}")

            for role_id in role_ids:
                try:
                    role = guild.get_role(role_id)

                    if not role:
                        print(f"⚠️ 역할을 찾을 수 없음: {role_id}")
                        if role_id not in invalid_roles:
                            invalid_roles.append(role_id)
                        continue

                    print(f"👥 역할 '{role.name}' 멤버 {len(role.members)}명 처리 중")

                    role_added_count = 0
                    for idx, member in enumerate(role.members):
                        # 예외 목록 확인
                        if exception_manager.is_exception(member.id):
                            print(f"  ⏭️ 예외 대상 건너뜀: {member.display_name}")
                            continue

                        # 대기열에 추가
                        if queue_manager.add_user(member.id):
                            added_count += 1
                            role_added_count += 1
                            print(f"  ➕ 대기열 추가: {member.display_name}")
                        else:
                            print(f"  ⏭️ 이미 대기열에 있음: {member.display_name}")

                        # 50명마다 비동기 제어권 양보 (블로킹 방지)
                        if (idx + 1) % 50 == 0:
                            await asyncio.sleep(0)
                            print(f"  ⏸️ 처리 진행 중... ({idx + 1}/{len(role.members)})")

                    # 처리된 역할 정보 저장
                    processed_roles.append({
                        'role': role,
                        'total_members': len(role.members),
                        'added_members': role_added_count
                    })

                except Exception as e:
                    print(f"⚠️ 역할 처리 오류 ({role_id}): {e}")
                    if role_id not in invalid_roles:
                        invalid_roles.append(role_id)
                    continue

                # 역할 사이마다 비동기 제어권 양보
                await asyncio.sleep(0)
        
        print(f"✅ 자동 역할 실행 완료 - {added_count}명 대기열 추가")
        
        # 자동 역할 실행 완료 로그 전송
        embed = discord.Embed(
            title="🎯 자동 역할 실행 완료",
            description=f"**{added_count}명**이 대기열에 추가되었습니다.",
            color=0x00ff00
        )
        
        # 처리된 역할들 정보 (최대 10개)
        if processed_roles:
            role_info_lines = []
            for info in processed_roles[:10]:
                role_info_lines.append(
                    f"• {info['role'].mention}: {info['added_members']}/{info['total_members']}명 추가"
                )
            
            if len(processed_roles) > 10:
                role_info_lines.append(f"• ...그리고 {len(processed_roles) - 10}개 역할 더")
            
            embed.add_field(
                name="📋 처리된 역할",
                value="\n".join(role_info_lines),
                inline=False
            )
        
        # 무효한 역할이 있으면 표시
        if invalid_roles:
            embed.add_field(
                name="⚠️ 무효한 역할",
                value=f"{len(invalid_roles)}개의 역할을 찾을 수 없습니다.\n"
                      f"관리자는 `/자동역할 기능:정리`로 무효한 역할들을 제거할 수 있습니다.",
                inline=False
            )
        
        current_queue_size = queue_manager.get_queue_size()
        embed.add_field(
            name="📊 대기열 현황",
            value=f"현재 대기 중: **{current_queue_size}명**",
            inline=False
        )
        
        if current_queue_size > 0:
            # 개선된 시간 표시 사용
            time_str = format_estimated_time(current_queue_size, 36)
            embed.add_field(
                name="⏰ 예상 완료 시간",
                value=time_str,
                inline=False
            )
        
        # 429 오류 상태 정보 추가
        if rate_limit_detected:
            embed.add_field(
                name="⚠️ API 상태",
                value=f"API 속도 제한이 감지되었습니다.\n해제 예정: {rate_limit_until.strftime('%H:%M:%S')}",
                inline=False
            )
        
        embed.timestamp = datetime.now()
        
        await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)
        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)
        
    except Exception as e:
        print(f"❌ 자동 역할 실행 오류: {e}")
        
        # 자동 역할 실행 실패 로그 전송
        embed = discord.Embed(
            title="❌ 자동 역할 실행 실패",
            description="자동 역할 실행 중 오류가 발생했습니다.",
            color=0xff0000
        )
        
        embed.add_field(
            name="❌ 오류 내용",
            value=str(e)[:1000],
            inline=False
        )
        
        embed.timestamp = datetime.now()
        
        await send_log_message(bot, FAILURE_CHANNEL_ID, embed)