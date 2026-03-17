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
from newbie_config_manager import newbie_config_manager
from commands.admin.scheduler.newbie_check import update_newbie_list_message

try:
    from log_manager import bot_logger, LogCategory, send_log_message
except ImportError:
    bot_logger = None

try:
    from log_manager import get_logger
    logger = get_logger("scheduler")
except ImportError:
    import logging
    logger = logging.getLogger("scheduler")

# bulk_updater import
try:
    from bulk_updater import bulk_data_manager
    logger.info("bulk_updater에서 bulk_data_manager 로드됨 (scheduler.py)")
    BULK_ENABLED = True
except ImportError:
    logger.warning("bulk_updater를 찾을 수 없습니다. Bulk 기능이 비활성화됩니다.")
    bulk_data_manager = None
    BULK_ENABLED = False

# database_manager import (데이터베이스 기능)
try:
    from database_manager import db_manager
    logger.info("database_manager에서 db_manager 로드됨 (scheduler.py)")
    DATABASE_ENABLED = True
except ImportError:
    logger.warning("database_manager를 찾을 수 없습니다. 데이터베이스 기능이 비활성화됩니다.")
    db_manager = None
    DATABASE_ENABLED = False

# auto_role_manager import (role_manager.py에서 가져오기 시도)
try:
    from role_manager import auto_role_manager
    logger.info("role_manager에서 auto_role_manager 로드됨 (scheduler.py)")
except ImportError:
    try:
        # auto_roles.txt 파일을 직접 읽는 방식으로 대체
        logger.warning("auto_role_manager를 찾을 수 없어 기본 방식을 사용합니다.")
        
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
                    logger.error(f"역할 파일 읽기 실패: {e}")
                    return []
        
        auto_role_manager = SimpleAutoRoleManager()
        logger.info("간단한 자동역할 관리자 생성됨 (scheduler.py)")
        
    except Exception as e:
        logger.error(f"자동역할 기능을 사용할 수 없습니다: {e}")
        auto_role_manager = None

# town_role_manager 안전하게 import
try:
    from town_role_manager import town_role_manager
    logger.info("town_role_manager 모듈 로드됨 (scheduler.py)")
    TOWN_ROLE_ENABLED = True
except ImportError as e:
    logger.warning(f"town_role_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    logger.warning("마을 역할 기능이 비활성화됩니다.")
    town_role_manager = None
    TOWN_ROLE_ENABLED = False

# callsign_manager 안전하게 import
try:
    from callsign_manager import callsign_manager
    logger.info("callsign_manager 모듈 로드됨 (scheduler.py)")
    CALLSIGN_ENABLED = True
except ImportError as e:
    logger.warning(f"callsign_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    logger.warning("콜사인 기능이 비활성화됩니다.")
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
    logger.info("scheduler.py: config.py에서 환경변수 로드 완료")
    logger.info(f"- SUCCESS_ROLE_ID: {SUCCESS_ROLE_ID}")
    logger.info(f"- SUCCESS_ROLE_ID_OUT: {SUCCESS_ROLE_ID_OUT}")
except ImportError:
    # config.py가 없으면 직접 환경변수 로드
    logger.warning("config.py를 찾을 수 없어 직접 환경변수를 로드합니다.")
    MC_API_BASE = os.getenv("MC_API_BASE", "https://api.planetearth.kr")
    BASE_NATION = os.getenv("BASE_NATION", "Red_Mafia")
    SUCCESS_ROLE_ID = int(os.getenv("SUCCESS_ROLE_ID", "0"))
    SUCCESS_ROLE_ID_OUT = int(os.getenv("SUCCESS_ROLE_ID_OUT", "0"))  # 외국인 역할 ID
    SUCCESS_CHANNEL_ID = int(os.getenv("SUCCESS_CHANNEL_ID", "0"))
    FAILURE_CHANNEL_ID = int(os.getenv("FAILURE_CHANNEL_ID", "0"))
    AUTO_EXECUTION_DAY = int(os.getenv("AUTO_EXECUTION_DAY", "2"))
    AUTO_EXECUTION_HOUR = int(os.getenv("AUTO_EXECUTION_HOUR", "3"))
    AUTO_EXECUTION_MINUTE = int(os.getenv("AUTO_EXECUTION_MINUTE", "24"))
    logger.info("scheduler.py: 직접 환경변수 로드 완료")
    logger.info(f"- SUCCESS_ROLE_ID: {SUCCESS_ROLE_ID}")
    logger.info(f"- SUCCESS_ROLE_ID_OUT: {SUCCESS_ROLE_ID_OUT}")

# 스케줄러 인스턴스
# 봇 인스턴스 참조 저장
_bot_instance = None

# 429 오류 관리를 위한 전역 변수들
rate_limit_detected = False  # 429 오류 감지 상태
rate_limit_until = None      # 제한 해제 예상 시간
retry_counts = {}            # 사용자별 재시도 횟수 추적
MAX_RETRY_COUNT = 3          # 최대 재시도 횟수
bulk_failed_users = []       # Bulk 처리 실패한 사용자 ID 리스트 (3분마다 1명씩 재처리)

try:
    from alliance_manager import alliance_manager, is_friendly_nation, create_nation_role_if_needed
    logger.info("alliance_manager 모듈 로드됨 (scheduler.py)")
    ALLIANCE_ENABLED = True
except ImportError as e:
    logger.warning(f"alliance_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    alliance_manager = None
    ALLIANCE_ENABLED = False

try:
    from nation_role_manager import nation_role_manager
    logger.info("nation_role_manager 모듈 로드됨 (scheduler.py)")
    NATION_ROLE_ENABLED = True
except ImportError as e:
    logger.warning(f"nation_role_manager 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    nation_role_manager = None
    NATION_ROLE_ENABLED = False

# travel_scheduler import (여행 시스템)
try:
    from travel_scheduler import is_user_traveling, get_user_travel_destination
    logger.info("travel_scheduler 모듈 로드됨 (scheduler.py)")
    TRAVEL_ENABLED = True
except ImportError as e:
    logger.warning(f"travel_scheduler 모듈을 로드할 수 없습니다 (scheduler.py): {e}")
    is_user_traveling = lambda x: False
    get_user_travel_destination = lambda x: None
    TRAVEL_ENABLED = False

# update_user_info 함수 전체 (기존 함수를 완전히 대체)

async def update_user_info(member, mc_id, nation, guild, town=None, nation_uuid=None, town_uuid=None, bot=None, joined_town_at=None):
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
        bot: Discord bot 인스턴스 (선택)
    """
    changes = []

    try:
        # 여행 중인 사용자 체크 - 역할/닉네임 변경 건너뛰기 (마크 닉네임은 변경)
        if TRAVEL_ENABLED and is_user_traveling(member.id):
            travel_destination = get_user_travel_destination(member.id)
            logger.info(f"{member.display_name}님은 여행 중 (목적지: {travel_destination}) - 역할/닉네임 양식 변경 건너뛰기")
            # 여행 중에도 마크 닉네임은 업데이트 (DB에만 저장)
            if DATABASE_ENABLED and db_manager:
                user_info = db_manager.get_user_info(member.id)
                if user_info and user_info.get('minecraft_uuid'):
                    db_manager.add_or_update_user(member.id, user_info['minecraft_uuid'], mc_id)
            return ["✈️ 여행 중 - 역할/닉네임 양식 변경 건너뜀"]

        # 매핑된 마을 역할 처리 (무소속 제외)
        if TOWN_ROLE_ENABLED and town_role_manager:
            try:
                # 1. 먼저 기존 마을 역할들을 모두 제거
                all_mapped_towns = town_role_manager.get_all_mappings_flat()
                for mapping in all_mapped_towns:
                    mapped_town = mapping['town_name']
                    mapped_role_id = mapping['role_id']
                    if mapped_town != town:  # 현재 마을이 아닌 역할들만
                        mapped_role = guild.get_role(mapped_role_id)
                        if mapped_role and mapped_role in member.roles:
                            await member.remove_roles(mapped_role)
                            changes.append(f"• **{mapped_town}** 마을 역할 제거됨 (마을 변경)")
                            logger.info(f"이전 마을 역할 제거: {mapped_town}")

                # 2. 새 마을 역할 부여 (무소속이 아닌 경우)
                if town and town != "무소속" and town != "❌":
                    role_id = town_role_manager.get_role_id_by_name(town)
                    if role_id:
                        town_role = guild.get_role(role_id)
                        if town_role:
                            if town_role not in member.roles:
                                await member.add_roles(town_role)
                                changes.append(f"• **{town}** 마을 역할 추가됨")
                                logger.info(f"매핑된 마을 역할 부여: {town}")
                            else:
                                logger.debug(f"이미 마을 역할 보유: {town}")
                        else:
                            changes.append(f"• ⚠️ 마을 역할을 찾을 수 없음 (ID: {role_id})")
                            logger.warning(f"마을 역할 없음: {role_id}")
                    else:
                        logger.debug(f"`{town}` 마을은 역할이 매핑되지 않음")
                elif town == "무소속" or town == "❌":
                    logger.debug("무소속/정보없음 사용자 - 마을 역할 모두 제거됨")

            except Exception as e:
                changes.append(f"• ⚠️ 마을 역할 처리 실패: {str(e)[:50]}")
                logger.warning(f"마을 역할 처리 실패: {e}")
        elif town and not TOWN_ROLE_ENABLED:
            logger.debug(f"`{town}` 마을 - 마을 역할 기능 비활성화됨")

        # 국가 역할 변경 시 이전 국가 역할 제거
        if NATION_ROLE_ENABLED and nation_role_manager:
            try:
                # 모든 국가 역할 매핑 조회
                all_nation_mappings = nation_role_manager.get_all_nation_roles()

                for nation_name, role_data in all_nation_mappings.items():
                    if nation_name != nation:  # 현재 국가가 아닌 역할들만
                        old_role = guild.get_role(role_data['role_id'])
                        if old_role and old_role in member.roles:
                            await member.remove_roles(old_role)
                            changes.append(f"• **{nation_name}** 국가 역할 제거됨 (국가 변경)")
                            logger.info(f"이전 국가 역할 제거: {nation_name}")

            except Exception as e:
                logger.warning(f"이전 국가 역할 제거 실패: {e}")

        # 국가별 역할 부여 (UUID 기반 로직)
        try:
            from config import config
            from alliance_manager import is_friendly_nation as check_friendly

            base_nation = getattr(config, 'BASE_NATION', 'Red_Mafia')
            base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)
        except:
            base_nation = 'Red_Mafia'
            base_nation_uuid = None

        # UUID가 없으면 캐시에서 조회 + DB 보충 저장
        if not nation_uuid and nation and BULK_ENABLED and bulk_data_manager:
            _info = bulk_data_manager.get_nation_by_name(nation)
            if _info:
                nation_uuid = _info.get('uuid')

        if not town_uuid and town and BULK_ENABLED and bulk_data_manager:
            _info = bulk_data_manager.get_town_by_name(town)
            if _info:
                town_uuid = _info.get('uuid')

        # 캐시에서 찾은 UUID를 DB에 보충 저장 (다음 조회 시 중복 캐시 조회 방지)
        if (nation_uuid or town_uuid) and DATABASE_ENABLED and db_manager:
            try:
                discord_id_for_member = getattr(member, 'id', None)
                if discord_id_for_member:
                    db_manager.update_user_nation_info(
                        discord_id_for_member,
                        nation=nation, nation_uuid=nation_uuid,
                        town=town, town_uuid=town_uuid
                    )
                    db_manager.backfill_history_uuid(discord_id_for_member, nation_uuid=nation_uuid, town_uuid=town_uuid)
            except Exception:
                pass

        # 국가 확인 (UUID 기반 - 이름은 무시)
        is_base_nation = False
        is_alliance_nation = False

        if nation_uuid:
            # UUID 기반 비교
            is_base_nation = (nation_uuid == base_nation_uuid)
            if ALLIANCE_ENABLED and alliance_manager:
                is_alliance_nation = alliance_manager.is_alliance_uuid(nation_uuid)
        else:
            # nation_uuid 없음 → 이름 기반 fallback
            is_base_nation = (nation.lower() == base_nation.lower()) if (nation and base_nation) else False
            if ALLIANCE_ENABLED and alliance_manager:
                is_alliance_nation = alliance_manager.is_alliance_name(nation) if nation else False
            if is_base_nation:
                logger.warning(f"nation_uuid 없어서 이름 기반 fallback 사용: {nation} == {base_nation}")

        is_friendly = is_base_nation or is_alliance_nation

        # 디버그 로그
        if nation_uuid:
            logger.info(f"UUID 기반 국가 확인: {nation} (UUID: {nation_uuid[:8]}...)")
        else:
            logger.info(f"UUID 없음, 이름 기반 확인: {nation}")
        
        if is_base_nation:
            # 기본 국가(BASE_NATION) 국민 - 조직원 역할 부여
            logger.info(f"{base_nation} 기본 국가 국민 확인됨")

            # 조직원 역할(SUCCESS_ROLE_ID) 부여
            if SUCCESS_ROLE_ID != 0:
                success_role = guild.get_role(SUCCESS_ROLE_ID)
                if success_role:
                    if success_role not in member.roles:
                        try:
                            await member.add_roles(success_role)
                            changes.append(f"• **{success_role.name}** 역할 추가됨")
                            logger.info(f"조직원 역할 부여: {success_role.name}")
                        except Exception as e:
                            changes.append(f"• ⚠️ 조직원 역할 부여 실패: {str(e)[:50]}")
                            logger.warning(f"조직원 역할 부여 실패: {e}")
                    else:
                        logger.debug(f"이미 조직원 역할 보유: {success_role.name}")
                else:
                    logger.warning(f"조직원 역할을 찾을 수 없음 (ID: {SUCCESS_ROLE_ID})")

            # 뉴비 역할 처리 (기본 국가 국민에게만)
            # DB의 red_mafia_joined_at을 단일 진실 원천으로 사용
            newbie_role_id = newbie_config_manager.get_newbie_role()
            newbie_added = False
            if newbie_role_id:
                newbie_role = guild.get_role(newbie_role_id)
                if newbie_role:
                    # DB에서 기존 가입일 조회
                    existing_joined = None
                    if DATABASE_ENABLED and db_manager:
                        try:
                            existing_joined = db_manager.get_red_mafia_joined(member.id)
                        except Exception as e:
                            logger.warning(f"가입일 조회 실패: {e}")

                    if existing_joined is not None:
                        # === 이미 가입일이 있는 사용자 (DB 기준으로 판정) ===
                        days_since_join = (datetime.now() - existing_joined).days
                        if days_since_join <= 14:
                            # 뉴비 기간 내 - 역할 없으면 자동 부여
                            if newbie_role not in member.roles:
                                try:
                                    await member.add_roles(newbie_role)
                                    changes.append(f"• **{newbie_role.name}** 역할 추가됨 (뉴비 기간 내)")
                                    logger.info(f"뉴비 역할 자동 부여 (DB 기준 {days_since_join}일): {newbie_role.name}")
                                except Exception as e:
                                    changes.append(f"• ⚠️ 뉴비 역할 부여 실패: {str(e)[:50]}")
                                    logger.warning(f"뉴비 역할 부여 실패: {e}")
                            else:
                                logger.debug(f"이미 뉴비 역할 보유 (DB 기준 {days_since_join}일): {newbie_role.name}")
                        else:
                            # 뉴비 기간 만료 - 역할 있으면 제거
                            if newbie_role in member.roles:
                                try:
                                    await member.remove_roles(newbie_role)
                                    changes.append(f"• **{newbie_role.name}** 역할 제거됨 (2주 경과)")
                                    logger.info(f"뉴비 역할 제거 (DB 기준 {days_since_join}일 경과): {newbie_role.name}")
                                except Exception as e:
                                    logger.warning(f"뉴비 역할 제거 실패: {e}")
                            else:
                                logger.debug(f"이미 이전 가입일 존재 ({days_since_join}일 전) - 뉴비 아님")
                    else:
                        # === 가입일 없는 신규 사용자 (joinedTownAt으로 판정) ===
                        # 이전에 7일 이상 소속된 적이 있는지 확인 (복귀 멤버)
                        is_returning_member = False
                        if DATABASE_ENABLED and db_manager:
                            try:
                                is_returning_member = db_manager.was_member_of_nation(
                                    member.id, base_nation, min_days=7
                                )
                                if is_returning_member:
                                    logger.debug(f"복귀 멤버 (이전 {base_nation} 7일 이상 소속) - 뉴비 역할 제외")
                            except Exception as e:
                                logger.warning(f"복귀 멤버 확인 실패: {e}")

                        # 뉴비 판정: API joinedTownAt + nation_history 최초 기록 중 더 오래된 날짜 기준
                        is_newbie = False
                        joined_at_dt = None

                        if not is_returning_member:
                            # 1. nation_history에서 이 국가에 최초로 소속된 날짜 조회
                            oldest_history_dt = None
                            if DATABASE_ENABLED and db_manager:
                                try:
                                    oldest_history_dt = db_manager.get_earliest_nation_join(member.id, base_nation)
                                    if oldest_history_dt:
                                        logger.info(f"📜 nation_history 최초 기록일: {oldest_history_dt.strftime('%Y-%m-%d')}")
                                except Exception as e:
                                    logger.warning(f"최초 가입일 조회 실패: {e}")

                            # 2. API joinedTownAt 파싱
                            api_joined_dt = None
                            if joined_town_at:
                                try:
                                    api_joined_dt = datetime.fromtimestamp(joined_town_at / 1000)
                                except Exception as e:
                                    logger.warning(f"joinedTownAt 파싱 실패: {e}")

                            # 3. 후보 중 가장 오래된 날짜 = 실질 최초 가입일
                            candidates = [d for d in [oldest_history_dt, api_joined_dt] if d]
                            if candidates:
                                joined_at_dt = min(candidates)
                                days_since_join = (datetime.now() - joined_at_dt).days
                                is_newbie = days_since_join <= 14
                                logger.info(f"실질 최초 가입일: {joined_at_dt.strftime('%Y-%m-%d')} ({days_since_join}일 전) → {'뉴비' if is_newbie else '뉴비 아님'}")
                            else:
                                is_newbie = True
                                logger.debug("가입일 정보 없음 - 기본 뉴비 처리")

                        if is_newbie:
                            try:
                                await member.add_roles(newbie_role)
                                changes.append(f"• **{newbie_role.name}** 역할 추가됨")
                                logger.info(f"뉴비 역할 부여: {newbie_role.name}")
                                newbie_added = True

                                # 뉴비 가입일 기록 (joinedTownAt 또는 현재 시간)
                                if DATABASE_ENABLED and db_manager:
                                    try:
                                        save_dt = joined_at_dt if joined_at_dt else datetime.now()
                                        db_manager.set_red_mafia_joined(member.id, save_dt)
                                        logger.info(f"뉴비 가입일 기록: {save_dt.strftime('%Y-%m-%d %H:%M')}")
                                    except Exception as db_err:
                                        logger.warning(f"뉴비 가입일 기록 실패: {db_err}")
                            except Exception as e:
                                changes.append(f"• ⚠️ 뉴비 역할 부여 실패: {str(e)[:50]}")
                                logger.warning(f"뉴비 역할 부여 실패: {e}")
                        else:
                            # 뉴비가 아닌 경우에도 가입일은 DB에 기록 (추적용)
                            if DATABASE_ENABLED and db_manager and joined_at_dt:
                                try:
                                    db_manager.set_red_mafia_joined(member.id, joined_at_dt)
                                    logger.info(f"가입일 기록 (뉴비 아님): {joined_at_dt.strftime('%Y-%m-%d %H:%M')}")
                                except Exception as db_err:
                                    logger.warning(f"가입일 기록 실패: {db_err}")
                else:
                    logger.warning(f"뉴비 역할을 찾을 수 없음 (ID: {newbie_role_id})")

            # 뉴비 알림 스레드 생성 + 목록 메시지 업데이트 (뉴비 역할이 새로 부여된 경우에만)
            if newbie_added:
                await send_newbie_notification(guild, member, member.id, mc_id, nation)
                # 뉴비 목록 메시지 업데이트
                await update_newbie_list_message(bot)

            # 외국인 역할 제거
            if SUCCESS_ROLE_ID_OUT != 0:
                out_role = guild.get_role(SUCCESS_ROLE_ID_OUT)
                if out_role and out_role in member.roles:
                    try:
                        await member.remove_roles(out_role)
                        changes.append(f"• **{out_role.name}** 역할 제거됨")
                        logger.info(f"외국인 역할 제거: {out_role.name}")
                    except Exception as e:
                        changes.append(f"• ⚠️ 외국인 역할 제거 실패: {str(e)[:50]}")
                        logger.warning(f"외국인 역할 제거 실패: {e}")

            # 기본 국가도 국가별 역할 부여 (선택사항)
            if nation != "무소속":
                try:
                    nation_role = await create_nation_role_if_needed(guild, nation)

                    if nation_role:
                        if nation_role not in member.roles:
                            await member.add_roles(nation_role)
                            changes.append(f"• **{nation_role.name}** 국가 역할 추가됨")
                            logger.info(f"기본 국가 역할 부여: {nation_role.name}")
                        else:
                            logger.debug(f"이미 기본 국가 역할 보유: {nation_role.name}")

                except Exception as e:
                    changes.append(f"• ⚠️ 국가 역할 처리 실패: {str(e)[:50]}")
                    logger.warning(f"국가 역할 처리 실패 ({nation}): {e}")

        elif is_alliance_nation:
            # 동맹 국가 국민 - 외국인 역할 + 국가별 역할 부여
            logger.info(f"{nation} 동맹 국가 국민 확인됨")

            # 뉴비 역할 제거 + 스레드 삭제 (외국인은 뉴비 아님)
            await remove_newbie_and_thread(guild, member, mc_id, bot)

            # 외국인 역할(SUCCESS_ROLE_ID_OUT) 부여
            if SUCCESS_ROLE_ID_OUT != 0:
                out_role = guild.get_role(SUCCESS_ROLE_ID_OUT)
                if out_role:
                    if out_role not in member.roles:
                        try:
                            await member.add_roles(out_role)
                            changes.append(f"• **{out_role.name}** 역할 추가됨 (동맹)")
                            logger.info(f"외국인 역할 부여: {out_role.name}")
                        except Exception as e:
                            changes.append(f"• ⚠️ 외국인 역할 부여 실패: {str(e)[:50]}")
                            logger.warning(f"외국인 역할 부여 실패: {e}")
                    else:
                        logger.debug(f"이미 외국인 역할 보유: {out_role.name}")
                else:
                    logger.warning(f"외국인 역할을 찾을 수 없음 (ID: {SUCCESS_ROLE_ID_OUT})")

            # 조직원 역할 제거
            if SUCCESS_ROLE_ID != 0:
                success_role = guild.get_role(SUCCESS_ROLE_ID)
                if success_role and success_role in member.roles:
                    try:
                        await member.remove_roles(success_role)
                        changes.append(f"• **{success_role.name}** 역할 제거됨")
                        logger.info(f"조직원 역할 제거: {success_role.name}")
                    except Exception as e:
                        changes.append(f"• ⚠️ 조직원 역할 제거 실패: {str(e)[:50]}")
                        logger.warning(f"조직원 역할 제거 실패: {e}")

            # 동맹 국가별 역할 부여
            if nation != "무소속":
                try:
                    # 국가 역할이 없으면 자동 생성
                    nation_role = await create_nation_role_if_needed(guild, nation)

                    if nation_role:
                        if nation_role not in member.roles:
                            await member.add_roles(nation_role)
                            changes.append(f"• **{nation_role.name}** 국가 역할 추가됨")
                            logger.info(f"동맹 국가 역할 부여: {nation_role.name}")
                        else:
                            logger.debug(f"이미 국가 역할 보유: {nation_role.name}")
                    else:
                        changes.append(f"• ⚠️ {nation} 국가 역할 생성/부여 실패")
                        logger.warning(f"{nation} 국가 역할 처리 실패")

                except Exception as e:
                    changes.append(f"• ⚠️ 국가 역할 처리 실패: {str(e)[:50]}")
                    logger.warning(f"국가 역할 처리 실패 ({nation}): {e}")
            
        else:
            # 외국인 또는 무소속
            if nation == "무소속":
                logger.info("무소속 사용자 확인됨 - 외국인 역할 부여")
            else:
                logger.info(f"외국인 확인됨: {nation}")

            # 뉴비 역할 제거 + 스레드 삭제 (외국인은 뉴비 아님)
            await remove_newbie_and_thread(guild, member, mc_id, bot)

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
                            logger.info(f"외국인 역할 부여: {out_role.name}")
                        except Exception as e:
                            changes.append(f"• ⚠️ 외국인 역할 부여 실패: {str(e)[:50]}")
                            logger.warning(f"외국인 역할 부여 실패: {e}")
                    else:
                        logger.debug(f"이미 외국인 역할 보유: {out_role.name}")
                else:
                    logger.warning(f"외국인 역할을 찾을 수 없음 (ID: {SUCCESS_ROLE_ID_OUT})")
            
            # 국민 역할 제거
            if SUCCESS_ROLE_ID != 0:
                success_role = guild.get_role(SUCCESS_ROLE_ID)
                if success_role and success_role in member.roles:
                    try:
                        await member.remove_roles(success_role)
                        changes.append(f"• **{success_role.name}** 역할 제거됨")
                        logger.info(f"국민 역할 제거: {success_role.name}")
                    except Exception as e:
                        changes.append(f"• ⚠️ 국민 역할 제거 실패: {str(e)[:50]}")
                        logger.warning(f"국민 역할 제거 실패: {e}")
            
            # 외국인 국가에도 국가별 역할 부여 (선택사항)
            if nation != "무소속":
                try:
                    # 외국인도 국가별 역할을 원한다면 이 부분 활성화
                    nation_role = await create_nation_role_if_needed(guild, nation)
                    
                    if nation_role:
                        if nation_role not in member.roles:
                            await member.add_roles(nation_role)
                            changes.append(f"• **{nation_role.name}** 외국 국가 역할 추가됨")
                            logger.info(f"외국 국가 역할 부여: {nation_role.name}")
                        else:
                            logger.debug(f"이미 외국 국가 역할 보유: {nation_role.name}")
                            
                except Exception as e:
                    changes.append(f"• ⚠️ 외국 국가 역할 처리 실패: {str(e)[:50]}")
                    logger.warning(f"외국 국가 역할 처리 실패 ({nation}): {e}")

        # 역할 부여 완료 후 닉네임 변경 (역할 양식 적용)
        role_format = None
        applied_format_name = None
        if CALLSIGN_ENABLED and callsign_manager:
            try:
                # 1. 먼저 SUCCESS_ROLE_ID_OUT 역할이 있는지 확인 (최우선)
                if SUCCESS_ROLE_ID_OUT != 0:
                    out_role = guild.get_role(SUCCESS_ROLE_ID_OUT)
                    if out_role and out_role in member.roles:
                        format_str = callsign_manager.get_role_format(SUCCESS_ROLE_ID_OUT)
                        if format_str:
                            role_format = format_str
                            applied_format_name = out_role.name
                            logger.info(f"외국인 역할 양식 적용 (우선): {out_role.name} - {format_str}")

                # 2. SUCCESS_ROLE_ID_OUT 양식이 없으면 다른 역할 양식 찾기
                if not role_format:
                    # 역할 우선순위 순으로 정렬 (position이 높을수록 우선순위가 높음)
                    sorted_roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
                    for role in sorted_roles:
                        format_str = callsign_manager.get_role_format(role.id)
                        if format_str:
                            role_format = format_str
                            applied_format_name = role.name
                            logger.info(f"역할 양식 적용: {role.name} - {format_str}")
                            break
            except Exception as e:
                logger.warning(f"역할 양식 확인 실패: {e}")

        # 새 닉네임 생성
        current_nickname = member.display_name

        if role_format:
            # 역할 양식이 있으면 양식 적용
            user_callsign = None

            # 콜사인 조회
            if CALLSIGN_ENABLED and callsign_manager:
                try:
                    user_callsign = callsign_manager.get_callsign(member.id)
                    if user_callsign:
                        logger.info(f"콜사인 조회됨: {user_callsign}")
                except Exception as e:
                    logger.warning(f"콜사인 조회 실패: {e}")

            # MC 정보가 없으면 ❌[ MC ] ❌로 표시
            display_mc_id = mc_id if mc_id else "❌[ MC ] ❌"

            # 양식 적용
            new_nickname = callsign_manager.apply_format_to_nickname(
                role_format,
                mc_id=display_mc_id,
                nation=nation,
                town=town,
                callsign=user_callsign,
                discord_joined_at=member.joined_at
            )
            logger.info(f"역할 양식 적용됨: {new_nickname}")
        else:
            # 역할 양식이 없으면 닉네임 변경하지 않음
            logger.debug("역할 양식 없음 - 닉네임 변경 건너뜀")
            new_nickname = None

        try:
            if new_nickname and current_nickname != new_nickname:
                # 3초 대기 후 닉네임 변경
                logger.info("닉네임 변경 대기 중... (3초)")
                await asyncio.sleep(3)
                await member.edit(nick=new_nickname)
                if applied_format_name:
                    changes.append(f"• 닉네임이 **``{new_nickname}``**로 변경됨 (🎭 {applied_format_name} 역할 양식)")
                else:
                    changes.append(f"• 닉네임이 **``{new_nickname}``**로 변경됨")
                logger.info(f"닉네임 변경: {current_nickname} → {new_nickname}")
            else:
                logger.debug(f"닉네임 유지: {new_nickname}")
        except discord.Forbidden:
            changes.append("• ⚠️ 닉네임 변경 권한 없음")
            logger.warning("닉네임 변경 권한 없음")
        except Exception as e:
            changes.append(f"• ⚠️ 닉네임 변경 실패: {str(e)[:50]}")
            logger.warning(f"닉네임 변경 실패: {e}")

        return changes

    except Exception as e:
        logger.error(f"사용자 정보 업데이트 실패: {e}")
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
        logger.warning(f"예외 사용자 확인 오류: {e}")
        return False

def setup_scheduler(bot):
    """스케줄러 설정 함수 (main.py에서 호출) - 누락된 함수 추가"""
    logger.info("스케줄러 설정 시작...")
    start_scheduler(bot)

def get_scheduler_info():
    """백그라운드 태스크 상태 정보를 반환 (discord.ext.tasks 기반)"""
    try:
        # 백그라운드 루프 실행 상태 - 3개의 병렬 대기열
        queue_loops = [queue_processor_loop_1, queue_processor_loop_2, queue_processor_loop_3]
        queue_running = [loop.is_running() for loop in queue_loops]
        any_queue_running = any(queue_running)
        auto_roles_running = auto_roles_checker.is_running()

        # 등록된 작업들
        jobs = []

        # 3개의 병렬 대기열 처리 루프 정보
        for i, (loop, running) in enumerate(zip(queue_loops, queue_running), 1):
            if running:
                if loop.next_iteration:
                    next_run = loop.next_iteration.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    next_run = "곧 실행"

                queue_size = queue_manager.get_queue_size(i-1)
                jobs.append({
                    "id": f"queue_processor_{i}",
                    "name": f"대기열 {i} 처리",
                    "next_run": next_run,
                    "interval": "1분마다",
                    "queue_size": queue_size
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

        # 뉴비 스레드 유지 루프 정보
        if newbie_thread_keeper.is_running():
            next_run = newbie_thread_keeper.next_iteration.strftime("%Y-%m-%d %H:%M:%S") if newbie_thread_keeper.next_iteration else "곧 실행"
            jobs.append({
                "id": "newbie_thread_keeper",
                "name": "뉴비 스레드 유지",
                "next_run": next_run,
                "interval": "12시간마다"
            })

        # 대기열 상태 정보
        queue_status = queue_manager.get_status()

        # 상태 정보
        status_info = {
            "running": any_queue_running or auto_roles_running,
            "queue_loop_running": any_queue_running,
            "queue_loops_status": queue_running,  # [True, True, True] 형태
            "auto_roles_loop_running": auto_roles_running,
            "jobs": jobs,
            "auto_execution_day": AUTO_EXECUTION_DAY,
            "auto_execution_hour": AUTO_EXECUTION_HOUR,
            "auto_execution_minute": AUTO_EXECUTION_MINUTE,
            "rate_limit_detected": rate_limit_detected,
            "rate_limit_until": rate_limit_until.strftime("%Y-%m-%d %H:%M:%S") if rate_limit_until else None,
            "retry_queue_size": len(retry_counts),
            "queue_status": queue_status  # 대기열 상세 상태 정보
        }

        return status_info
    except Exception as e:
        logger.info(f"백그라운드 태스크 정보 조회 오류: {e}")
        return {
            "running": False,
            "queue_loop_running": False,
            "queue_loops_status": [False, False, False],
            "auto_roles_loop_running": False,
            "jobs": [],
            "auto_execution_day": AUTO_EXECUTION_DAY,
            "auto_execution_hour": AUTO_EXECUTION_HOUR,
            "auto_execution_minute": AUTO_EXECUTION_MINUTE,
            "rate_limit_detected": False,
            "rate_limit_until": None,
            "retry_queue_size": 0,
            "queue_status": {"total_size": 0, "queue_sizes": [0, 0, 0], "processing": [False, False, False], "any_processing": False}
        }
    


def handle_rate_limit():
    """429 오류 감지 시 호출되는 함수"""
    global rate_limit_detected, rate_limit_until

    rate_limit_detected = True
    rate_limit_until = datetime.now() + timedelta(minutes=5)
    rate_limit_unix = int(rate_limit_until.timestamp())

    logger.error(f"🚨 API 속도 제한 감지! 5분간 대기 ({rate_limit_until.strftime('%H:%M:%S')}까지, Unix: {rate_limit_unix})")

def is_rate_limited() -> bool:
    """현재 API 속도 제한 상태인지 확인"""
    global rate_limit_detected, rate_limit_until
    
    if not rate_limit_detected:
        return False
    
    if datetime.now() >= rate_limit_until:
        # 제한 시간이 지났으면 상태 초기화
        rate_limit_detected = False
        rate_limit_until = None
        logger.info("API 속도 제한 해제")
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

# 글로벌 CSV 데이터 수집 리스트 및 자동 실행 플래그
_csv_data_collection = []
_is_auto_execution = False  # 스케줄러 자동 실행 여부

# 대기열 처리 통계 (모든 큐의 결과를 누적)
_queue_stats = {
    'total_queued': 0,         # 대기열에 추가된 총 사용자 수
    'bulk_processed': 0,       # Bulk 모드로 처리된 수
    'individual_processed': 0, # 개별 모드로 처리된 수
    'no_uuid': 0,              # UUID 없음 (후순위)
    'no_bulk_data': 0,         # Bulk 데이터 없음 (후순위)
    'not_in_guild': 0,         # 서버 탈퇴
    'nation_roles_new': 0,     # 국가 역할 새로 부여
    'nation_roles_existing': 0,# 국가 역할 이미 보유
    'failed': 0,               # 실패
    'bulk_mode_used': False,   # Bulk 모드 사용 여부
}

def _reset_queue_stats():
    """대기열 처리 통계 초기화"""
    global _queue_stats
    _queue_stats = {
        'total_queued': 0,
        'bulk_processed': 0,
        'individual_processed': 0,
        'no_uuid': 0,
        'no_bulk_data': 0,
        'not_in_guild': 0,
        'nation_roles_new': 0,
        'nation_roles_existing': 0,
        'failed': 0,
        'bulk_mode_used': False,
    }

def add_to_csv_collection(user_data: dict):
    """CSV 데이터 수집 리스트에 사용자 정보 추가 (자동 실행 시에만)"""
    global _csv_data_collection, _is_auto_execution

    # 자동 실행 중일 때만 CSV 데이터 수집
    if _is_auto_execution:
        _csv_data_collection.append(user_data)
    else:
        # 자동 실행이 아닐 때는 수집하지 않음
        pass

def save_csv_report():
    """수집된 데이터를 CSV 파일로 저장 (data/csv_exports 폴더) - 10명 이상일 때만"""
    global _csv_data_collection

    try:
        if not _csv_data_collection:
            logger.info("CSV 저장: 데이터 없음")
            return None

        # 10명 미만이면 CSV 파일 생성하지 않음
        if len(_csv_data_collection) < 10:
            logger.info(f"CSV 저장 건너뜀: 인원 부족 ({len(_csv_data_collection)}명 < 10명)")
            # 데이터 초기화
            _csv_data_collection = []
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

        logger.info(f"CSV 보고서 저장 완료: {filepath} ({len(_csv_data_collection)}건)")

        # 데이터 초기화
        _csv_data_collection = []

        return filepath

    except Exception as e:
        logger.error(f"CSV 저장 실패: {e}")
        return None

async def remove_newbie_and_thread(guild, member, mc_name: str, bot=None):
    """
    외국인으로 판정된 경우 뉴비 역할 제거 및 관련 스레드 삭제
    단, DB 기준 2주 이내인 뉴비는 역할을 유지 (오탐 방지)

    Args:
        guild: Discord 길드
        member: Discord 멤버
        mc_name: 마인크래프트 닉네임
        bot: Discord 봇 (뉴비 목록 업데이트용)
    """
    try:
        newbie_removed = False

        # 1. 뉴비 역할 제거 (2주 체크 후)
        newbie_role_id = newbie_config_manager.get_newbie_role()
        if newbie_role_id:
            newbie_role = guild.get_role(newbie_role_id)
            if newbie_role and newbie_role in member.roles:
                # DB에서 가입일 확인 - 2주 이내면 역할 유지 (오탐 방지)
                should_remove = True
                if DATABASE_ENABLED and db_manager:
                    try:
                        existing_joined = db_manager.get_red_mafia_joined(member.id)
                        if existing_joined:
                            days_since_join = (datetime.now() - existing_joined).days
                            if days_since_join <= 14:
                                should_remove = False
                                logger.debug(f"뉴비 기간 내 ({days_since_join}일) - 역할 유지 (외국인 판정 무시)")
                    except Exception as db_err:
                        logger.warning(f"가입일 확인 실패: {db_err}")

                if should_remove:
                    try:
                        await member.remove_roles(newbie_role)
                        logger.info(f"뉴비 역할 제거됨: {newbie_role.name} (외국인 판정)")
                        newbie_removed = True

                        # DB에서 가입일 초기화 (재가입 시 새 가입일이 기록되도록)
                        if DATABASE_ENABLED and db_manager:
                            try:
                                db_manager.clear_red_mafia_joined(member.id)
                                logger.info("가입일 초기화됨 (외국인 판정)")
                            except Exception as db_err:
                                logger.warning(f"가입일 초기화 실패: {db_err}")
                    except Exception as e:
                        logger.warning(f"뉴비 역할 제거 실패: {e}")

        # 2. 뉴비 스레드 찾아서 삭제
        channel_id = newbie_config_manager.get_notification_channel()
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                # 스레드 이름 패턴: "🆕 {mc_name}"
                thread_name = f"🆕 {mc_name}"

                # 채널의 모든 스레드 확인
                try:
                    # 활성 스레드 확인
                    for thread in channel.threads:
                        if thread.name == thread_name or thread.name.startswith(f"🆕 {mc_name}"):
                            try:
                                await thread.delete()
                                logger.info(f"뉴비 스레드 삭제됨: {thread.name} (외국인 판정)")
                            except Exception as e:
                                logger.warning(f"스레드 삭제 실패: {e}")
                            break

                    # 아카이브된 스레드도 확인
                    async for thread in channel.archived_threads(limit=50):
                        if thread.name == thread_name or thread.name.startswith(f"🆕 {mc_name}"):
                            try:
                                await thread.delete()
                                logger.info(f"아카이브된 뉴비 스레드 삭제됨: {thread.name} (외국인 판정)")
                            except Exception as e:
                                logger.warning(f"아카이브된 스레드 삭제 실패: {e}")
                            break
                except Exception as e:
                    logger.warning(f"스레드 검색 실패: {e}")

        # 3. 뉴비 목록 메시지 업데이트
        if newbie_removed and bot:
            await update_newbie_list_message(bot)

    except Exception as e:
        logger.warning(f"뉴비 역할/스레드 제거 실패: {e}")


async def send_newbie_notification(guild, member, discord_id: int, mc_name: str, nation: str):
    """
    뉴비 알림 채널에 스레드 생성 및 알림 전송

    Args:
        guild: Discord 길드
        member: Discord 멤버
        discord_id: 디스코드 ID
        mc_name: 마인크래프트 닉네임
        nation: 국가
    """
    try:
        from database_manager import db_manager

        # 알림 채널 확인
        channel_id = newbie_config_manager.get_notification_channel()
        if not channel_id:
            logger.debug("뉴비 알림 채널이 설정되지 않음")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(f"뉴비 알림 채널을 찾을 수 없음: {channel_id}")
            return

        # 핑 역할 목록
        ping_roles = newbie_config_manager.get_ping_roles()

        # 사용자 정보 조회
        user_info = None
        name_history = []
        nation_history = []
        if DATABASE_ENABLED and db_manager:
            try:
                user_info = db_manager.get_user_info(discord_id)
                name_history = db_manager.get_name_history(discord_id, limit=5)
                nation_history = db_manager.get_nation_history(discord_id, limit=3)
            except:
                pass

        # 임베드 생성
        embed = discord.Embed(
            title="🆕 새로운 뉴비가 Red Mafia에 가입했습니다!",
            color=0x00ff00,
            timestamp=datetime.now()
        )

        # 기본 정보
        embed.add_field(
            name="👤 디스코드",
            value=f"{member.mention}\n`{member.name}`",
            inline=True
        )

        embed.add_field(
            name="🎮 마인크래프트",
            value=f"`{mc_name}`",
            inline=True
        )

        embed.add_field(
            name="🏴 국가",
            value=f"`{nation}`",
            inline=True
        )

        # 서버 최초 가입일
        if user_info and user_info.get('first_seen'):
            first_seen = user_info['first_seen']
            if hasattr(first_seen, 'strftime'):
                embed.add_field(
                    name="📅 서버 최초 가입일",
                    value=first_seen.strftime("%Y-%m-%d %H:%M"),
                    inline=True
                )

        # 이름 히스토리
        if name_history and len(name_history) > 1:
            history_text = "\n".join([f"• `{h.get('minecraft_name', '?')}`" for h in name_history[:5]])
            embed.add_field(
                name="📝 닉네임 히스토리",
                value=history_text,
                inline=False
            )

        # 국가 히스토리
        if nation_history and len(nation_history) > 1:
            nation_lines = []
            for h in nation_history[:3]:
                nation_val = h.get('nation_name') or '무소속'
                town_val = h.get('town_name') or '없음'
                nation_lines.append(f"• `{nation_val}` / `{town_val}`")
            history_text = "\n".join(nation_lines)
            embed.add_field(
                name="🌍 국가 히스토리",
                value=history_text,
                inline=False
            )

        # 스레드 이름 생성
        thread_name = f"🆕 {mc_name}"
        if len(thread_name) > 100:
            thread_name = thread_name[:100]

        # 이미 같은 이름의 스레드가 있는지 확인 (중복 방지)
        existing_thread = None
        try:
            # 활성 스레드에서 검색
            for thread in channel.threads:
                if thread.name == thread_name or thread.name.startswith(f"🆕 {mc_name}"):
                    existing_thread = thread
                    break

            # 아카이브된 스레드에서도 검색
            if not existing_thread:
                async for thread in channel.archived_threads(limit=50):
                    if thread.name == thread_name or thread.name.startswith(f"🆕 {mc_name}"):
                        existing_thread = thread
                        break
        except Exception as search_error:
            logger.warning(f"스레드 검색 중 오류: {search_error}")

        # 이미 스레드가 있으면 생성하지 않음
        if existing_thread:
            logger.debug(f"뉴비 스레드가 이미 존재함: {existing_thread.name} - 스레드 생성 건너뜀")
            return

        try:
            # 공개 스레드 생성
            thread = await channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread
            )

            # 멘션 메시지 생성
            mentions = [member.mention]  # 뉴비 본인
            if ping_roles:
                for role_id in ping_roles:
                    role = guild.get_role(role_id)
                    if role:
                        mentions.append(role.mention)

            ping_content = " ".join(mentions) + " 님이 Red Mafia에 가입했습니다!"

            # 스레드에 임베드 + 멘션 메시지 전송
            await thread.send(content=ping_content, embed=embed)

            logger.info(f"뉴비 스레드 생성됨: {thread.name}")

        except discord.Forbidden:
            # 스레드 생성 권한이 없으면 일반 메시지로 전송
            logger.warning("스레드 생성 권한 없음, 일반 메시지로 전송")
            mentions = [member.mention]
            if ping_roles:
                for role_id in ping_roles:
                    role = guild.get_role(role_id)
                    if role:
                        mentions.append(role.mention)

            ping_content = " ".join(mentions)
            await channel.send(content=ping_content, embed=embed)
            logger.info(f"뉴비 알림 전송됨: {member.name} -> #{channel.name}")

        except Exception as e:
            logger.warning(f"스레드 생성 실패: {e}")
            # 일반 메시지로 전송
            await channel.send(embed=embed)

    except Exception as e:
        logger.error(f"뉴비 알림 전송 실패: {e}")
        import traceback
        traceback.print_exc()


async def send_rate_limit_notification(bot):
    """429 오류 발생 시 알림 메시지 전송"""
    try:
        embed = discord.Embed(
            title="⏰ API 속도 제한 감지",
            description="API 속도 제한으로 인해 5분간 처리를 일시 중단합니다.",
            color=0xffaa00
        )

        # Unix 타임스탬프 계산
        rate_limit_unix = int(rate_limit_until.timestamp())

        embed.add_field(
            name="📊 현재 상황",
            value=f"• **제한 해제 시간**: <t:{rate_limit_unix}:F> (<t:{rate_limit_unix}:R>)\n"
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
        # 성공/실패 채널이 다른 경우에만 성공 채널에도 전송
        if SUCCESS_CHANNEL_ID != FAILURE_CHANNEL_ID:
            await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)

    except Exception as e:
        logger.error(f"속도 제한 알림 전송 실패: {e}")

async def manual_execute_auto_roles(bot):
    """자동 역할 부여를 수동으로 실행 - 새로운 자동역할 관리자 사용"""
    try:
        logger.info("수동 자동 역할 실행 시작")
        _reset_queue_stats()

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
            logger.info(f"길드 처리: {guild.name}")
            
            for role_id in role_ids:
                try:
                    role = guild.get_role(role_id)
                    
                    if not role:
                        logger.warning(f"역할을 찾을 수 없음: {role_id}")
                        if role_id not in invalid_roles:
                            invalid_roles.append(role_id)
                        continue
                    
                    logger.info(f"역할 '{role.name}' 멤버 {len(role.members)}명 처리 중")
                    
                    role_added_count = 0
                    for member in role.members:
                        # 예외 목록 확인
                        if exception_manager.is_exception(member.id):
                            logger.info(f"예외 대상 건너뜀: {member.display_name}")
                            continue

                        # 대기열에 추가
                        if queue_manager.add_user(member.id):
                            added_count += 1
                            role_added_count += 1
                            logger.info(f"대기열 추가: {member.display_name}")
                            if bot_logger:
                                bot_logger.log_queue("자동역할 실행 - 대기열 추가", target_user_id=member.id, source="scheduler", action="queue_add", details={"trigger": "auto_role_execution"})
                        else:
                            logger.info(f"이미 대기열에 있음: {member.display_name}")

                    # 처리된 역할 정보 저장
                    processed_roles.append({
                        'role': role,
                        'total_members': len(role.members),
                        'added_members': role_added_count
                    })
                    
                except Exception as e:
                    logger.warning(f"역할 처리 오류 ({role_id}): {e}")
                    if role_id not in invalid_roles:
                        invalid_roles.append(role_id)
                    continue
        
        logger.info(f"자동 역할 실행 완료 - {added_count}명 대기열 추가")
        
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
            # 개선된 시간 표시 사용 (20초/명으로 계산)
            time_str = format_estimated_time(current_queue_size, 20)
            embed.add_field(
                name="⏰ 예상 완료 시간",
                value=time_str,
                inline=False
            )
        
        embed.timestamp = datetime.now()

        await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)
        # 성공/실패 채널이 다른 경우에만 실패 채널에도 전송
        if FAILURE_CHANNEL_ID != SUCCESS_CHANNEL_ID:
            await send_log_message(bot, FAILURE_CHANNEL_ID, embed)

        return {
            "success": True,
            "message": f"{added_count}명이 대기열에 추가되었습니다.",
            "added_count": added_count,
            "processed_roles": len(processed_roles),
            "invalid_roles": len(invalid_roles)
        }

    except Exception as e:
        logger.error(f"자동 역할 실행 오류: {e}")
        
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

# Discord.py tasks를 사용한 백그라운드 루프 - 3개의 병렬 대기열
# 대기열 처리 루프 1
@tasks.loop(minutes=1)
async def queue_processor_loop_1():
    """대기열 1 처리 루프 - 1분마다 실행"""
    global _bot_instance
    if _bot_instance is None:
        return
    try:
        await process_queue_batch(_bot_instance, queue_index=0)
    except Exception as e:
        logger.error(f"대기열 1 처리 루프 오류: {e}")
        import traceback
        traceback.print_exc()

@queue_processor_loop_1.before_loop
async def before_queue_processor_1():
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        logger.info("대기열 1 처리 루프 준비 완료")

# 대기열 처리 루프 2
@tasks.loop(minutes=1)
async def queue_processor_loop_2():
    """대기열 2 처리 루프 - 1분마다 실행"""
    global _bot_instance
    if _bot_instance is None:
        return
    try:
        await process_queue_batch(_bot_instance, queue_index=1)
    except Exception as e:
        logger.error(f"대기열 2 처리 루프 오류: {e}")
        import traceback
        traceback.print_exc()

@queue_processor_loop_2.before_loop
async def before_queue_processor_2():
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        logger.info("대기열 2 처리 루프 준비 완료")

# 대기열 처리 루프 3
@tasks.loop(minutes=1)
async def queue_processor_loop_3():
    """대기열 3 처리 루프 - 1분마다 실행"""
    global _bot_instance
    if _bot_instance is None:
        return
    try:
        await process_queue_batch(_bot_instance, queue_index=2)
    except Exception as e:
        logger.error(f"대기열 3 처리 루프 오류: {e}")
        import traceback
        traceback.print_exc()

@queue_processor_loop_3.before_loop
async def before_queue_processor_3():
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        logger.info("대기열 3 처리 루프 준비 완료")

# 하위 호환성을 위한 별칭 (기존 코드에서 참조할 경우)
queue_processor_loop = queue_processor_loop_1

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

            logger.info(f"자동 역할 실행 시간 도달: {now.strftime('%Y-%m-%d %H:%M')}")

            # 백그라운드로 실행 (블로킹 방지)
            asyncio.create_task(execute_auto_roles(_bot_instance))

    except Exception as e:
        logger.error(f"자동 역할 체크 루프 오류: {e}")

@auto_roles_checker.before_loop
async def before_auto_roles_checker():
    """자동 역할 체크 시작 전 봇 준비 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        logger.info("자동 역할 체크 루프 준비 완료")

@tasks.loop(minutes=5)
async def bulk_data_updater():
    """Bulk 데이터 업데이트 루프 - 5분마다 실행"""
    if not BULK_ENABLED or not bulk_data_manager:
        return

    try:
        logger.info("Bulk 데이터 업데이트 시작 (5분 주기)")
        # 비동기적으로 bulk 데이터 가져오기
        await asyncio.to_thread(bulk_data_manager.fetch_bulk_data, save_to_db=True)

        # 통계 출력
        stats = bulk_data_manager.get_stats()
        logger.info(f"총 주민: {stats['total_residents']}명")
        logger.info(f"총 국가: {stats['total_nations']}개")
        logger.info(f"🏘️ 총 마을: {stats['total_towns']}개")
        logger.info(f"⏱️ 마지막 업데이트: {stats['last_update']}")

    except Exception as e:
        logger.error(f"Bulk 데이터 업데이트 오류: {e}")
        import traceback
        traceback.print_exc()

@bulk_data_updater.before_loop
async def before_bulk_data_updater():
    """Bulk 데이터 업데이트 시작 전 봇 준비 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        logger.info("Bulk 데이터 업데이트 루프 준비 완료")

@tasks.loop(minutes=3)
async def bulk_failed_retry_loop():
    """Bulk 처리 실패한 사용자를 3분마다 대기열에 추가하여 재처리"""
    global _bot_instance, bulk_failed_users

    if _bot_instance is None:
        return

    if not bulk_failed_users:
        return

    # 속도 제한 상태 확인
    if is_rate_limited():
        logger.info("[RETRY] API 속도 제한 중 - 재처리 건너뜀")
        return

    # 최대 5명씩 대기열에 추가
    batch_size = min(5, len(bulk_failed_users))
    batch = bulk_failed_users[:batch_size]
    bulk_failed_users = bulk_failed_users[batch_size:]
    remaining = len(bulk_failed_users)

    added = 0
    for user_id in batch:
        if not queue_manager.is_user_in_queue(user_id):
            queue_manager.add_user_back(user_id)  # 대기열 뒤에 추가
            added += 1
            logger.info(f"[RETRY] Bulk 실패 사용자 대기열 추가: {user_id}")
        else:
            logger.info(f"[RETRY] 이미 대기열에 있음: {user_id}")

    logger.info(f"[RETRY] {added}명 대기열 추가 완료 (남은 재처리 대기: {remaining}명)")

    if not bulk_failed_users:
        logger.info("[RETRY] 모든 Bulk 실패 사용자를 대기열에 추가 완료!")

@bulk_failed_retry_loop.before_loop
async def before_bulk_failed_retry_loop():
    """Bulk 실패 재처리 루프 시작 전 봇 준비 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        logger.info("Bulk 실패 재처리 루프 준비 완료 (3분마다)")

@tasks.loop(hours=12)
async def newbie_thread_keeper():
    """아카이브된 뉴비 스레드를 자동으로 다시 열어주는 루프 (12시간마다)"""
    global _bot_instance

    if _bot_instance is None:
        return

    try:
        from config import config
        from database_manager import db_manager

        guild = _bot_instance.get_guild(config.GUILD_ID)
        if not guild:
            return

        # 뉴비 알림 채널 확인
        channel_id = newbie_config_manager.get_notification_channel()
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # 뉴비 역할 확인
        newbie_role_id = newbie_config_manager.get_newbie_role()
        if not newbie_role_id:
            return

        newbie_role = guild.get_role(newbie_role_id)
        if not newbie_role:
            return

        # 현재 뉴비 멤버들의 MC 닉네임 수집
        newbie_mc_names = set()
        for member in newbie_role.members:
            try:
                user_info = db_manager.get_user_info(member.id)
                if user_info and user_info.get('current_minecraft_name'):
                    newbie_mc_names.add(user_info['current_minecraft_name'])
            except:
                pass

        if not newbie_mc_names:
            return

        # 아카이브된 뉴비 스레드 찾아서 다시 열기
        unarchived_count = 0
        try:
            async for thread in channel.archived_threads(limit=100):
                if not thread.name.startswith("🆕 "):
                    continue

                # 스레드 이름에서 MC 닉네임 추출
                mc_name = thread.name[2:].strip()  # "🆕 " 제거

                # 현재 뉴비인 경우에만 다시 열기
                if mc_name in newbie_mc_names:
                    try:
                        await thread.edit(archived=False)
                        unarchived_count += 1
                        logger.info(f"뉴비 스레드 다시 열림: {thread.name}")
                        await asyncio.sleep(1)  # 레이트 리밋 방지
                    except Exception as e:
                        logger.warning(f"스레드 다시 열기 실패 ({thread.name}): {e}")
        except Exception as e:
            logger.warning(f"아카이브된 스레드 검색 실패: {e}")

        if unarchived_count > 0:
            logger.info(f"[THREAD] 아카이브된 뉴비 스레드 {unarchived_count}개 다시 열림")

    except Exception as e:
        logger.error(f"뉴비 스레드 유지 루프 오류: {e}")

@newbie_thread_keeper.before_loop
async def before_newbie_thread_keeper():
    """뉴비 스레드 유지 루프 시작 전 봇 준비 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
        logger.info("뉴비 스레드 유지 루프 준비 완료")

def start_scheduler(bot):
    """스케줄러 시작 - discord.ext.tasks 사용"""
    global _bot_instance

    try:
        logger.info("백그라운드 태스크 시작")

        # 봇 인스턴스 저장
        _bot_instance = bot

        # 3개의 병렬 대기열 처리 루프 시작
        logger.info("3개의 병렬 대기열 처리 루프 시작...")
        if not queue_processor_loop_1.is_running():
            queue_processor_loop_1.start()
            logger.info("대기열 1 처리 루프 시작 (1분마다)")
        if not queue_processor_loop_2.is_running():
            queue_processor_loop_2.start()
            logger.info("대기열 2 처리 루프 시작 (1분마다)")
        if not queue_processor_loop_3.is_running():
            queue_processor_loop_3.start()
            logger.info("대기열 3 처리 루프 시작 (1분마다)")

        # 자동 역할 체크 루프 시작
        if not auto_roles_checker.is_running():
            auto_roles_checker.start()

            day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            day_name = day_names[AUTO_EXECUTION_DAY] if 0 <= AUTO_EXECUTION_DAY <= 6 else "알 수 없음"

            logger.info("자동 역할 체크 루프 시작")
            logger.info(f"자동 역할 실행 예정: 매주 {day_name} {AUTO_EXECUTION_HOUR:02d}:{AUTO_EXECUTION_MINUTE:02d}")

        # Bulk 데이터 업데이트 루프 시작
        if BULK_ENABLED and not bulk_data_updater.is_running():
            bulk_data_updater.start()
            logger.info("Bulk 데이터 업데이트 루프 시작 (5분마다)")

        # 뉴비 스레드 유지 루프 시작
        if not newbie_thread_keeper.is_running():
            newbie_thread_keeper.start()
            logger.info("뉴비 스레드 유지 루프 시작 (12시간마다)")

        # Bulk 실패 재처리 루프 시작
        if not bulk_failed_retry_loop.is_running():
            bulk_failed_retry_loop.start()
            logger.info("Bulk 실패 재처리 루프 시작 (3분마다 1명씩)")

        logger.info("백그라운드 태스크 시작 완료 (3개 병렬 대기열 활성화)")

    except Exception as e:
        logger.error(f"백그라운드 태스크 시작 실패: {e}")
        import traceback
        traceback.print_exc()

def clear_queue():
    """대기열 초기화"""
    try:
        queue_size = queue_manager.get_queue_size()
        if queue_size > 0:
            logger.info(f"대기열 초기화 중... ({queue_size}명)")
            cleared = queue_manager.clear_queue()
            logger.info(f"{cleared}명의 대기열 항목 삭제 완료")
        else:
            logger.debug("대기열이 비어있음")
    except Exception as e:
        logger.error(f"대기열 초기화 실패: {e}")

def stop_scheduler():
    """스케줄러 중지 및 대기열 초기화"""
    try:
        logger.info("백그라운드 태스크 중지")

        # 3개의 병렬 대기열 처리 루프 중지
        if queue_processor_loop_1.is_running():
            queue_processor_loop_1.cancel()
            logger.info("대기열 1 처리 루프 중지")
        if queue_processor_loop_2.is_running():
            queue_processor_loop_2.cancel()
            logger.info("대기열 2 처리 루프 중지")
        if queue_processor_loop_3.is_running():
            queue_processor_loop_3.cancel()
            logger.info("대기열 3 처리 루프 중지")

        if auto_roles_checker.is_running():
            auto_roles_checker.cancel()
            logger.info("자동 역할 체크 루프 중지")

        if BULK_ENABLED and bulk_data_updater.is_running():
            bulk_data_updater.cancel()
            logger.info("Bulk 데이터 업데이트 루프 중지")

        if newbie_thread_keeper.is_running():
            newbie_thread_keeper.cancel()
            logger.info("뉴비 스레드 유지 루프 중지")

        if bulk_failed_retry_loop.is_running():
            bulk_failed_retry_loop.cancel()
            logger.info("Bulk 실패 재처리 루프 중지")

        logger.info("백그라운드 태스크 중지 완료")

        # 대기열 초기화
        clear_queue()

    except Exception as e:
        logger.error(f"백그라운드 태스크 중지 실패: {e}")

async def process_users_bulk(bot, queue_index: int = 0):
    """
    대기열 20명 이상일 때 Bulk 데이터를 활용하여 일괄 처리
    - 1순위: 국가 역할 지급 (nation UUID 조회)
    - 2순위: 나머지 처리 (닉네임, 마을 역할, 뉴비 등)
    - UUID 없는 사용자는 대기열 뒤에 재추가
    """
    try:
        from config import config

        guild = bot.get_guild(config.GUILD_ID) if config.GUILD_ID else None
        if not guild:
            logger.info("[BULK] Discord 서버를 찾을 수 없습니다")
            return

        # 모든 대기열에서 사용자 꺼내기
        all_users = queue_manager.get_all_and_clear(queue_index)
        if not all_users:
            return

        logger.info(f"{'='*60}")
        logger.info(f"[Q{queue_index+1}] BULK 모드 처리 시작 ({len(all_users)}명)")
        logger.info(f"{'='*60}")

        # Bulk 데이터 최신화 (캐시가 오래되었으면 갱신)
        if BULK_ENABLED and bulk_data_manager:
            data_age = bulk_data_manager.get_data_age()
            if not data_age or data_age.total_seconds() > 300:  # 5분 이상 경과
                logger.info("[BULK] Bulk 데이터 갱신 중...")
                await asyncio.to_thread(bulk_data_manager.fetch_all_bulk_data, force=True)
                logger.info(f"[BULK] Bulk 데이터 갱신 완료: 주민 {len(bulk_data_manager.bulk_data)}명")
        else:
            logger.info("[BULK] Bulk 데이터 매니저가 비활성화됨 - 개별 처리로 전환")
            # bulk 불가능하면 다시 대기열에 넣고 기존 방식으로 처리
            requeue_count = 0
            for uid in all_users:
                if queue_manager.add_user(uid):
                    requeue_count += 1
            if bot_logger and requeue_count > 0:
                bot_logger.log_queue(f"Bulk 처리 불가 - {requeue_count}명 대기열 재추가", source="scheduler", action="queue_requeue", details={"reason": "bulk_fallback", "count": requeue_count})
            return

        # DB에서 UUID 조회하여 분류
        uuid_users = []   # (user_id, uuid, db_data) - UUID 있는 사용자
        no_uuid_users = []  # UUID 없는 사용자

        for user_id in all_users:
            try:
                user_data = db_manager.get_user_info(user_id) if DATABASE_ENABLED and db_manager else None
                if user_data and user_data.get('minecraft_uuid'):
                    uuid_users.append((user_id, user_data['minecraft_uuid'], user_data))
                else:
                    no_uuid_users.append(user_id)
            except Exception:
                no_uuid_users.append(user_id)

        # UUID 없는 사용자는 대기열 맨 뒤에 재추가 (나중에 개별 처리)
        requeue_count = 0
        for uid in no_uuid_users:
            if queue_manager.add_user_back(uid):
                requeue_count += 1
        if bot_logger and requeue_count > 0:
            bot_logger.log_queue(f"Bulk 처리 불가 - {requeue_count}명 대기열 재추가", source="scheduler", action="queue_requeue", details={"reason": "bulk_fallback", "count": requeue_count})

        logger.info(f"[BULK] UUID 보유: {len(uuid_users)}명, UUID 없음(후순위): {len(no_uuid_users)}명")

        if not uuid_users:
            logger.info("[BULK] UUID 보유 사용자가 없어 bulk 처리 종료")
            return

        # ===== Bulk 데이터 + 길드 멤버 사전 검증 =====
        # Bulk 데이터가 없거나 서버에 없는 사용자를 미리 분류
        bulk_ready_users = []    # bulk 처리 가능한 사용자
        not_in_guild = 0         # 서버에 없는 사용자 (탈퇴)
        no_bulk_data_users = []  # bulk 데이터에 없는 사용자 (개별 처리 필요)

        for user_id, uuid, db_data in uuid_users:
            member = guild.get_member(user_id)
            if not member:
                not_in_guild += 1
                continue  # 서버를 떠난 사용자 - 재추가 불필요

            resident_data = bulk_data_manager.get_resident_by_uuid(uuid)
            if not resident_data:
                no_bulk_data_users.append(user_id)
                continue

            bulk_ready_users.append((user_id, uuid, db_data))

        # Bulk 데이터 없는 사용자는 대기열 뒤에 재추가 (개별 API로 처리)
        requeue_count_bulk = 0
        for uid in no_bulk_data_users:
            if queue_manager.add_user_back(uid):
                requeue_count_bulk += 1
        if bot_logger and requeue_count_bulk > 0:
            bot_logger.log_queue(f"Bulk 처리 불가 - {requeue_count_bulk}명 대기열 재추가", source="scheduler", action="queue_requeue", details={"reason": "bulk_fallback", "count": requeue_count_bulk})

        if not_in_guild > 0:
            logger.warning(f"[BULK] 서버 미존재 (탈퇴): {not_in_guild}명 건너뜀")
        if no_bulk_data_users:
            logger.warning(f"[BULK] Bulk 데이터 없음 → 개별 처리로 전환: {len(no_bulk_data_users)}명")

        logger.info(f"[BULK] Bulk 처리 대상: {len(bulk_ready_users)}명")

        if not bulk_ready_users:
            logger.info("[BULK] Bulk 처리 가능한 사용자가 없어 종료")
            return

        # ===== 1순위: 국가 역할 지급 =====
        logger.info("\n  🏛️ [BULK] 1순위: 국가 역할 처리 시작")
        nation_stats = await _bulk_assign_nation_roles(bot, guild, bulk_ready_users) or {}

        # ===== 2순위: 나머지 처리 (닉네임, 뉴비 등) =====
        logger.warning("\n  📝 [BULK] 2순위: 나머지 처리 시작 (닉네임, 뉴비 등)")
        remaining_stats = await _bulk_process_remaining(bot, guild, bulk_ready_users) or {}

        # 통계 누적
        global _queue_stats, bulk_failed_users
        _queue_stats['total_queued'] += len(all_users)
        _queue_stats['bulk_processed'] += remaining_stats.get('processed', 0)
        _queue_stats['no_uuid'] += len(no_uuid_users)
        _queue_stats['no_bulk_data'] += len(no_bulk_data_users)
        _queue_stats['not_in_guild'] += not_in_guild
        _queue_stats['nation_roles_new'] += nation_stats.get('new', 0)
        _queue_stats['nation_roles_existing'] += nation_stats.get('existing', 0)
        _queue_stats['failed'] += remaining_stats.get('failed', 0) + nation_stats.get('failed', 0)
        _queue_stats['bulk_mode_used'] = True

        # 실패한 사용자를 재처리 목록에 추가 (3분마다 대기열에 추가하여 재처리)
        nation_failed = nation_stats.get('failed_user_ids', [])
        remaining_failed = remaining_stats.get('failed_user_ids', [])
        all_failed = list(set(nation_failed + remaining_failed))  # 중복 제거
        if all_failed:
            # 기존 bulk_failed_users에 없는 사용자만 추가
            existing_ids = set(bulk_failed_users)
            new_failed = [uid for uid in all_failed if uid not in existing_ids]
            bulk_failed_users.extend(new_failed)
            logger.info(f"[BULK] 실패한 {len(new_failed)}명을 재처리 목록에 추가 (3분마다 대기열로 이동)")

        logger.info(f"{'='*60}")
        logger.info(f"[Q{queue_index+1}] BULK 모드 처리 완료: {len(bulk_ready_users)}명 처리, {len(no_uuid_users)}명 UUID없음(후순위), {len(no_bulk_data_users)}명 Bulk없음(후순위), {not_in_guild}명 탈퇴")
        logger.info(f"{'='*60}")

    except Exception as e:
        logger.error(f"Bulk 모드 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        # 실패 시 사용자들을 다시 대기열에 추가
        requeue_count = 0
        for uid in all_users:
            if queue_manager.add_user(uid):
                requeue_count += 1
        if bot_logger and requeue_count > 0:
            bot_logger.log_queue(f"Bulk 처리 불가 - {requeue_count}명 대기열 재추가", source="scheduler", action="queue_requeue", details={"reason": "bulk_fallback", "count": requeue_count})


async def _bulk_assign_nation_roles(bot, guild, uuid_users: list):
    """
    Bulk 데이터를 사용하여 국가 역할을 1순위로 지급
    - bulk_data에서 nation 조회
    - nation_data에서 nation UUID 조회
    - create_nation_role_if_needed()로 역할 생성/부여
    """
    try:
        from config import config

        base_nation = config.BASE_NATION
        base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)

        if not ALLIANCE_ENABLED:
            logger.warning("[BULK] ALLIANCE_ENABLED=False - 국가 역할 자동 부여 비활성화됨")
            return

        processed = 0
        already_has = 0
        no_nation = 0
        failed = 0
        failed_user_ids = []  # 실패한 사용자 ID 추적

        for user_id, uuid, db_data in uuid_users:
            try:
                member = guild.get_member(user_id)
                if not member:
                    continue

                # 여행 중인 사용자는 역할 변경 건너뛰기
                if TRAVEL_ENABLED and is_user_traveling(user_id):
                    continue

                # Bulk 데이터에서 국가 정보 조회 (사전 검증됨)
                resident_data = bulk_data_manager.get_resident_by_uuid(uuid)
                if not resident_data:
                    continue

                nation = resident_data.get('nation') or None

                if not nation:
                    no_nation += 1
                    continue

                # nation UUID 조회 (캐시에서)
                nation_uuid = None
                nation_info = bulk_data_manager.get_nation_by_name(nation)
                if nation_info:
                    nation_uuid = nation_info.get('uuid')

                # 이전 국가 역할 제거 (nation_role_manager 사용)
                if NATION_ROLE_ENABLED and nation_role_manager:
                    all_nation_mappings = nation_role_manager.get_all_nation_roles()
                    for mapped_nation, role_data in all_nation_mappings.items():
                        if mapped_nation != nation:
                            old_role = guild.get_role(role_data['role_id'])
                            if old_role and old_role in member.roles:
                                await member.remove_roles(old_role)
                                logger.info(f"{member.name}: {mapped_nation} 국가 역할 제거")

                # 국가 역할 생성/부여
                nation_role = await create_nation_role_if_needed(guild, nation)
                if nation_role and nation_role not in member.roles:
                    await member.add_roles(nation_role)
                    logger.info(f"{member.name}: {nation} 국가 역할 부여")
                    processed += 1
                elif nation_role:
                    already_has += 1  # 이미 보유
                else:
                    logger.warning(f"{member.name}: {nation} 국가 역할 생성/조회 실패 (None 반환)")
                    failed += 1
                    failed_user_ids.append(user_id)

                # UUID를 DB에 보충 저장
                if DATABASE_ENABLED and db_manager and nation_uuid:
                    db_manager.update_user_nation_info(
                        user_id, nation=nation, nation_uuid=nation_uuid,
                        town=resident_data.get('town'),
                        town_uuid=None
                    )

                await asyncio.sleep(0.3)  # 레이트 리밋 방지

            except Exception as e:
                logger.error(f"{user_id} 국가 역할 처리 실패: {e}")
                failed += 1
                failed_user_ids.append(user_id)

        logger.info(f"[BULK] 국가 역할 처리 완료: 새로부여 {processed}건, 이미보유 {already_has}건, 무소속 {no_nation}건, 실패 {failed}건")
        return {'new': processed, 'existing': already_has, 'no_nation': no_nation, 'failed': failed, 'failed_user_ids': failed_user_ids}

    except Exception as e:
        logger.error(f"Bulk 국가 역할 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        return {'new': 0, 'existing': 0, 'no_nation': 0, 'failed': 0, 'failed_user_ids': []}


async def _bulk_process_remaining(bot, guild, uuid_users: list):
    """
    Bulk 데이터를 사용하여 나머지 처리 (닉네임, 조직원/외국인 역할, 뉴비 등)
    - base nation 소속 사용자는 개별 API로 joinedTownAt 조회
    """
    try:
        from config import config

        base_nation = config.BASE_NATION
        base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)

        try:
            from callsign_manager import callsign_manager as cs_manager
        except ImportError:
            cs_manager = None

        processed = 0
        failed = 0
        failed_user_ids = []  # 실패한 사용자 ID 추적

        async with aiohttp.ClientSession() as session:
            for user_id, uuid, db_data in uuid_users:
                try:
                    member = guild.get_member(user_id)
                    if not member:
                        continue

                    # 여행 중인 사용자는 건너뛰기
                    if TRAVEL_ENABLED and is_user_traveling(user_id):
                        continue

                    # Bulk 데이터에서 정보 조회
                    resident_data = bulk_data_manager.get_resident_by_uuid(uuid)
                    if not resident_data:
                        continue

                    mc_name = resident_data.get('name')
                    nation = resident_data.get('nation') or None
                    town = resident_data.get('town') or None
                    nation_ranks = resident_data.get('nationRanks') or None
                    town_ranks = resident_data.get('townRanks') or None

                    if not mc_name:
                        continue

                    # nation UUID 조회
                    nation_uuid = None
                    if nation:
                        nation_info = bulk_data_manager.get_nation_by_name(nation)
                        if nation_info:
                            nation_uuid = nation_info.get('uuid')

                    # town UUID 조회
                    town_uuid = None
                    if town:
                        town_info = bulk_data_manager.get_town_by_name(town)
                        if town_info:
                            town_uuid = town_info.get('uuid')

                    # base nation 소속 확인
                    if nation_uuid:
                        is_in_base_nation = (nation_uuid == base_nation_uuid)
                    else:
                        is_in_base_nation = (nation.lower() == base_nation.lower()) if (nation and base_nation) else False

                    # joinedTownAt 조회 (bulk 데이터에서 직접 가져옴)
                    joined_town_at = resident_data.get('joinedTownAt')
                    if joined_town_at == 0:
                        joined_town_at = None

                    # update_user_info() 호출 (기존 로직 활용)
                    role_changes = await update_user_info(
                        member, mc_name, nation or "❌", guild, town,
                        nation_uuid=nation_uuid, town_uuid=town_uuid, bot=bot,
                        joined_town_at=joined_town_at
                    )

                    # DB 업데이트
                    if DATABASE_ENABLED and db_manager:
                        db_manager.add_or_update_user(user_id, uuid, mc_name)
                        db_manager.add_nation_history(
                            discord_id=user_id,
                            nation_name=nation,
                            nation_uuid=nation_uuid,
                            town_name=town,
                            town_uuid=town_uuid,
                            nation_ranks=nation_ranks,
                            town_ranks=town_ranks
                        )
                        db_manager.update_user_nation_info(
                            user_id, nation=nation, nation_uuid=nation_uuid,
                            town=town, town_uuid=town_uuid
                        )

                    processed += 1

                    # 성공 로그 전송
                    last_online = resident_data.get('lastOnline')
                    days_offline = "정보 없음"
                    if last_online:
                        try:
                            last_online_dt = datetime.fromtimestamp(last_online / 1000)
                            days_diff = (datetime.now() - last_online_dt).days
                            days_offline = "오늘" if days_diff == 0 else f"{days_diff}일 전"
                        except Exception:
                            pass

                    embed = discord.Embed(
                        title="✅ 사용자 처리 완료 (Bulk)",
                        description=f"**Discord:** {member.mention}\n**MC:** {mc_name}",
                        color=0x00ff00
                    )
                    embed.add_field(name="🏛️ 국가", value=nation or "무소속", inline=True)
                    embed.add_field(name="🏘️ 마을", value=town or "없음", inline=True)
                    embed.add_field(name="🕒 마지막 접속", value=days_offline, inline=True)
                    if role_changes:
                        embed.add_field(name="🔧 변경사항", value="\n".join(role_changes[:5]), inline=False)
                    embed.timestamp = datetime.now()

                    await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)

                    await asyncio.sleep(0.5)  # 레이트 리밋 방지

                except Exception as e:
                    logger.error(f"{user_id} 나머지 처리 실패: {e}")
                    failed += 1
                    failed_user_ids.append(user_id)

        logger.warning(f"[BULK] 나머지 처리 완료: 성공 {processed}건, 실패 {failed}건")
        return {'processed': processed, 'failed': failed, 'failed_user_ids': failed_user_ids}

    except Exception as e:
        logger.error(f"Bulk 나머지 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        return {'processed': 0, 'failed': 0, 'failed_user_ids': []}


async def _fetch_joined_town_at(session, uuid: str) -> int:
    """
    개별 resident API에서 joinedTownAt 밀리초 타임스탬프를 조회

    Args:
        session: aiohttp 세션
        uuid: Minecraft UUID

    Returns:
        joinedTownAt 밀리초 타임스탬프 (없으면 None)
    """
    try:
        url = f"{MC_API_BASE}/resident?uuid={uuid}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data') and len(data['data']) > 0:
                    return data['data'][0].get('joinedTownAt')
            elif response.status == 429:
                logger.warning(f"joinedTownAt API 429 - UUID: {uuid[:8]}...")
    except Exception as e:
        logger.warning(f"joinedTownAt 조회 실패 (UUID: {uuid[:8]}...): {e}")
    return None


async def process_queue_batch(bot, queue_index: int = 0):
    """특정 대기열에서 사용자들을 배치로 처리 - 429 오류 처리 추가, 개별 API 조회 방식"""
    try:
        # 속도 제한 상태 확인
        if is_rate_limited():
            remaining_time = (rate_limit_until - datetime.now()).total_seconds()
            logger.info(f"[Q{queue_index+1}] API 속도 제한 중 - 남은 시간: {remaining_time:.0f}초")
            return

        # 해당 대기열이 이미 처리 중인지 확인
        if queue_manager.is_processing(queue_index):
            return

        # 처리 전 해당 대기열 크기 확인
        queue_size_before = queue_manager.get_queue_size(queue_index)

        if queue_size_before == 0:
            return

        # === 개별 API 조회 처리 ===
        logger.info(f"[Q{queue_index+1}] 대기열 배치 처리 시작 (대기: {queue_size_before}명)")
        queue_manager.set_processing(queue_index, True)

        # 배치 크기 (한 번에 처리할 사용자 수)
        batch_size = 10
        processed_users = []

        for _ in range(batch_size):
            user_id = queue_manager.get_next(queue_index)
            if user_id is None:
                break
            processed_users.append(user_id)

        if not processed_users:
            queue_manager.set_processing(queue_index, False)
            return

        logger.info(f"[Q{queue_index+1}] 배치 처리 대상: {len(processed_users)}명")

        # DB 연동 여부로 유저 분리
        db_users = []  # DB에 UUID가 있는 유저 (Discord ID API 스킵)
        new_users = []  # DB에 UUID가 없는 유저 (Discord ID API 호출 필요)

        for user_id in processed_users:
            try:
                user_data = db_manager.get_user_info(user_id)
                if user_data and user_data.get('minecraft_uuid'):
                    db_users.append(user_id)
                else:
                    new_users.append(user_id)
            except:
                new_users.append(user_id)  # 확인 실패하면 신규로 간주

        logger.info(f"[Q{queue_index+1}] 분류: DB UUID 보유 {len(db_users)}명, UUID 없음 {len(new_users)}명")

        # API 세션 생성
        async with aiohttp.ClientSession() as session:
            # 1. DB에 UUID가 있는 유저 먼저 처리 (Discord ID API 스킵)
            for idx, user_id in enumerate(db_users, 1):
                try:
                    if is_rate_limited():
                        logger.info(f"[Q{queue_index+1}] 속도 제한 감지 - 나머지 사용자 대기열에 재추가")
                        queue_manager.add_user(user_id)
                        remaining_ids = db_users[idx:] + new_users
                        # 나머지 모두 다시 추가
                        for remaining_id in remaining_ids:
                            queue_manager.add_user(remaining_id)
                        if bot_logger:
                            bot_logger.log_queue(f"속도 제한 - {len(remaining_ids) + 1}명 대기열 재추가", source="scheduler", action="queue_requeue", details={"reason": "rate_limit", "count": len(remaining_ids) + 1})
                        break

                    logger.info(f"[Q{queue_index+1}] [{idx}/{len(db_users)}] DB UUID 보유 유저 처리: {user_id}")
                    await process_single_user(bot, session, user_id)
                    await asyncio.sleep(5)  # UUID로만 게임 정보 API 호출
                except Exception as e:
                    logger.error(f"[Q{queue_index+1}] DB UUID 보유 유저 {user_id} 처리 실패: {e}")

            # 2. UUID 없는 유저 처리 (Discord ID API + 게임 정보 API)
            for idx, user_id in enumerate(new_users, 1):
                try:
                    if is_rate_limited():
                        logger.info(f"[Q{queue_index+1}] 속도 제한 감지 - 나머지 신규 유저 대기열에 재추가")
                        # 나머지 신규 유저 다시 추가
                        remaining_ids = new_users[idx-1:]
                        for remaining_id in remaining_ids:
                            queue_manager.add_user(remaining_id)
                        if bot_logger:
                            bot_logger.log_queue(f"속도 제한 - {len(remaining_ids)}명 대기열 재추가", source="scheduler", action="queue_requeue", details={"reason": "rate_limit", "count": len(remaining_ids)})
                        break

                    logger.info(f"[Q{queue_index+1}] [{idx}/{len(new_users)}] UUID 없는 유저 처리: {user_id}")
                    await process_single_user(bot, session, user_id)
                    await asyncio.sleep(10)  # Discord ID API + 게임 정보 API 호출
                except Exception as e:
                    logger.error(f"[Q{queue_index+1}] UUID 없는 유저 {user_id} 처리 실패: {e}")

        logger.info(f"[Q{queue_index+1}] 배치 처리 완료: DB UUID 보유 {len(db_users)}명, UUID 없음 {len(new_users)}명")

        # 개별 처리 통계 누적
        global _queue_stats
        _queue_stats['total_queued'] += len(processed_users)
        _queue_stats['individual_processed'] += len(processed_users)

        # 처리 후 대기열이 비었는지 확인하고 완료 메시지 전송
        queue_size_after = queue_manager.get_queue_size()

        if queue_size_after == 0 and queue_size_before > 0:
            await _send_queue_complete_message(bot, queue_size_before)

    except Exception as e:
        logger.error(f"[Q{queue_index+1}] 배치 처리 오류: {e}")
    finally:
        queue_manager.set_processing(queue_index, False)


async def _send_queue_complete_message(bot, queue_size_before: int):
    """대기열 처리 완료 메시지 전송 (총합 통계 포함)"""
    global _queue_stats, _is_auto_execution
    logger.info("모든 대기열 처리 완료!")

    # CSV 보고서 저장
    csv_filepath = save_csv_report()

    # 자동 실행 플래그 해제
    if _is_auto_execution:
        _is_auto_execution = False
        logger.info("CSV 데이터 수집 비활성화됨 (대기열 처리 완료)")

    stats = _queue_stats

    embed = discord.Embed(
        title="✅ 자동 실행 완료",
        description="모든 대기열 처리가 완료되었습니다.",
        color=0x00ff00
    )

    # 총합 처리 결과
    total_processed = stats['bulk_processed'] + stats['individual_processed']
    mode_text = "Bulk + 개별" if stats['bulk_mode_used'] and stats['individual_processed'] > 0 else ("Bulk" if stats['bulk_mode_used'] else "개별")

    summary_lines = [
        f"**총 대기열:** {stats['total_queued']}명",
        f"**처리 완료:** {total_processed}명 ({mode_text} 모드)",
    ]
    if stats['bulk_processed'] > 0:
        summary_lines.append(f"  - Bulk 처리: {stats['bulk_processed']}명")
    if stats['individual_processed'] > 0:
        summary_lines.append(f"  - 개별 처리: {stats['individual_processed']}명")
    if stats['failed'] > 0:
        summary_lines.append(f"**실패:** {stats['failed']}건")
    embed.add_field(
        name="📊 처리 결과",
        value="\n".join(summary_lines),
        inline=False
    )

    # 국가 역할 통계 (Bulk 모드에서만)
    if stats['bulk_mode_used'] and (stats['nation_roles_new'] > 0 or stats['nation_roles_existing'] > 0):
        nation_lines = [
            f"**새로 부여:** {stats['nation_roles_new']}건",
            f"**이미 보유:** {stats['nation_roles_existing']}건",
        ]
        embed.add_field(
            name="🏛️ 국가 역할",
            value="\n".join(nation_lines),
            inline=True
        )

    # 건너뛴 사용자 통계
    skipped_lines = []
    if stats['no_uuid'] > 0:
        skipped_lines.append(f"UUID 없음 (후순위): {stats['no_uuid']}명")
    if stats['no_bulk_data'] > 0:
        skipped_lines.append(f"Bulk 데이터 없음 (후순위): {stats['no_bulk_data']}명")
    if stats['not_in_guild'] > 0:
        skipped_lines.append(f"서버 탈퇴: {stats['not_in_guild']}명")
    if skipped_lines:
        embed.add_field(
            name="⚠️ 건너뜀",
            value="\n".join(skipped_lines),
            inline=True
        )

    if csv_filepath:
        csv_filename = os.path.basename(csv_filepath)
        embed.add_field(
            name="📄 CSV 보고서",
            value=f"파일명: `{csv_filename}`",
            inline=False
        )
    embed.timestamp = datetime.now()

    # 통계 초기화
    _reset_queue_stats()

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
        logger.warning(f"성공 채널 전송 실패: {e}")

    if FAILURE_CHANNEL_ID != SUCCESS_CHANNEL_ID:
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
            logger.warning(f"실패 채널 전송 실패: {e}")


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
        logger.info(f"사용자 처리 시작: {user_id}")

        # 예외 사용자 확인 (최우선 체크)
        if exception_manager and exception_manager.is_exception(user_id):
            logger.info(f"예외 사용자 건너뜀: {user_id}")
            return {'success': False, 'error': '예외 사용자'}

        # 모든 길드에서 해당 사용자 찾기
        for g in bot.guilds:
            m = g.get_member(user_id)
            if m:
                member = m
                guild = g
                break

        if not member or not guild:
            error_message = "서버에서 사용자를 찾을 수 없습니다."
            logger.warning(f"{error_message}: {user_id}")

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
            return {'success': False, 'error': error_message}

        # 항상 Discord ID API로 최신 연동 계정 확인 (마크 계정 변경 대응)
        # DB 캐시는 API 실패 시 폴백으로만 사용
        cached_uuid = None
        cached_mc_name = None
        if DATABASE_ENABLED and db_manager:
            try:
                user_data = db_manager.get_user_info(user_id)
                if user_data:
                    cached_uuid = user_data.get('minecraft_uuid')
                    cached_mc_name = user_data.get('current_minecraft_name')
            except Exception as db_error:
                logger.warning(f"데이터베이스 조회 실패: {db_error}")

        # Discord ID로 UUID 조회 (항상 최신 계정 확인)
        api_success = False
        logger.info("API를 통해 UUID 조회 중...")
        # 1단계: 디스코드 ID → UUID, MC Name
        url1 = f"{MC_API_BASE}/discord?discord={user_id}"

        try:
            async with session.get(url1, timeout=aiohttp.ClientTimeout(total=10)) as r1:
                if r1.status == 429:
                    # 429 오류 처리
                    logger.error(f"🚨 API 속도 제한 감지 (1단계) - 사용자 {user_id} 재대기열 추가")
                    handle_rate_limit()
                    await send_rate_limit_notification(bot)

                    # 재시도 횟수 확인
                    retry_count = increment_retry_count(user_id)
                    if should_retry(user_id):
                        queue_manager.add_user(user_id)  # 재대기열에 추가
                        if bot_logger:
                            bot_logger.log_queue("API 429 재시도 대기열 추가", target_user_id=user_id, source="scheduler", action="queue_requeue", details={"reason": "api_429_retry"})
                        logger.info(f"재시도 {retry_count}/{MAX_RETRY_COUNT}: {member.display_name}")
                    else:
                        clear_retry_count(user_id)
                        logger.error(f"최대 재시도 횟수 초과: {member.display_name}")

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
                    raise Exception(f"API 호출 실패 (HTTP {r1.status})")

                data1 = await r1.json()
                if not data1.get('data') or not data1['data']:
                    raise Exception("마인크래프트 계정이 연동되지 않았습니다")

                # 여러 마크 계정이 연동된 경우, lastOnline 기준 최신 계정 선택
                linked_accounts = data1['data']
                if len(linked_accounts) > 1:
                    logger.info(f"연동된 마크 계정 {len(linked_accounts)}개 발견 - lastOnline 기준 최신 계정 선택")
                    # bulk API로 모든 UUID의 lastOnline 조회
                    uuids_to_check = [acc.get('uuid') for acc in linked_accounts if acc.get('uuid')]
                    bulk_url = f"{MC_API_BASE}/resident/bulk"
                    try:
                        async with session.post(bulk_url, json=uuids_to_check, timeout=aiohttp.ClientTimeout(total=15)) as bulk_r:
                            if bulk_r.status == 200:
                                bulk_data = await bulk_r.json()
                                if bulk_data.get('data'):
                                    # lastOnline 기준으로 정렬하여 최신 계정 찾기
                                    sorted_accounts = sorted(
                                        bulk_data['data'],
                                        key=lambda x: x.get('lastOnline', 0),
                                        reverse=True
                                    )
                                    latest_account = sorted_accounts[0]
                                    uuid = latest_account.get('uuid')
                                    mc_id = latest_account.get('name')
                                    last_online_ts = latest_account.get('lastOnline', 0)
                                    last_online_days = (datetime.now().timestamp() * 1000 - last_online_ts) / (1000 * 60 * 60 * 24) if last_online_ts else 0
                                    logger.info(f"최신 계정 선택: {mc_id} (마지막 접속: {int(last_online_days)}일 전)")
                                    for acc in sorted_accounts[1:]:
                                        old_ts = acc.get('lastOnline', 0)
                                        old_days = (datetime.now().timestamp() * 1000 - old_ts) / (1000 * 60 * 60 * 24) if old_ts else 0
                                        logger.info(f"↳ 이전 계정: {acc.get('name')} (마지막 접속: {int(old_days)}일 전)")
                                    api_success = True
                                else:
                                    # bulk 실패 시 첫 번째 계정 사용
                                    uuid = linked_accounts[0].get('uuid')
                                    mc_id = linked_accounts[0].get('name')
                                    api_success = True
                            else:
                                uuid = linked_accounts[0].get('uuid')
                                mc_id = linked_accounts[0].get('name')
                                api_success = True
                    except Exception as bulk_err:
                        logger.warning(f"Bulk API 조회 실패, 첫 번째 계정 사용: {bulk_err}")
                        uuid = linked_accounts[0].get('uuid')
                        mc_id = linked_accounts[0].get('name')
                        api_success = True
                else:
                    uuid = linked_accounts[0].get('uuid')
                    mc_id = linked_accounts[0].get('name')
                    api_success = True

                if not uuid or not mc_id:
                    raise Exception("마인크래프트 계정 정보가 불완전합니다")

                logger.info(f"마크 정보: {mc_id} (UUID: {uuid[:8]}...)")

                # DB에 UUID와 마크 닉네임 저장 (캐시 갱신)
                if DATABASE_ENABLED and db_manager:
                    try:
                        # 캐시와 다른 경우에만 저장 (마크 계정 변경 감지)
                        if cached_uuid != uuid or cached_mc_name != mc_id:
                            if cached_mc_name and cached_mc_name != mc_id:
                                logger.info(f"마크 계정 변경 감지: {cached_mc_name} → {mc_id}")
                            db_manager.add_or_update_user(
                                discord_id=user_id,
                                minecraft_uuid=uuid,
                                minecraft_name=mc_id
                            )
                            logger.info(f"UUID와 마크 닉네임 DB에 저장: {mc_id} (UUID: {uuid[:8]}...)")
                    except Exception as save_error:
                        logger.warning(f"UUID 저장 실패: {save_error}")

                await asyncio.sleep(5)  # API 제한을 위한 대기 (비블로킹)

        except Exception as api_error:
            # API 실패 시 캐시된 UUID 사용 (폴백)
            if cached_uuid and cached_mc_name:
                logger.warning(f"API 실패, 캐시된 UUID 사용: {cached_mc_name} (UUID: {cached_uuid[:8]}...)")
                uuid = cached_uuid
                mc_id = cached_mc_name
            else:
                # 캐시도 없으면 에러
                error_message = f"마인크래프트 계정 연동 정보를 찾을 수 없습니다"
                logger.error(f"1단계 실패: {api_error}")
                raise Exception(error_message)

        # 2단계: UUID → 게임 정보 (항상 개별 API 호출, 실패 시 DB 폴백)
        logger.info("UUID로 게임 정보 조회 중...")
        game_info = None
        url2 = f"{MC_API_BASE}/resident?uuid={uuid}"

        try:
            async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                if r2.status == 429:
                    # 429 오류 처리
                    logger.error(f"🚨 API 속도 제한 감지 (2단계) - 사용자 {user_id} 재대기열 추가")
                    handle_rate_limit()
                    await send_rate_limit_notification(bot)

                    # 재시도 횟수 확인
                    retry_count = increment_retry_count(user_id)
                    if should_retry(user_id):
                        queue_manager.add_user(user_id)  # 재대기열에 추가
                        if bot_logger:
                            bot_logger.log_queue("API 429 재시도 대기열 추가", target_user_id=user_id, source="scheduler", action="queue_requeue", details={"reason": "api_429_retry"})
                        logger.info(f"재시도 {retry_count}/{MAX_RETRY_COUNT}: {member.display_name}")
                    else:
                        clear_retry_count(user_id)
                        logger.error(f"최대 재시도 횟수 초과: {member.display_name}")
                    return
                elif r2.status != 200:
                    raise Exception(f"게임 정보를 조회할 수 없습니다 (HTTP {r2.status})")

                data2 = await r2.json()
                if not data2.get('data') or not data2['data']:
                    raise Exception("게임 내 정보가 없습니다")

                game_info = data2['data'][0]

        except Exception as stage2_err:
            # DB 폴백: all_players 테이블에서 게임 정보 조회
            if DATABASE_ENABLED and db_manager:
                try:
                    db_player = db_manager.get_player_by_uuid(uuid)
                    if not db_player and mc_id:
                        db_player = db_manager.get_player_by_name(mc_id)
                    if db_player:
                        # DB 컬럼명 → API 필드명 정규화
                        db_player["nationUuid"] = db_player.get("nation_uuid")
                        db_player["townUuid"] = db_player.get("town_uuid")
                        db_player["nationRanks"] = db_player.get("nation_ranks", "")
                        db_player["townRanks"] = db_player.get("town_ranks", "")
                        game_info = db_player
                        logger.debug(f"2단계 API 실패, DB 캐시로 처리: {mc_id} (원인: {stage2_err})")
                except Exception as db_err:
                    logger.warning(f"DB 폴백 실패: {db_err}")

            if not game_info:
                raise stage2_err

        # 모든 게임 정보 추출 (Bulk 또는 API 데이터에서)
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
        joined_town_at_ts = game_info.get('joinedTownAt')  # 밀리초 타임스탬프

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

                logger.info(f"게임 정보: {nation}/{town}, 마지막 접속: {days_offline}")

            except Exception as e:
                logger.warning(f"마지막 온라인 시간 처리 오류: {e}")
                last_online_formatted = "알 수 없음"
                days_offline = "알 수 없음"
        else:
            last_online_formatted = "정보 없음"
            days_offline = "정보 없음"
            logger.info(f"게임 정보: {nation}/{town}, 마지막 접속: 정보 없음")
        
        # 성공 시 재시도 횟수 초기화
        clear_retry_count(user_id)
        
        # 역할 부여 및 닉네임 변경 (마을 정보 및 UUID 포함, joinedTownAt 전달)
        role_changes = await update_user_info(
            member, mc_id, nation, guild, town,
            nation_uuid=nation_uuid, town_uuid=town_uuid, bot=bot,
            joined_town_at=joined_town_at_ts
        )

        # 데이터베이스에 사용자 정보 저장 (UUID, Minecraft 닉네임 히스토리)
        if DATABASE_ENABLED and db_manager:
            try:
                db_manager.add_or_update_user(
                    discord_id=user_id,
                    minecraft_uuid=uuid,
                    minecraft_name=mc_id
                )
                logger.info(f"데이터베이스 저장 완료: {mc_id} (UUID: {uuid[:8]}...)")

                # 국가 히스토리 저장
                db_manager.add_nation_history(
                    discord_id=user_id,
                    nation_name=nation if nation and nation not in ["❌", "무소속"] else None,
                    nation_uuid=nation_uuid if nation_uuid else None,
                    town_name=town if town and town not in ["❌", "무소속"] else None,
                    town_uuid=town_uuid if town_uuid else None,
                    nation_ranks=nation_ranks if nation_ranks else None,
                    town_ranks=town_ranks if town_ranks else None
                )
                logger.info(f"국가 히스토리 저장 완료: {nation}/{town} (국가 계급: {nation_ranks}, 마을 계급: {town_ranks})")

            except Exception as e:
                logger.warning(f"데이터베이스 저장 실패: {e}")

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
            logger.warning(f"CSV 데이터 수집 실패: {e}")

        logger.info(f"사용자 처리 완료: {member.display_name} ({nation}, {town})")

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
            return {
                'success': True,
                'nation': nation,
                'town': town,
                'mc_id': mc_id,
                'role_changes': role_changes,
                'incomplete': True  # 국가/마을 정보 불완전 플래그
            }

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
            value=f"**Discord:** {member.mention}\n**닉네임:** ``{member.display_name}``",
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
            role_id = town_role_manager.get_role_id_by_name(town)
            if role_id:
                town_role = guild.get_role(role_id)
                if town_role:
                    embed.add_field(
                        name="🏘️ 마을 역할",
                        value=f"**{town}** → {town_role.mention}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🏘️ 마을 역할",
                        value=f"**{town}** → ⚠️ 역할 없음 (ID: {role_id})",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="🏘️ 마을 역할",
                    value=f"**{town}** → ℹ️ 역할 연동 안됨",
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

        # 성공 결과 반환
        return {
            'success': True,
            'nation': nation,
            'town': town,
            'mc_id': mc_id,
            'role_changes': role_changes
        }

    except Exception as e:
        logger.error(f"사용자 {user_id} 처리 중 오류: {e}")

        # 429 오류가 아닌 일반 오류의 경우 재시도 횟수 초기화
        clear_retry_count(user_id)

        # 마인크래프트 계정이 연동되지 않은 경우 모든 역할 제거 및 닉네임 초기화
        role_removal_changes = []
        if "마인크래프트 계정이 연동되지 않았습니다" in str(e) or "마인크래프트 계정 연동 정보를 찾을 수 없습니다" in str(e):
            logger.info("마크 계정 미연동 - 모든 관련 역할 제거 및 닉네임 초기화 시작")

            if member and guild:
                # 0. 닉네임 설정 (역할 양식이 있으면 적용, 없으면 초기화)
                try:
                    original_nick = member.nick if member.nick else member.name

                    # 역할 양식 확인
                    role_format = None
                    applied_format_name = None
                    if CALLSIGN_ENABLED and callsign_manager:
                        try:
                            # 역할 우선순위 순으로 정렬
                            sorted_roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
                            for role in sorted_roles:
                                format_str = callsign_manager.get_role_format(role.id)
                                if format_str:
                                    role_format = format_str
                                    applied_format_name = role.name
                                    logger.info(f"마크 미연동 사용자에게 역할 양식 적용: {role.name} - {format_str}")
                                    break
                        except Exception as role_err:
                            logger.warning(f"역할 양식 확인 실패: {role_err}")

                    if role_format:
                        # 역할 양식이 있으면 양식 적용 (MC 정보는 ❌[ MC ] ❌로 표시)
                        user_callsign = None

                        # 콜사인 조회
                        try:
                            user_callsign = callsign_manager.get_callsign(member.id)
                            if user_callsign:
                                logger.info(f"콜사인 조회됨: {user_callsign}")
                        except:
                            pass

                        new_nickname = callsign_manager.apply_format_to_nickname(
                            role_format,
                            mc_id="❌[ MC ] ❌",
                            nation=None,
                            town=None,
                            callsign=user_callsign,
                            discord_joined_at=member.joined_at
                        )

                        if member.nick != new_nickname:
                            await member.edit(nick=new_nickname)
                            role_removal_changes.append(f"• 닉네임 변경됨: `{original_nick}` → `{new_nickname}` (🎭 {applied_format_name} 역할 양식)")
                            logger.info(f"역할 양식으로 닉네임 설정: {original_nick} → {new_nickname}")
                        else:
                            logger.debug(f"닉네임 유지: {new_nickname}")
                    else:
                        # 역할 양식이 없으면 닉네임 변경하지 않음
                        logger.debug("역할 양식 없음 - 닉네임 변경 건너뜀")

                except discord.Forbidden:
                    role_removal_changes.append(f"• ⚠️ 닉네임 변경 권한 없음")
                    logger.warning("닉네임 변경 권한 없음")
                except Exception as nick_error:
                    role_removal_changes.append(f"• ⚠️ 닉네임 변경 실패: {str(nick_error)[:50]}")
                    logger.warning(f"닉네임 변경 실패: {nick_error}")

                # 1. 국민 역할 제거
                if SUCCESS_ROLE_ID != 0:
                    success_role = guild.get_role(SUCCESS_ROLE_ID)
                    if success_role and success_role in member.roles:
                        try:
                            await member.remove_roles(success_role)
                            role_removal_changes.append(f"• **{success_role.name}** 역할 제거됨")
                            logger.info(f"국민 역할 제거: {success_role.name}")
                        except Exception as role_error:
                            logger.warning(f"국민 역할 제거 실패: {role_error}")

                # 2. 외국인 역할 제거
                if SUCCESS_ROLE_ID_OUT != 0:
                    out_role = guild.get_role(SUCCESS_ROLE_ID_OUT)
                    if out_role and out_role in member.roles:
                        try:
                            await member.remove_roles(out_role)
                            role_removal_changes.append(f"• **{out_role.name}** 역할 제거됨")
                            logger.info(f"외국인 역할 제거: {out_role.name}")
                        except Exception as role_error:
                            logger.warning(f"외국인 역할 제거 실패: {role_error}")

                # 3. 모든 마을 역할 제거
                if TOWN_ROLE_ENABLED and town_role_manager:
                    try:
                        all_mapped_towns = town_role_manager.get_all_mappings()
                        for mapped_town, mapped_role_id in all_mapped_towns.items():
                            mapped_role = guild.get_role(mapped_role_id)
                            if mapped_role and mapped_role in member.roles:
                                await member.remove_roles(mapped_role)
                                role_removal_changes.append(f"• **{mapped_town}** 마을 역할 제거됨")
                                logger.info(f"마을 역할 제거: {mapped_town}")
                    except Exception as role_error:
                        logger.warning(f"마을 역할 제거 실패: {role_error}")

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
                                    logger.info(f"국가 역할 제거: {nation_name}")
                    except Exception as role_error:
                        logger.warning(f"국가 역할 제거 실패: {role_error}")

                if role_removal_changes:
                    logger.info(f"총 {len(role_removal_changes)}개 역할 제거 완료")

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
                    role_id = town_role_manager.get_role_id_by_name(town)
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
        logger.error(f"사용자 {user_id} 처리 중 오류: {e}")
        
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
                    role_id = town_role_manager.get_role_id_by_name(town)
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

        # 실패 결과 반환
        return {
            'success': False,
            'error': str(e)
        }

async def execute_auto_roles(bot):
    """자동 역할 실행 함수 - 새로운 자동역할 관리자 사용 (비블로킹)"""
    global _is_auto_execution

    try:
        logger.info("자동 역할 실행 시작")

        # ===== Bulk 데이터 먼저 업데이트 =====
        try:
            from bulk_updater import bulk_data_manager

            logger.info("자동 실행 전 Bulk 데이터 강제 업데이트 시작...")

            # 비동기로 bulk 데이터 가져오기
            update_success = await asyncio.to_thread(bulk_data_manager.fetch_bulk_data)

            if not update_success:
                logger.warning("Bulk 데이터 업데이트 실패 - 기존 캐시 데이터 사용")

                # 캐시 데이터가 있는지 확인
                if bulk_data_manager.is_data_available():
                    data_age = bulk_data_manager.get_data_age()
                    logger.info(f"📦 기존 캐시 사용 (데이터 경과 시간: {data_age})")
                else:
                    logger.warning("캐시 데이터도 없음 - 개별 API 호출로 진행")

        except Exception as e:
            logger.warning(f"Bulk 데이터 업데이트 오류: {e} - 개별 API 호출로 진행")

        # 자동 실행 플래그 설정 (CSV 수집 활성화) + 통계 초기화
        _is_auto_execution = True
        _reset_queue_stats()
        logger.info("CSV 데이터 수집 활성화됨 (스케줄러 자동 실행)")

        # 자동역할 관리자에서 역할 목록 가져오기
        role_ids = auto_role_manager.get_roles()

        if not role_ids:
            logger.warning("자동처리로 설정된 역할이 없습니다.")

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
            logger.info(f"길드 처리: {guild.name}")

            for role_id in role_ids:
                try:
                    role = guild.get_role(role_id)

                    if not role:
                        logger.warning(f"역할을 찾을 수 없음: {role_id}")
                        if role_id not in invalid_roles:
                            invalid_roles.append(role_id)
                        continue

                    logger.info(f"역할 '{role.name}' 멤버 {len(role.members)}명 처리 중")

                    role_added_count = 0
                    for idx, member in enumerate(role.members):
                        # 예외 목록 확인
                        if exception_manager.is_exception(member.id):
                            logger.info(f"예외 대상 건너뜀: {member.display_name}")
                            continue

                        # 대기열에 추가
                        if queue_manager.add_user(member.id):
                            added_count += 1
                            role_added_count += 1
                            logger.info(f"대기열 추가: {member.display_name}")
                            if bot_logger:
                                bot_logger.log_queue("자동역할 대기열 추가", target_user_id=member.id, source="scheduler", action="queue_add", details={"trigger": "auto_role"})
                        else:
                            logger.info(f"이미 대기열에 있음: {member.display_name}")

                        # 50명마다 비동기 제어권 양보 (블로킹 방지)
                        if (idx + 1) % 50 == 0:
                            await asyncio.sleep(0)
                            logger.info(f"처리 진행 중... ({idx + 1}/{len(role.members)})")

                    # 처리된 역할 정보 저장
                    processed_roles.append({
                        'role': role,
                        'total_members': len(role.members),
                        'added_members': role_added_count
                    })

                except Exception as e:
                    logger.warning(f"역할 처리 오류 ({role_id}): {e}")
                    if role_id not in invalid_roles:
                        invalid_roles.append(role_id)
                    continue

                # 역할 사이마다 비동기 제어권 양보
                await asyncio.sleep(0)
        
        logger.info(f"자동 역할 실행 완료 - {added_count}명 대기열 추가")
        
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
            # 개선된 시간 표시 사용 (20초/명으로 계산)
            time_str = format_estimated_time(current_queue_size, 20)
            embed.add_field(
                name="⏰ 예상 완료 시간",
                value=time_str,
                inline=False
            )
        
        # 429 오류 상태 정보 추가
        if rate_limit_detected:
            rate_limit_unix = int(rate_limit_until.timestamp())
            embed.add_field(
                name="⚠️ API 상태",
                value=f"API 속도 제한이 감지되었습니다.\n해제 예정: <t:{rate_limit_unix}:F> (<t:{rate_limit_unix}:R>)",
                inline=False
            )
        
        embed.timestamp = datetime.now()

        await send_log_message(bot, SUCCESS_CHANNEL_ID, embed)
        # 성공/실패 채널이 다른 경우에만 실패 채널에도 전송
        if FAILURE_CHANNEL_ID != SUCCESS_CHANNEL_ID:
            await send_log_message(bot, FAILURE_CHANNEL_ID, embed)

    except Exception as e:
        logger.error(f"자동 역할 실행 오류: {e}")

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

    # finally 블록 제거: 플래그 해제는 대기열 처리 완료 시에만 수행 (process_queue_batch에서 처리)