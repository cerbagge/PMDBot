import discord
from discord.ext import commands
import asyncio
import sys
import os

from log_manager import get_logger
logger = get_logger("main")

# 설정 로드
try:
    from config import config
except ImportError:
    logger.error("config.py 파일을 찾을 수 없습니다. config.py 파일을 생성해주세요.")
    sys.exit(1)

# 예외 관리자 로드
try:
    from exception_manager import exception_manager
    logger.info("exception_manager 모듈 로드됨")
except ImportError:
    logger.warning("exception_manager.py 파일을 찾을 수 없습니다. 예외 관리 기능이 비활성화됩니다.")
    exception_manager = None

# scheduler 모듈 로드 (자동 처리에 필요)
try:
    from scheduler import is_exception_user
    logger.info("scheduler 모듈에서 예외 사용자 확인 함수 로드됨")
except ImportError:
    logger.warning("scheduler.py에서 is_exception_user 함수를 로드할 수 없습니다.")
    is_exception_user = None

# callsign_manager 모듈 로드
try:
    from callsign_manager import callsign_manager
    logger.info("callsign_manager 모듈 로드됨")
    CALLSIGN_ENABLED = True
except ImportError:
    logger.warning("callsign_manager.py 파일을 찾을 수 없습니다. 콜사인 기능이 비활성화됩니다.")
    callsign_manager = None
    CALLSIGN_ENABLED = False

# 로그 매니저 로드
try:
    from log_manager import bot_logger, LogCategory
except ImportError:
    bot_logger = None

# Intents 설정
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def setup_hook():
    """봇 연결 전에 영구 View 등록 (버튼 상호작용 복구용)"""
    try:
        from commands.admin.return_system.ticket_handler import ReturnTicketView, CloseTicketView
        bot.add_view(ReturnTicketView())
        bot.add_view(CloseTicketView())
        logger.info("ReturnTicketView / CloseTicketView setup_hook 등록 완료")
    except Exception as e:
        logger.warning(f"복귀 View setup_hook 등록 실패: {e}")


async def clear_and_sync_commands():
    """모든 기존 명령어를 완전히 삭제하고 새로운 명령어를 등록하는 함수"""
    try:
        logger.info("모든 슬래시 명령어 완전 삭제 및 재등록 시작...")

        # Step 1: 전역 명령어 완전 삭제
        logger.info("전역 명령어 완전 삭제 중...")
        try:
            existing_global_commands = await asyncio.wait_for(
                bot.tree.fetch_commands(),
                timeout=60.0
            )
            logger.info(f"기존 전역 명령어 {len(existing_global_commands)}개 발견")

            # 전역 명령어 삭제
            bot.tree.clear_commands(guild=None)
            await asyncio.wait_for(bot.tree.sync(), timeout=60.0)
            logger.info(f"{len(existing_global_commands)}개 전역 명령어 삭제 완료")

            # 전역 명령어 삭제 반영 대기 (짧게)
            if existing_global_commands:
                logger.info("전역 명령어 삭제 반영 대기 중... (3초)")
                await asyncio.sleep(3)
        except asyncio.TimeoutError:
            logger.warning("전역 명령어 삭제 타임아웃 - 계속 진행")
        except Exception as e:
            logger.warning(f"전역 명령어 삭제 오류: {e}")

        # Step 2: 길드 명령어 완전 삭제 (설정된 경우)
        if config.GUILD_ID:
            logger.info(f"길드 {config.GUILD_ID} 명령어 완전 삭제 중...")
            try:
                guild = discord.Object(id=config.GUILD_ID)
                existing_guild_commands = await asyncio.wait_for(
                    bot.tree.fetch_commands(guild=guild),
                    timeout=60.0
                )
                logger.info(f"기존 길드 명령어 {len(existing_guild_commands)}개 발견")

                # 길드 명령어 삭제
                bot.tree.clear_commands(guild=guild)
                await asyncio.wait_for(bot.tree.sync(guild=guild), timeout=60.0)
                logger.info(f"{len(existing_guild_commands)}개 길드 명령어 삭제 완료")

                # 길드 명령어 삭제 반영 대기 (짧게)
                if existing_guild_commands:
                    logger.info("길드 명령어 삭제 반영 대기 중... (2초)")
                    await asyncio.sleep(2)
            except asyncio.TimeoutError:
                logger.warning("길드 명령어 삭제 타임아웃 - 계속 진행")
            except Exception as e:
                logger.warning(f"길드 명령어 삭제 오류: {e}")

        # Step 3: 짧은 대기
        logger.info("명령어 삭제 반영 대기 중... (2초)")
        await asyncio.sleep(2)

        logger.info("명령어 삭제 작업 완료!")
        return True

    except discord.Forbidden:
        logger.error("명령어 관리 권한이 없습니다!")
        logger.info("봇에 다음 권한이 있는지 확인하세요:")
        logger.info("   - applications.commands (슬래시 명령어)")
        logger.info("   - Use Slash Commands")
        return False
    except discord.HTTPException as e:
        logger.error(f"Discord API 오류: {e}")
        if e.status == 429:
            logger.info("Rate limit에 걸렸습니다. 잠시 후 다시 시도해주세요.")
        return False
    except Exception as e:
        logger.error(f"명령어 삭제 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

# 명령어 동기화 대기 플래그 파일
SYNC_PENDING_FILE = "data/sync_pending.json"

def save_sync_pending(retry_after: int = 86400):
    """Rate Limit 발생 시 다음 재시도 시간 저장"""
    import json
    from datetime import datetime, timedelta

    os.makedirs("data", exist_ok=True)
    retry_time = datetime.now() + timedelta(seconds=retry_after)

    data = {
        "pending": True,
        "retry_after": retry_time.isoformat(),
        "created_at": datetime.now().isoformat()
    }

    with open(SYNC_PENDING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    logger.info(f"명령어 동기화 예약됨: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")


def clear_sync_pending():
    """동기화 대기 플래그 제거"""
    if os.path.exists(SYNC_PENDING_FILE):
        os.remove(SYNC_PENDING_FILE)
        logger.info("명령어 동기화 대기 플래그 제거됨")


def get_sync_pending():
    """동기화 대기 상태 확인"""
    import json
    from datetime import datetime

    if not os.path.exists(SYNC_PENDING_FILE):
        return None

    try:
        with open(SYNC_PENDING_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if data.get("pending"):
            retry_time = datetime.fromisoformat(data["retry_after"])
            if datetime.now() >= retry_time:
                return "ready"  # 재시도 시간 도달
            else:
                return retry_time  # 아직 대기 중
        return None
    except Exception:
        return None


async def register_new_commands():
    """확장 로드 후 새로운 명령어를 등록하는 함수"""
    try:
        logger.info("새로운 슬래시 명령어 등록 시작...")

        # 등록 가능한 명령어 확인
        available_commands = bot.tree.get_commands()
        logger.info(f"로드된 명령어 {len(available_commands)}개 발견")

        if not available_commands:
            logger.warning("등록할 명령어가 없습니다! 확장이 제대로 로드되었는지 확인하세요.")
            return False

        if config.GUILD_ID:
            # 길드 명령어로 등록
            logger.info(f"길드 {config.GUILD_ID}에 명령어 등록 중...")
            guild = discord.Object(id=config.GUILD_ID)
            bot.tree.copy_global_to(guild=guild)

            # 타임아웃 설정 (120초) + 재시도
            synced_commands = None
            for attempt in range(3):
                try:
                    synced_commands = await asyncio.wait_for(
                        bot.tree.sync(guild=guild),
                        timeout=10.0
                    )
                    logger.info(f"길드에 {len(synced_commands)}개 명령어 등록 완료")
                    clear_sync_pending()  # 성공 시 대기 플래그 제거
                    break
                except asyncio.TimeoutError as e:
                    if attempt < 2:
                        logger.warning(f"명령어 동기화 타임아웃 - 재시도 {attempt + 2}/3... 오류: {e}")
                        await asyncio.sleep(5)

                    else:
                        logger.warning("명령어 동기화 타임아웃 (120초) - Discord API가 느립니다")
                        logger.info("명령어가 등록되었을 수 있습니다. Discord에서 확인해주세요.")
                        return True

        else:
            # 전역 명령어로 등록
            logger.info("전역 명령어 등록 중...")
            synced_commands = None
            for attempt in range(3):
                try:
                    synced_commands = await asyncio.wait_for(
                        bot.tree.sync(),
                        timeout=120.0
                    )
                    logger.info(f"{len(synced_commands)}개 전역 명령어 등록 완료 (최대 1시간 후 반영)")
                    clear_sync_pending()  # 성공 시 대기 플래그 제거
                    break
                except asyncio.TimeoutError:
                    if attempt < 2:
                        logger.warning(f"명령어 동기화 타임아웃 - 재시도 {attempt + 2}/3...")
                        await asyncio.sleep(5)
                    else:
                        logger.warning("명령어 동기화 타임아웃 (120초) - Discord API가 느립니다")
                        return True

        # 등록된 명령어 목록 출력
        if synced_commands:
            logger.info(f"최종 등록된 명령어 ({len(synced_commands)}개):")
            for cmd in synced_commands:
                description = cmd.description[:50] + "..." if len(cmd.description) > 50 else cmd.description
                logger.info(f"   - /{cmd.name}: {description}")

        logger.info("새로운 명령어 등록 완료!")
        return True

    except discord.HTTPException as e:
        logger.error(f"Discord API 오류: {e}")
        if e.status == 429:
            # Rate Limit - 다음날 재시도 예약
            retry_after = getattr(e, 'retry_after', 86400)  # 기본 24시간
            if retry_after < 3600:
                retry_after = 86400  # 최소 24시간
            save_sync_pending(int(retry_after))
            logger.info(f"Rate Limit! {retry_after}초 후 재시도 예약됨")

            # 백그라운드에서 재시도 스케줄링
            asyncio.create_task(schedule_sync_retry(retry_after))
        return False
    except Exception as e:
        logger.error(f"새로운 명령어 등록 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


async def schedule_sync_retry(delay: int):
    """Rate Limit 후 지정된 시간 뒤에 명령어 동기화 재시도"""
    logger.info(f"{delay}초 후 명령어 동기화 재시도 예약됨...")
    await asyncio.sleep(delay)

    # 봇이 여전히 실행 중인지 확인
    if bot.is_ready():
        logger.info("명령어 동기화 재시도 시작...")
        success = await register_new_commands()
        if success:
            logger.info("명령어 동기화 재시도 성공!")
        else:
            logger.warning("명령어 동기화 재시도 실패 - 다음 봇 재시작 시 다시 시도합니다.")

@bot.event
async def on_ready():
    """봇 준비 완료 시 실행"""
    logger.info(f"봇 로그인됨: {bot.user}")
    logger.info(f"길드 ID: {config.GUILD_ID}")
    logger.info(f"Success Channel: {config.SUCCESS_CHANNEL_ID}")
    logger.info(f"Failure Channel: {config.FAILURE_CHANNEL_ID}")

    # on_ready는 재접속 시에도 호출되므로, 초기화는 한 번만 실행
    if getattr(bot, '_extensions_loaded', False):
        logger.debug("재접속 감지 - 확장 모듈 이미 로드됨, 초기화 건너뜀")
        return

    # 멤버 자동 추가 설정 확인
    auto_add_status = getattr(config, 'AUTO_ADD_NEW_MEMBERS', True)
    logger.info(f"새 멤버 자동 추가: {'활성화' if auto_add_status else '비활성화'}")

    # 예외 관리자 초기화
    if exception_manager:
        try:
            exception_count = len(exception_manager.get_exceptions())
            logger.info(f"예외 관리자 초기화 완료 (예외 사용자: {exception_count}명)")
        except Exception as e:
            logger.warning(f"예외 관리자 초기화 오류: {e}")
    
    # ===== 1단계: 명령어 삭제 (선택적) =====
    # 명령어 삭제는 Rate Limit을 유발할 수 있으므로 기본적으로 건너뜁니다.
    # 명령어 충돌이 있을 경우에만 CLEAR_COMMANDS_ON_START=True로 설정하세요.
    clear_on_start = getattr(config, 'CLEAR_COMMANDS_ON_START', False)

    if clear_on_start:
        logger.info("=" * 60)
        logger.info("1단계: 기존 슬래시 명령어 삭제")
        logger.info("=" * 60)

        command_clear_success = await clear_and_sync_commands()

        if not command_clear_success:
            logger.warning("명령어 삭제 실패 - 계속 진행합니다.")
    else:
        logger.info("=" * 60)
        logger.info("1단계: 명령어 삭제 건너뜀 (CLEAR_COMMANDS_ON_START=False)")
        logger.info("=" * 60)
    
    # ===== 2단계: 확장(명령어) 로드 =====
    logger.info("=" * 60)
    logger.info("2단계: 확장 모듈 로드 (commands.py)")
    logger.info("=" * 60)
    
    await load_extensions()
    bot._extensions_loaded = True

    # ===== 3단계: 새로운 명령어 등록 =====
    logger.info("=" * 60)
    logger.info("3단계: 새로운 슬래시 명령어 등록")
    logger.info("=" * 60)
    
    register_success = await register_new_commands()
    
    if not register_success:
        logger.warning("새로운 명령어 등록에 실패했습니다!")

    logger.info("=" * 60)
    logger.info("명령어 완전 초기화 작업 완료!")
    logger.info("=" * 60)
    
    # ===== 4단계: 스케줄러 설정 =====
    # 스케줄러 설정
    try:
        from scheduler import setup_scheduler
        logger.info("스케줄러 설정:")
        logger.info(f"   - GUILD_ID: {config.GUILD_ID}")
        logger.info(f"   - SUCCESS_CHANNEL_ID: {config.SUCCESS_CHANNEL_ID}")
        logger.info(f"   - FAILURE_CHANNEL_ID: {config.FAILURE_CHANNEL_ID}")
        
        # 스케줄 시간 정보 추가
        auto_execution_day = getattr(config, 'AUTO_EXECUTION_DAY', 2)  # 기본값: 수요일(2)
        auto_execution_hour = getattr(config, 'AUTO_EXECUTION_HOUR', 3)  # 기본값: 03시
        auto_execution_minute = getattr(config, 'AUTO_EXECUTION_MINUTE', 24)  # 기본값: 24분
        
        # 요일 한글 변환
        day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        korean_day = day_names[auto_execution_day] if 0 <= auto_execution_day <= 6 else "알 수 없음"
        
        logger.info(f"자동 실행 스케줄: 매주 {korean_day} {auto_execution_hour:02d}:{auto_execution_minute:02d}")

        setup_scheduler(bot)
        logger.info("스케줄러 시작됨")
        logger.info("스케줄러 설정 완료")
    except Exception as e:
        logger.error(f"스케줄러 설정 실패: {e}")
        import traceback
        traceback.print_exc()
    
    # 콜사인 백업 스케줄러 시작
    if CALLSIGN_ENABLED:
        try:
            from callsign_backup import CallsignBackupManager, CallsignBackupScheduler
            
            # 백업 관리자 인스턴스 생성
            backup_manager = CallsignBackupManager()
            
            # 스케줄러 시작
            backup_scheduler = CallsignBackupScheduler(bot, backup_manager)
            
            # bot 객체에 백업 관리자 저장 (commands.py에서 사용하기 위해)
            bot.backup_manager = backup_manager
            
            logger.info("콜사인 백업 스케줄러 설정:")
            logger.info("   - 백업 디렉토리: callsign_backups/")
            logger.info("   - 자동 백업: 매주 월요일 08:00")
            logger.info("   - 보관 기간: 30일 (자동 백업만)")
            logger.info("콜사인 백업 스케줄러 시작 완료")

        except ImportError as e:
            logger.warning(f"콜사인 백업 모듈을 로드할 수 없습니다: {e}")
            logger.warning("   callsign_backup.py 파일이 필요합니다.")
            bot.backup_manager = None
        except Exception as e:
            logger.error(f"콜사인 백업 스케줄러 시작 실패: {e}")
            import traceback
            traceback.print_exc()
            bot.backup_manager = None
    else:
        logger.debug("콜사인 기능이 비활성화되어 백업 스케줄러를 시작하지 않습니다.")
        bot.backup_manager = None

    # ===== 4.5단계: BASE_NATION UUID 초기화 =====
    try:
        logger.info("=" * 60)
        logger.info("BASE_NATION UUID 초기화")
        logger.info("=" * 60)
        await config.initialize_base_nation_uuid()
    except Exception as e:
        logger.warning(f"BASE_NATION UUID 초기화 실패: {e}")

    # ===== 5단계: Bulk 데이터 자동 업데이트 시작 =====
    try:
        from bulk_updater import bulk_data_manager

        logger.info("=" * 60)
        logger.info("Bulk 데이터 자동 업데이트 시작")
        logger.info("=" * 60)
        logger.info("   - 업데이트 주기: 15분")
        logger.info("   - API: https://api.planetearth.kr/resident/bulk")
        logger.info("   - Discord 자동 동기화: 활성화")
        logger.info("     * MC 닉네임 변경 -> Discord 별명 자동 변경")
        logger.info("     * 국가 변경 -> 역할 자동 처리")
        logger.info("     * 콜사인 -> 별명에 자동 포함")

        # Discord bot 인스턴스 연결 (자동 닉네임/역할 변경용)
        bulk_data_manager.set_bot(bot)

        # 백그라운드에서 자동 업데이트 시작 (태스크 참조 저장)
        auto_update_task = asyncio.create_task(bulk_data_manager.start_auto_update())
        bulk_data_manager._auto_update_task = auto_update_task

        # bot 객체에 저장 (다른 모듈에서 사용 가능)
        bot.bulk_data_manager = bulk_data_manager

        logger.info("Bulk 데이터 자동 업데이트 시작됨")

        # 기존 BASE_NATION 멤버 중 가입일이 없는 사용자들 보정
        try:
            from database_manager import db_manager

            if config.BASE_NATION:
                backfilled = db_manager.backfill_red_mafia_joined(config.BASE_NATION)
                if backfilled > 0:
                    logger.info(f"기존 {config.BASE_NATION} 멤버 {backfilled}명의 가입일 보정 완료")
        except Exception as backfill_error:
            logger.warning(f"기존 멤버 가입일 보정 실패: {backfill_error}")

    except Exception as e:
        logger.error(f"Bulk 데이터 자동 업데이트 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        bot.bulk_data_manager = None

    # ===== 6단계: 여행 스케줄러 시작 =====
    try:
        from travel_scheduler import setup_travel_scheduler

        logger.info("=" * 60)
        logger.info("여행 스케줄러 시작")
        logger.info("=" * 60)
        logger.info("   - 체크 주기: 1시간")
        logger.info("   - 기능: 여행 시작/종료 자동 처리")
        logger.info("   - 알림: 1일 전, 당일 알림")

        setup_travel_scheduler(bot)
        logger.info("여행 스케줄러 시작됨")

        # 영구 View 등록 (봇 재시작 후에도 버튼이 작동하도록)
        try:
            from commands.user.travel.travel_request import (
                TravelReviewView, TravelAdminControlView, TravelUserControlView,
                TravelPanelView, TravelOverstayView
            )
            from travel_manager import travel_manager, travel_config_manager

            # 활성 여행들의 View 복원
            active_travels = travel_manager.get_active_travels()
            pending_travels = travel_manager.get_pending_travels()

            for travel in pending_travels:
                bot.add_view(TravelReviewView(travel["id"]))

            # BASE_NATION 확인 (외국인 여행 판별용)
            _base_nation = getattr(config, 'BASE_NATION', 'Red_Mafia')

            for travel in active_travels:
                bot.add_view(TravelAdminControlView(travel["id"], travel["discord_id"]))
                # 목적지가 BASE_NATION이면 외국인 여행 → 초대 버튼 포함
                is_foreigner = travel.get("destination_nation", "").lower() == _base_nation.lower()
                bot.add_view(TravelUserControlView(travel["id"], travel["discord_id"], show_invite=is_foreigner))

            # 최근 완료된 여행의 미복귀 View 복원 (최근 50개)
            completed_travels = travel_manager.get_all_travels(limit=50)
            overstay_count = 0
            for travel in completed_travels:
                if travel["status"] == "completed":
                    bot.add_view(TravelOverstayView(travel["id"], travel["discord_id"]))
                    overstay_count += 1

            # 여행 신청 패널 View 복원
            panel_info = travel_config_manager.get_panel_info()
            if panel_info:
                bot.add_view(TravelPanelView())
                logger.info(f"여행 신청 패널 View 복원: channel={panel_info['channel_id']}")

            logger.info(f"여행 영구 View 등록: 대기 {len(pending_travels)}개, 활성 {len(active_travels)}개, 미복귀 View {overstay_count}개")
        except Exception as view_error:
            logger.warning(f"여행 View 등록 실패: {view_error}")

    except ImportError as e:
        logger.warning(f"travel_scheduler 모듈을 로드할 수 없습니다: {e}")
        logger.warning("   여행 시스템이 비활성화됩니다.")
    except Exception as e:
        logger.error(f"여행 스케줄러 시작 실패: {e}")
        import traceback
        traceback.print_exc()

    # ===== 6.5단계: 경고 영구 View 등록 =====
    try:
        from commands.admin.warning.warning_manage import WarningLogView
        from database_manager import db_manager

        warning_views = db_manager.get_warnings_with_message_id(config.GUILD_ID)
        for w in warning_views:
            bot.add_view(WarningLogView(w['id']))

        if warning_views:
            logger.info(f"경고 영구 View 등록: {len(warning_views)}개")
    except Exception as warning_view_error:
        logger.warning(f"경고 View 등록 실패: {warning_view_error}")

    # ===== 6.6단계: 역할신청 패널 영구 View 등록 =====
    try:
        from commands.admin.role_panel.role_panel import RolePanelApplyView
        from database_manager import db_manager as _rp_db

        panels = _rp_db.get_active_role_panels(config.GUILD_ID)
        registered = 0
        for p in panels:
            if p.get('message_id'):
                bot.add_view(RolePanelApplyView(p['panel_id'], p['role_id']))
                registered += 1

        if registered:
            logger.info(f"역할신청 패널 영구 View 등록: {registered}개")
    except Exception as e:
        logger.warning(f"역할신청 패널 View 등록 실패: {e}")

    # ===== 6.8단계: 복귀 스케줄러 시작 =====
    try:
        from return_scheduler import setup_return_scheduler

        logger.info("=" * 60)
        logger.info("복귀 스케줄러 시작")
        logger.info("=" * 60)
        logger.info("   - 잠수 체크: 매일 03:00 (60일 이상 미접속 국민)")
        logger.info("   - 잠수 DM: 매일 16:00 (최초 1회)")
        logger.info("   - 일일 핑: 매일 13:00 (복귀채팅 채널)")

        setup_return_scheduler(bot)
        logger.info("복귀 스케줄러 시작 완료")

    except ImportError as e:
        logger.warning(f"return_scheduler 모듈을 로드할 수 없습니다: {e}")
    except Exception as e:
        logger.error(f"복귀 스케줄러 시작 실패: {e}")
        import traceback
        traceback.print_exc()

    # ===== 6.9단계: 복귀 닫기 버튼 영구 View 등록 =====
    try:
        from commands.admin.return_system.ticket_handler import CloseTicketView
        bot.add_view(CloseTicketView())
        logger.info("CloseTicketView 영구 등록 완료")
    except Exception as e:
        logger.warning(f"CloseTicketView 등록 실패: {e}")

    # ===== 6.7단계: 공지 스케줄러 시작 =====
    try:
        from announcement_scheduler import setup_announcement_scheduler

        logger.info("=" * 60)
        logger.info("공지 스케줄러 시작")
        logger.info("=" * 60)
        logger.info("   - 체크 주기: 30초")
        logger.info("   - 기능: 예약된 공지 자동 전송")

        setup_announcement_scheduler(bot)
        logger.info("공지 스케줄러 시작 완료")

    except ImportError as e:
        logger.warning(f"공지 스케줄러 모듈을 로드할 수 없습니다: {e}")
    except Exception as e:
        logger.error(f"공지 스케줄러 시작 실패: {e}")
        import traceback
        traceback.print_exc()

    logger.info("봇이 완전히 준비되었습니다!")

    # ===== 7단계: 시작 알림 전송 =====
    try:
        import aiohttp
        from version import VERSION, GITHUB_REPO

        # GitHub 최신 릴리즈 확인
        latest_version = None
        release_url = None
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": config.USER_AGENT}) as session:
                async with session.get(
                    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        latest_version = data.get("tag_name", "").lstrip("v")
                        release_url = data.get("html_url")
        except Exception:
            pass

        log_channel = bot.get_channel(config.LOG_CHANNEL_ID)
        if log_channel:
            is_latest = latest_version is None or latest_version == VERSION

            embed = discord.Embed(
                title="🟢 봇 시작됨",
                color=0x57F287 if is_latest else 0xFEE75C,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="현재 버전", value=f"`v{VERSION}`", inline=True)

            if latest_version:
                if is_latest:
                    embed.add_field(name="최신 버전", value=f"`v{latest_version}` ✅", inline=True)
                else:
                    embed.add_field(
                        name="최신 버전",
                        value=f"`v{latest_version}` ⬆️ [업데이트]({release_url})" if release_url else f"`v{latest_version}` ⬆️ 업데이트 필요",
                        inline=True
                    )
            else:
                embed.add_field(name="최신 버전", value="확인 실패", inline=True)

            embed.add_field(name="서버", value=f"`{config.BASE_NATION}`", inline=True)
            await log_channel.send(embed=embed)
    except Exception as e:
        logger.warning(f"시작 알림 전송 실패: {e}")

    # ===== 8단계: 터미널 명령어 입력 핸들러 시작 =====
    asyncio.create_task(terminal_input_handler())

@bot.event
async def on_message(message):
    """메시지 이벤트 처리 - command_loader를 통해 처리"""
    try:
        # 새로운 명령어 시스템의 메시지 핸들러 호출
        # &MF 명령어 등은 commands/admin/MF/mf_handler.py에서 처리됨
        if hasattr(bot, 'command_loader'):
            try:
                await bot.command_loader.handle_message(message)
            except Exception as handler_error:
                logger.error(f"메시지 핸들러 오류: {handler_error}")

    except Exception as e:
        logger.error(f"on_message 이벤트 처리 중 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 다른 명령어도 처리할 수 있도록 process_commands 호출
        await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    """새로운 멤버가 서버에 들어올 때 자동으로 대기열에 추가"""
    try:
        logger.info(f"새 멤버 입장 감지: {member.display_name} ({member.id})")

        # AUTO_ADD_NEW_MEMBERS 설정 확인 (기본값: True)
        auto_add_enabled = getattr(config, 'AUTO_ADD_NEW_MEMBERS', True)
        if not auto_add_enabled:
            logger.warning(f"자동 추가 비활성화 상태 - {member.display_name} 건너뜀")
            return

        # queue_manager 로드
        try:
            from queue_manager import queue_manager
        except ImportError as e:
            logger.error(f"queue_manager 로드 실패: {e}")
            return

        # 예외 사용자 확인 (두 가지 방법으로 확인)
        is_exception = False

        # 방법 1: exception_manager 사용
        if exception_manager:
            try:
                is_exception = exception_manager.is_exception(member.id)
                logger.debug(f"exception_manager 확인: {member.display_name} -> 예외 사용자: {is_exception}")
            except Exception as e:
                logger.warning(f"exception_manager 확인 오류: {e}")

        # 방법 2: scheduler의 is_exception_user 함수 사용 (fallback)
        if not is_exception and is_exception_user:
            try:
                is_exception = is_exception_user(member.id)
                logger.debug(f"scheduler 확인: {member.display_name} -> 예외 사용자: {is_exception}")
            except Exception as e:
                logger.warning(f"scheduler 예외 확인 오류: {e}")

        # 예외 사용자 처리
        if is_exception:
            logger.info(f"예외 사용자이므로 대기열 추가 제외: {member.display_name} ({member.id})")

            # 예외 사용자용 환영 메시지 (선택사항)
            try:
                welcome_channel_id = getattr(config, 'WELCOME_CHANNEL_ID', None)
                if welcome_channel_id:
                    welcome_channel = bot.get_channel(welcome_channel_id)
                    if welcome_channel:
                        await welcome_channel.send(
                            f"🎉 {member.mention}님 환영합니다! "
                            f"예외 설정으로 인해 자동 인증 대상에서 제외됩니다."
                        )
                        logger.info(f"예외 사용자 환영 메시지 전송됨: {member.display_name}")
            except Exception as e:
                logger.warning(f"예외 사용자 환영 메시지 전송 실패: {e}")
            return

        # 대기열에 우선 추가 (맨 앞에 추가)
        try:
            # 이미 대기열에 있는지 확인
            if hasattr(queue_manager, 'is_user_in_queue') and queue_manager.is_user_in_queue(member.id):
                logger.debug(f"이미 대기열에 있음: {member.display_name}")
            else:
                # 우선순위로 맨 앞에 추가
                if hasattr(queue_manager, 'add_user_priority'):
                    queue_manager.add_user_priority(member.id)
                    logger.info(f"대기열 1순위로 추가됨: {member.display_name} (현재 대기열: {queue_manager.get_queue_size()}명)")
                    if bot_logger:
                        bot_logger.log_queue(
                            f"신규 멤버 우선 대기열 추가: {member.display_name}",
                            target_user_id=member.id, target_user_name=member.display_name,
                            source="event_handler", action="queue_add_priority",
                            details={"event": "on_member_join", "queue_size": queue_manager.get_queue_size()}
                        )
                else:
                    # fallback: 일반 추가
                    queue_manager.add_user(member.id)
                    logger.info(f"대기열에 추가됨: {member.display_name} (현재 대기열: {queue_manager.get_queue_size()}명)")
                    if bot_logger:
                        bot_logger.log_queue(
                            f"신규 멤버 대기열 추가 (fallback): {member.display_name}",
                            target_user_id=member.id, target_user_name=member.display_name,
                            source="event_handler", action="queue_add",
                            details={"event": "on_member_join", "queue_size": queue_manager.get_queue_size()}
                        )

                # 성공 채널에 알림 (선택사항)
                try:
                    success_channel = bot.get_channel(config.SUCCESS_CHANNEL_ID)
                    if success_channel:
                        await success_channel.send(f"📝 새 멤버 우선 대기열 추가: {member.mention} (대기: {queue_manager.get_queue_size()}명)")
                except Exception as e:
                    logger.warning(f"대기열 추가 알림 전송 실패: {e}")
        except Exception as e:
            logger.error(f"대기열 추가 실패: {member.display_name} - {e}")
            return

        # 환영 메시지
        try:
            welcome_channel_id = getattr(config, 'WELCOME_CHANNEL_ID', None)
            if welcome_channel_id:
                welcome_channel = bot.get_channel(welcome_channel_id)
                if welcome_channel:
                    await welcome_channel.send(
                        f"🎉 {member.mention}님 환영합니다! "
                        f"마인크래프트 계정 연동을 위해 자동으로 인증 대기열에 추가되었습니다. "
                        f"잠시만 기다려주세요! (현재 대기: {queue_manager.get_queue_size()}명)"
                    )
                    logger.info(f"환영 메시지 전송됨: {member.display_name}")
            else:
                logger.debug(f"환영 채널이 설정되지 않음 (WELCOME_CHANNEL_ID)")
        except Exception as e:
            logger.warning(f"환영 메시지 전송 실패: {e}")

    except Exception as e:
        logger.error(f"on_member_join 이벤트 처리 중 오류: {e}")
        import traceback
        traceback.print_exc()

@bot.event
async def on_error(event, *args, **kwargs):
    """오류 발생 시 로그"""
    import traceback
    logger.error(f"이벤트 오류 발생: {event}")
    traceback.print_exc()

# 확장 로드 함수
async def load_extensions():
    """확장 모듈 로드 - 새로운 commands 폴더 시스템"""

    logger.info("명령어 로드 시작...")

    try:
        # 새로운 commands 폴더의 자동 로더 사용
        from commands import setup

        # 명령어 자동 로드
        command_loader = setup(bot)

        # bot 객체에 command_loader 저장 (on_message에서 사용)
        bot.command_loader = command_loader

        logger.info("명령어 자동 로더 설정 완료")

    except Exception as e:
        logger.error(f"명령어 로드 실패: {e}")
        import traceback
        traceback.print_exc()

    logger.info("명령어 로드 완료!")

async def main():
    """메인 실행 함수"""
    # 토큰 검증
    if not config.DISCORD_TOKEN:
        logger.error("Discord 토큰이 설정되지 않았습니다!")
        logger.info(".env 파일에 DISCORD_TOKEN을 설정해주세요.")
        return

    # 봇 실행
    try:
        async with bot:
            await bot.start(config.DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.error("Discord 토큰이 잘못되었습니다!")
        logger.info("Discord Developer Portal에서 새로운 토큰을 생성해주세요.")
    except asyncio.CancelledError:
        logger.info("봇 작업이 취소되었습니다.")
    except Exception as e:
        logger.error(f"봇 실행 중 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 봇 종료 시 정리
        try:
            from scheduler import stop_scheduler
            stop_scheduler()
        except Exception:
            pass

        # Bulk updater 정리
        try:
            from bulk_updater import bulk_data_manager
            bulk_data_manager.stop_auto_update()
        except Exception:
            pass

        # 여행 스케줄러 정리
        try:
            from travel_scheduler import stop_travel_scheduler
            stop_travel_scheduler()
        except Exception:
            pass

        # 공지 스케줄러 정리
        try:
            from announcement_scheduler import stop_announcement_scheduler
            stop_announcement_scheduler()
        except Exception:
            pass

        # 복귀 스케줄러 정리
        try:
            from return_scheduler import stop_return_scheduler
            stop_return_scheduler()
        except Exception:
            pass

        # 봇 연결 종료
        if not bot.is_closed():
            await bot.close()

        logger.info("봇 정리 완료")


async def handle_noob_command(cmd: str):
    """noob 명령어 처리: noob -day / <디스코드ID> / YYYY.MM.DD"""
    from datetime import datetime

    # 파싱: noob -day / id / date
    parts = cmd.split()

    if len(parts) < 6 or parts[1] != "-day" or parts[2] != "/" or parts[4] != "/":
        logger.info("사용법: noob -day / <디스코드ID> / YYYY.MM.DD")
        logger.info("예시: noob -day / 123456789012345678 / 2025.01.15")
        return

    discord_id_str = parts[3]
    date_str = parts[5]

    # 디스코드 ID 파싱
    try:
        discord_id = int(discord_id_str)
    except ValueError:
        logger.error(f"잘못된 디스코드 ID: {discord_id_str}")
        logger.info("   디스코드 ID는 숫자여야 합니다.")
        return

    # 날짜 파싱
    try:
        new_joined_at = datetime.strptime(date_str, "%Y.%m.%d")
    except ValueError:
        logger.error(f"잘못된 날짜 형식: {date_str}")
        logger.info("   형식: YYYY.MM.DD (예: 2025.01.15)")
        return

    # 데이터베이스 연결
    try:
        from database_manager import db_manager
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        return

    # 사용자 정보 확인
    user_info = db_manager.get_user_info(discord_id)
    if not user_info:
        logger.error(f"디스코드 ID {discord_id}는 데이터베이스에 없습니다.")
        return

    # 기존 가입일 확인
    old_joined_at = db_manager.get_red_mafia_joined(discord_id)
    old_joined_str = old_joined_at.strftime('%Y.%m.%d %H:%M:%S') if old_joined_at else "미설정"

    # 사용자 정보 출력
    mc_name = user_info.get('current_minecraft_name', '알 수 없음')
    nation = user_info.get('current_nation', '없음')

    logger.info(f"{'='*50}")
    logger.info(f"대상: {discord_id}")
    logger.info(f"마인크래프트: {mc_name}")
    logger.info(f"현재 국가: {nation}")
    logger.info(f"이전 가입일: {old_joined_str}")
    logger.info(f"새 가입일: {new_joined_at.strftime('%Y.%m.%d %H:%M:%S')}")
    logger.info(f"{'='*50}")

    # 가입일 업데이트
    success = db_manager.set_red_mafia_joined(discord_id, new_joined_at)

    if success:
        # 남은 뉴비 기간 계산
        days_since = (datetime.now() - new_joined_at).days
        days_left = 14 - days_since

        if days_left > 0:
            status = f"D-{days_left} (뉴비)"
        else:
            status = f"뉴비 기간 만료 ({abs(days_left)}일 초과)"

        logger.info("가입일 조정 완료!")
        logger.info(f"뉴비 상태: {status}")
    else:
        logger.error("가입일 조정 실패")


async def handle_mclink_command(cmd: str):
    """mclink 명령어 처리: mclink <디스코드ID> <MC닉네임>"""

    parts = cmd.split()

    if len(parts) != 3:
        logger.info("사용법: mclink <디스코드ID> <MC닉네임>")
        logger.info("예시: mclink 123456789012345678 Steve")
        return

    discord_id_str = parts[1]
    mc_nick = parts[2]

    # 디스코드 ID 파싱
    try:
        discord_id = int(discord_id_str)
    except ValueError:
        logger.error(f"잘못된 디스코드 ID: {discord_id_str}")
        logger.info("   디스코드 ID는 숫자여야 합니다.")
        return

    # Bulk 데이터에서 MC 닉네임으로 UUID 조회
    if not hasattr(bot, 'bulk_data_manager') or not bot.bulk_data_manager:
        logger.error("Bulk 데이터 매니저가 초기화되지 않았습니다.")
        return

    resident = bot.bulk_data_manager.get_resident_by_name(mc_nick)
    if not resident:
        # 메모리 캐시에 없으면 DB all_players 테이블에서 검색
        try:
            from database_manager import db_manager
            db_player = db_manager.get_player_by_name(mc_nick)
            if db_player:
                resident = db_player
                logger.debug("메모리 캐시에 없어 DB에서 조회했습니다.")
        except Exception:
            pass

    if not resident:
        logger.error(f"MC 닉네임 '{mc_nick}'을(를) Bulk 데이터 및 DB에서 찾을 수 없습니다.")
        logger.info("   서버에 접속한 적이 있는 닉네임인지 확인해주세요.")
        return

    mc_uuid = resident.get('uuid', '')
    mc_name = resident.get('name', mc_nick)
    nation = resident.get('nation', '없음')
    town = resident.get('town', '없음')

    # 기존 연동 정보 확인
    try:
        from database_manager import db_manager
    except Exception as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        return

    existing_user = db_manager.get_user_info(discord_id)

    logger.info(f"{'='*50}")
    logger.info("MC 계정 수동 연동")
    logger.info(f"{'='*50}")
    logger.info(f"   디스코드 ID: {discord_id}")
    logger.info(f"   MC 닉네임:   {mc_name}")
    logger.info(f"   MC UUID:     {mc_uuid}")
    logger.info(f"   국가:        {nation}")
    logger.info(f"   마을:        {town}")

    if existing_user:
        old_mc = existing_user.get('current_minecraft_name', '없음')
        logger.warning(f"   기존 연동: {old_mc} -> {mc_name} (덮어쓰기)")

    logger.info(f"{'='*50}")

    # DB에 연동 저장
    success = db_manager.add_or_update_user(discord_id, mc_uuid, mc_name)

    if not success:
        logger.error("연동 실패: 데이터베이스 저장 오류")
        return

    # 국가/마을 정보도 업데이트
    nation_uuid = resident.get('nationUuid', None)
    town_uuid = resident.get('townUuid', None)
    db_manager.update_user_nation_info(
        discord_id,
        nation=nation,
        nation_uuid=nation_uuid,
        town=town,
        town_uuid=town_uuid
    )

    logger.info(f"연동 완료! {discord_id} <-> {mc_name} ({mc_uuid})")

    # Discord 별명 변경 시도
    if config.GUILD_ID:
        try:
            guild = bot.get_guild(config.GUILD_ID)
            if guild:
                member = guild.get_member(discord_id)
                if member:
                    # 콜사인 확인
                    display_name = mc_name
                    if CALLSIGN_ENABLED and callsign_manager:
                        try:
                            callsign = callsign_manager.get_callsign(discord_id)
                            if callsign:
                                display_name = f"[{callsign}] {mc_name}"
                        except Exception:
                            pass

                    await member.edit(nick=display_name)
                    logger.info(f"Discord 별명 변경: {display_name}")
                else:
                    logger.warning(f"서버에서 멤버를 찾을 수 없습니다 (ID: {discord_id})")
            else:
                logger.warning(f"길드를 찾을 수 없습니다 (ID: {config.GUILD_ID})")
        except Exception as e:
            logger.warning(f"Discord 별명 변경 실패: {e}")


async def terminal_input_handler():
    """터미널에서 명령어를 입력받아 처리하는 핸들러"""
    logger.info("=" * 60)
    logger.info("터미널 명령어 모드 활성화")
    logger.info("   사용 가능한 명령어:")
    logger.info("   - status: 봇 상태 확인")
    logger.info("   - queue: 대기열 상태 확인")
    logger.info("   - bulk: Bulk 데이터 상태 확인")
    logger.info("   - update <resident|nation|town|all>: Bulk 수동 업데이트")
    logger.info("   - mclink <디스코드ID> <MC닉네임>: MC 계정 수동 연동")
    logger.info("   - sync: 명령어 재동기화")
    logger.info("   - reload: 확장 모듈 리로드")
    logger.info("   - help: 도움말")
    logger.info("   - quit / exit: 봇 종료")
    logger.info("=" * 60)

    while True:
        try:
            # 비동기로 입력 받기
            cmd = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input(">> ").strip().lower()
            )

            if not cmd:
                continue

            if cmd in ("quit", "exit", "q"):
                logger.info("종료 명령 감지...")
                # 봇 종료
                await bot.close()
                break

            elif cmd == "status":
                logger.info(f"봇 상태: {'온라인' if bot.is_ready() else '오프라인'}")
                logger.info(f"   - 연결된 서버: {len(bot.guilds)}개")
                logger.info(f"   - 지연시간: {round(bot.latency * 1000)}ms")
                if bot.user:
                    logger.info(f"   - 봇 유저: {bot.user.name}#{bot.user.discriminator}")

            elif cmd == "queue":
                try:
                    from queue_manager import queue_manager
                    logger.info(f"대기열 상태:")
                    logger.info(f"   - 현재 대기: {queue_manager.get_queue_size()}명")
                except Exception as e:
                    logger.error(f"대기열 확인 실패: {e}")

            elif cmd == "bulk":
                if hasattr(bot, 'bulk_data_manager') and bot.bulk_data_manager:
                    manager = bot.bulk_data_manager
                    logger.info("Bulk 데이터 상태:")
                    logger.info(f"   - 주민 데이터: {len(manager.bulk_data)}개")
                    logger.info(f"   - 자동 업데이트: {'실행중' if manager.is_running else '중지됨'}")
                    if manager.last_update:
                        logger.info(f"   - 마지막 업데이트: {manager.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    logger.error("Bulk 데이터 매니저가 초기화되지 않았습니다.")

            elif cmd == "sync":
                logger.info("명령어 동기화 중...")
                try:
                    if config.GUILD_ID:
                        guild = discord.Object(id=config.GUILD_ID)
                        synced = await bot.tree.sync(guild=guild)
                    else:
                        synced = await bot.tree.sync()
                    logger.info(f"{len(synced)}개 명령어 동기화 완료")
                except Exception as e:
                    logger.error(f"동기화 실패: {e}")

            elif cmd == "reload":
                logger.info("확장 모듈 리로드 중...")
                try:
                    await load_extensions()
                    logger.info("확장 모듈 리로드 완료")
                except Exception as e:
                    logger.error(f"리로드 실패: {e}")

            elif cmd.startswith("update"):
                # update 명령어 처리: update resident / update nation / update town / update all
                parts = cmd.split()
                if len(parts) < 2:
                    logger.info("사용법: update <resident|nation|town|all>")
                    logger.info("   - update resident: 주민 데이터 업데이트")
                    logger.info("   - update nation: 국가 데이터 업데이트")
                    logger.info("   - update town: 마을 데이터 업데이트")
                    logger.info("   - update all: 모든 데이터 업데이트")
                    continue

                update_type = parts[1].lower()

                if hasattr(bot, 'bulk_data_manager') and bot.bulk_data_manager:
                    manager = bot.bulk_data_manager

                    if update_type == "resident":
                        logger.info("Resident Bulk 데이터 업데이트 중...")
                        success = await asyncio.to_thread(manager.fetch_bulk_data, save_to_db=True, force=True)
                        if success:
                            logger.info(f"Resident 업데이트 완료: {len(manager.bulk_data)}명")
                            # Discord 업데이트 처리
                            await manager.process_discord_updates()
                        else:
                            logger.error("Resident 업데이트 실패")

                    elif update_type == "nation":
                        logger.info("Nation Bulk 데이터 업데이트 중...")
                        success = await asyncio.to_thread(manager.fetch_nation_bulk_data, save_to_db=True, force=True)
                        if success:
                            logger.info(f"Nation 업데이트 완료: {len(manager.nation_data)}개")
                        else:
                            logger.error("Nation 업데이트 실패")

                    elif update_type == "town":
                        logger.info("Town Bulk 데이터 업데이트 중...")
                        success = await asyncio.to_thread(manager.fetch_town_bulk_data, save_to_db=True, force=True)
                        if success:
                            logger.info(f"Town 업데이트 완료: {len(manager.town_data)}개")
                        else:
                            logger.error("Town 업데이트 실패")

                    elif update_type == "all":
                        logger.info("모든 Bulk 데이터 업데이트 중...")
                        success = await asyncio.to_thread(manager.fetch_all_bulk_data, save_to_db=True, force=True)
                        if success:
                            logger.info("전체 업데이트 완료:")
                            logger.info(f"   - Resident: {len(manager.bulk_data)}명")
                            logger.info(f"   - Nation: {len(manager.nation_data)}개")
                            logger.info(f"   - Town: {len(manager.town_data)}개")
                            # Discord 업데이트 처리
                            await manager.process_discord_updates()
                        else:
                            logger.error("전체 업데이트 실패")

                    else:
                        logger.warning(f"알 수 없는 업데이트 타입: {update_type}")
                        logger.info("   사용 가능: resident, nation, town, all")
                else:
                    logger.error("Bulk 데이터 매니저가 초기화되지 않았습니다.")

            elif cmd.startswith("mclink"):
                # mclink 명령어 처리: mclink <디스코드ID> <MC닉네임>
                await handle_mclink_command(cmd)

            elif cmd.startswith("noob"):
                # noob 명령어 처리: noob -day / <디스코드ID> / YYYY.MM.DD
                await handle_noob_command(cmd)

            elif cmd == "help":
                logger.info("사용 가능한 명령어:")
                logger.info("   - status: 봇 상태 확인")
                logger.info("   - queue: 대기열 상태 확인")
                logger.info("   - bulk: Bulk 데이터 상태 확인")
                logger.info("   - update <type>: Bulk 데이터 수동 업데이트")
                logger.info("       * update resident: 주민 데이터 업데이트")
                logger.info("       * update nation: 국가 데이터 업데이트")
                logger.info("       * update town: 마을 데이터 업데이트")
                logger.info("       * update all: 모든 데이터 업데이트")
                logger.info("   - mclink <디스코드ID> <MC닉네임>: MC 계정 수동 연동")
                logger.info("   - sync: 명령어 재동기화")
                logger.info("   - reload: 확장 모듈 리로드")
                logger.info("   - noob -day / <디스코드ID> / YYYY.MM.DD: 뉴비 가입일 조정")
                logger.info("   - help: 이 도움말")
                logger.info("   - quit / exit: 봇 종료")

            else:
                logger.warning(f"알 수 없는 명령어: {cmd}")
                logger.info("   'help'를 입력하여 사용 가능한 명령어를 확인하세요.")

        except EOFError:
            # 입력 스트림 종료 시
            break
        except Exception as e:
            logger.error(f"명령어 처리 오류: {e}")


def run_bot():
    """봇 실행 래퍼 함수"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Ctrl+C 감지 - 봇 종료 중...")

        # Bulk updater 즉시 정리
        try:
            from bulk_updater import bulk_data_manager
            bulk_data_manager.stop_auto_update()
        except Exception:
            pass

        # 스케줄러 즉시 정리
        try:
            from scheduler import stop_scheduler
            stop_scheduler()
        except Exception:
            pass

        # 여행 스케줄러 즉시 정리
        try:
            from travel_scheduler import stop_travel_scheduler
            stop_travel_scheduler()
        except Exception:
            pass

        # 복귀 스케줄러 즉시 정리
        try:
            from return_scheduler import stop_return_scheduler
            stop_return_scheduler()
        except Exception:
            pass
    finally:
        # 모든 태스크 정리
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()

            # 취소된 태스크들이 완료되도록 대기 (타임아웃 3초)
            if pending:
                loop.run_until_complete(
                    asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=3.0
                    )
                )
        except asyncio.TimeoutError:
            logger.warning("태스크 정리 타임아웃 - 강제 종료")
        except Exception:
            pass

        # 이벤트 루프 종료
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass

        loop.close()
        logger.info("봇이 안전하게 종료되었습니다.")

        # 프로세스 강제 종료 (백그라운드 스레드가 남아있을 수 있음)
        import os
        os._exit(0)


# 메인 실행
if __name__ == "__main__":
    logger.info("Discord Bot 시작 중...")
    config.print_config_status()
    run_bot()