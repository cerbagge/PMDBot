import discord
from discord.ext import commands
import asyncio
import sys

# 설정 로드
try:
    from config import config
except ImportError:
    print("❌ config.py 파일을 찾을 수 없습니다. config.py 파일을 생성해주세요.")
    sys.exit(1)

# 예외 관리자 로드
try:
    from exception_manager import exception_manager
    print("✅ exception_manager 모듈 로드됨")
except ImportError:
    print("⚠️ exception_manager.py 파일을 찾을 수 없습니다. 예외 관리 기능이 비활성화됩니다.")
    exception_manager = None

# scheduler 모듈 로드 (자동 처리에 필요)
try:
    from scheduler import is_exception_user
    print("✅ scheduler 모듈에서 예외 사용자 확인 함수 로드됨")
except ImportError:
    print("⚠️ scheduler.py에서 is_exception_user 함수를 로드할 수 없습니다.")
    is_exception_user = None

# callsign_manager 모듈 로드
try:
    from callsign_manager import callsign_manager
    print("✅ callsign_manager 모듈 로드됨")
    CALLSIGN_ENABLED = True
except ImportError:
    print("⚠️ callsign_manager.py 파일을 찾을 수 없습니다. 콜사인 기능이 비활성화됩니다.")
    callsign_manager = None
    CALLSIGN_ENABLED = False

# Intents 설정
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

async def clear_and_sync_commands():
    """모든 기존 명령어를 완전히 삭제하고 새로운 명령어를 등록하는 함수"""
    try:
        print("🧹 모든 슬래시 명령어 완전 삭제 및 재등록 시작...")
        
        # Step 1: 전역 명령어 완전 삭제
        print("🌍 전역 명령어 완전 삭제 중...")
        try:
            existing_global_commands = await bot.tree.fetch_commands()
            print(f"📋 기존 전역 명령어 {len(existing_global_commands)}개 발견")
            
            # 전역 명령어 삭제
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()
            print(f"✅ {len(existing_global_commands)}개 전역 명령어 삭제 완료")
            
            # 전역 명령어 삭제 반영 대기
            if existing_global_commands:
                print("⏳ 전역 명령어 삭제 반영 대기 중... (15초)")
                await asyncio.sleep(15)
        except Exception as e:
            print(f"⚠️ 전역 명령어 삭제 오류: {e}")
        
        # Step 2: 길드 명령어 완전 삭제 (설정된 경우)
        if config.GUILD_ID:
            print(f"🏰 길드 {config.GUILD_ID} 명령어 완전 삭제 중...")
            try:
                guild = discord.Object(id=config.GUILD_ID)
                existing_guild_commands = await bot.tree.fetch_commands(guild=guild)
                print(f"📋 기존 길드 명령어 {len(existing_guild_commands)}개 발견")
                
                # 길드 명령어 삭제
                bot.tree.clear_commands(guild=guild)
                await bot.tree.sync(guild=guild)
                print(f"✅ {len(existing_guild_commands)}개 길드 명령어 삭제 완료")
                
                # 길드 명령어 삭제 반영 대기
                if existing_guild_commands:
                    print("⏳ 길드 명령어 삭제 반영 대기 중... (5초)")
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"⚠️ 길드 명령어 삭제 오류: {e}")
        
        # Step 3: 추가 대기 시간 (완전한 삭제 보장)
        print("⏳ 명령어 삭제 완전 반영 대기 중... (10초)")
        await asyncio.sleep(10)
        
        # Step 4: 삭제 확인
        print("🔍 삭제 완료 확인 중...")
        try:
            remaining_global = await bot.tree.fetch_commands()
            remaining_count = len(remaining_global)
            
            if config.GUILD_ID:
                guild = discord.Object(id=config.GUILD_ID)
                remaining_guild = await bot.tree.fetch_commands(guild=guild)
                guild_count = len(remaining_guild)
                print(f"📊 삭제 후 잔여 명령어 - 전역: {remaining_count}개, 길드: {guild_count}개")
            else:
                print(f"📊 삭제 후 잔여 전역 명령어: {remaining_count}개")
            
            if remaining_count > 0 or (config.GUILD_ID and guild_count > 0):
                print("⚠️ 일부 명령어가 아직 남아있습니다. 추가 대기...")
                await asyncio.sleep(10)
            else:
                print("✅ 모든 명령어 삭제 확인 완료!")
                
        except Exception as e:
            print(f"⚠️ 삭제 확인 중 오류: {e}")
        
        print("🧹 명령어 완전 삭제 작업 완료!")
        print("⏳ 새로운 명령어 등록을 위해 확장 로드를 기다립니다...")
        return True
        
    except discord.Forbidden:
        print("❌ 명령어 관리 권한이 없습니다!")
        print("💡 봇에 다음 권한이 있는지 확인하세요:")
        print("   - applications.commands (슬래시 명령어)")
        print("   - Use Slash Commands")
        return False
    except discord.HTTPException as e:
        print(f"❌ Discord API 오류: {e}")
        if "429" in str(e):
            print("💡 너무 많은 요청으로 인한 제한입니다. 잠시 후 다시 시도하세요.")
        return False
    except Exception as e:
        print(f"❌ 명령어 삭제 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

async def register_new_commands():
    """확장 로드 후 새로운 명령어를 등록하는 함수"""
    try:
        print("\n📝 새로운 슬래시 명령어 등록 시작...")
        
        # 등록 가능한 명령어 확인
        available_commands = bot.tree.get_commands()
        print(f"🔍 로드된 명령어 {len(available_commands)}개 발견")
        
        if not available_commands:
            print("⚠️ 등록할 명령어가 없습니다! 확장이 제대로 로드되었는지 확인하세요.")
            return False
            
        if config.GUILD_ID:
            # 길드 명령어로 등록
            print(f"🏰 길드 {config.GUILD_ID}에 명령어 등록 중...")
            guild = discord.Object(id=config.GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced_commands = await bot.tree.sync(guild=guild)
            print(f"✅ 길드에 {len(synced_commands)}개 명령어 등록 완료")
            
        else:
            # 전역 명령어로 등록
            print("🌍 전역 명령어 등록 중...")
            synced_commands = await bot.tree.sync()
            print(f"✅ {len(synced_commands)}개 전역 명령어 등록 완료 (최대 1시간 후 반영)")
        
        # 등록된 명령어 목록 출력
        if synced_commands:
            print(f"📝 최종 등록된 명령어 ({len(synced_commands)}개):")
            for cmd in synced_commands:
                description = cmd.description[:50] + "..." if len(cmd.description) > 50 else cmd.description
                print(f"   - /{cmd.name}: {description}")
        
        print("🎉 새로운 명령어 등록 완료!")
        return True
        
    except Exception as e:
        print(f"❌ 새로운 명령어 등록 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

@bot.event
async def on_ready():
    """봇 준비 완료 시 실행"""
    print(f"✅ 봇 로그인됨: {bot.user}")
    print(f"✅ 길드 ID: {config.GUILD_ID}")
    print(f"✅ Success Channel: {config.SUCCESS_CHANNEL_ID}")
    print(f"✅ Failure Channel: {config.FAILURE_CHANNEL_ID}")
    
    # 멤버 자동 추가 설정 확인
    auto_add_status = getattr(config, 'AUTO_ADD_NEW_MEMBERS', True)
    print(f"✅ 새 멤버 자동 추가: {'활성화' if auto_add_status else '비활성화'}")
    
    # 예외 관리자 초기화
    if exception_manager:
        try:
            exception_count = len(exception_manager.get_exceptions())
            print(f"✅ 예외 관리자 초기화 완료 (예외 사용자: {exception_count}명)")
        except Exception as e:
            print(f"⚠️ 예외 관리자 초기화 오류: {e}")
    
    # ===== 1단계: 모든 기존 명령어 완전 삭제 =====
    print("\n" + "="*60)
    print("🧹 1단계: 모든 기존 슬래시 명령어 완전 삭제")
    print("="*60)
    
    command_clear_success = await clear_and_sync_commands()
    
    if not command_clear_success:
        print("❌ 명령어 삭제에 실패했습니다!")
        return
    
    # ===== 2단계: 확장(명령어) 로드 =====
    print("\n" + "="*60)
    print("📦 2단계: 확장 모듈 로드 (commands.py)")
    print("="*60)
    
    await load_extensions()
    
    # ===== 3단계: 새로운 명령어 등록 =====
    print("\n" + "="*60)
    print("📝 3단계: 새로운 슬래시 명령어 등록")
    print("="*60)
    
    register_success = await register_new_commands()
    
    if not register_success:
        print("⚠️ 새로운 명령어 등록에 실패했습니다!")
    
    print("\n" + "="*60)
    print("✅ 명령어 완전 초기화 작업 완료!")
    print("="*60 + "\n")
    
    # ===== 4단계: 스케줄러 설정 =====
    # 스케줄러 설정
    try:
        from scheduler import setup_scheduler
        print("🔧 스케줄러 설정:")
        print(f"   - GUILD_ID: {config.GUILD_ID}")
        print(f"   - SUCCESS_CHANNEL_ID: {config.SUCCESS_CHANNEL_ID}")
        print(f"   - FAILURE_CHANNEL_ID: {config.FAILURE_CHANNEL_ID}")
        
        # 스케줄 시간 정보 추가
        auto_execution_day = getattr(config, 'AUTO_EXECUTION_DAY', 2)  # 기본값: 수요일(2)
        auto_execution_hour = getattr(config, 'AUTO_EXECUTION_HOUR', 3)  # 기본값: 03시
        auto_execution_minute = getattr(config, 'AUTO_EXECUTION_MINUTE', 24)  # 기본값: 24분
        
        # 요일 한글 변환
        day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        korean_day = day_names[auto_execution_day] if 0 <= auto_execution_day <= 6 else "알 수 없음"
        
        print(f"🕒 자동 실행 스케줄: 매주 {korean_day} {auto_execution_hour:02d}:{auto_execution_minute:02d}")
        
        setup_scheduler(bot)
        print("🚀 스케줄러 시작됨")
        print("✅ 스케줄러 설정 완료")
    except Exception as e:
        print(f"❌ 스케줄러 설정 실패: {e}")
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
            
            print("💾 콜사인 백업 스케줄러 설정:")
            print("   - 백업 디렉토리: callsign_backups/")
            print("   - 자동 백업: 매주 월요일 08:00")
            print("   - 보관 기간: 30일 (자동 백업만)")
            print("✅ 콜사인 백업 스케줄러 시작 완료")
            
        except ImportError as e:
            print(f"⚠️ 콜사인 백업 모듈을 로드할 수 없습니다: {e}")
            print("   callsign_backup.py 파일이 필요합니다.")
            bot.backup_manager = None
        except Exception as e:
            print(f"❌ 콜사인 백업 스케줄러 시작 실패: {e}")
            import traceback
            traceback.print_exc()
            bot.backup_manager = None
    else:
        print("ℹ️ 콜사인 기능이 비활성화되어 백업 스케줄러를 시작하지 않습니다.")
        bot.backup_manager = None
        
    print("🚀 봇이 완전히 준비되었습니다!")

@bot.event
async def on_message(message):
    """메시지 이벤트 처리 - &MF 명령어 감지 (특정 봇만)"""
    try:
        # &MF 명령어 확인
        if message.content.startswith('&MF'):
            # 허용된 봇 ID 목록
            ALLOWED_BOT_IDS = [557628352828014614, 1325579039888511056]

            # 허용된 봇이 아니면 무시
            if message.author.id not in ALLOWED_BOT_IDS:
                print(f"⚠️ &MF 명령어 무시: 허용되지 않은 사용자 {message.author.name} ({message.author.id})")
                return

            import re

            # &MF 제거하고 나머지 텍스트 추출
            content = message.content[3:].strip()

            print(f"🔍 &MF 명령어 감지! (봇: {message.author.name})")
            print(f"📝 원본 메시지: {message.content}")
            print(f"📝 처리된 내용: {content}")

            # 디스코드 ID 추출
            # 1. 유저 멘션 형태 (<@123456789> 또는 <@!123456789>)
            user_mention_match = re.search(r'<@!?(\d{15,20})>', content)
            if user_mention_match:
                discord_id = int(user_mention_match.group(1))
                print(f"✅ 유저 멘션에서 ID 추출: {discord_id}")
            else:
                # 2. 숫자만 있는 경우
                discord_id_match = re.search(r'(\d{15,20})', content)
                if not discord_id_match:
                    await message.channel.send("디스코드 ID를 찾을 수 없습니다. 사용법: `&MF 디스코드ID` 또는 `&MF @유저멘션`")
                    return
                discord_id = int(discord_id_match.group(1))
                print(f"✅ 숫자에서 ID 추출: {discord_id}")

            print(f"🎯 최종 Discord ID: {discord_id}")

            # database_manager 로드
            try:
                from database_manager import db_manager
            except ImportError:
                await message.channel.send("데이터베이스 모듈을 로드할 수 없습니다.")
                print("❌ database_manager 로드 실패")
                return

            # DB에서 유저 정보 조회
            user_info = db_manager.get_user_info(discord_id)

            if not user_info:
                await message.channel.send(f"디스코드 ID `{discord_id}`에 해당하는 사용자를 찾을 수 없습니다.")
                print(f"❌ DB에서 사용자 정보 없음: {discord_id}")
                return

            minecraft_name = user_info.get('current_minecraft_name')

            if not minecraft_name:
                await message.channel.send(f"사용자 `{discord_id}`의 마인크래프트 닉네임이 등록되지 않았습니다.")
                print(f"❌ 마인크래프트 닉네임 없음: {discord_id}")
                return

            # 국가 정보 조회
            nation_info = db_manager.get_current_nation(discord_id)

            if not nation_info or not nation_info.get('nation_name'):
                await message.channel.send(f"사용자 `{minecraft_name}`의 국가 정보를 찾을 수 없습니다.")
                print(f"❌ 국가 정보 없음: {discord_id} ({minecraft_name})")
                return

            nation_name = nation_info['nation_name']
            new_channel_name = f"{nation_name} 대사관"

            # 현재 채널 이름 변경
            try:
                old_name = message.channel.name
                await message.channel.edit(name=new_channel_name)
                await message.channel.send(
                    f"✅ 채널 이름이 변경되었습니다!\n"
                    f"사용자: `{minecraft_name}` (Discord ID: `{discord_id}`)\n"
                    f"국가: `{nation_name}`\n"
                    f"변경: `{old_name}` → `{new_channel_name}`"
                )
                print(f"✅ 채널 이름 변경 성공: {old_name} -> {new_channel_name}")
            except discord.Forbidden:
                await message.channel.send("❌ 채널 이름을 변경할 권한이 없습니다.")
                print(f"❌ 채널 이름 변경 권한 없음: {message.channel.name}")
            except Exception as e:
                await message.channel.send(f"❌ 채널 이름 변경 중 오류가 발생했습니다: {e}")
                print(f"❌ 채널 이름 변경 오류: {e}")
                import traceback
                traceback.print_exc()

    except Exception as e:
        print(f"❌ on_message 이벤트 처리 중 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 다른 명령어도 처리할 수 있도록 process_commands 호출
        await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    """새로운 멤버가 서버에 들어올 때 자동으로 대기열에 추가"""
    try:
        print(f"👋 새 멤버 입장 감지: {member.display_name} ({member.id})")

        # AUTO_ADD_NEW_MEMBERS 설정 확인 (기본값: True)
        auto_add_enabled = getattr(config, 'AUTO_ADD_NEW_MEMBERS', True)
        if not auto_add_enabled:
            print(f"⚠️ 자동 추가 비활성화 상태 - {member.display_name} 건너뜀")
            return

        # queue_manager 로드
        try:
            from queue_manager import queue_manager
        except ImportError as e:
            print(f"❌ queue_manager 로드 실패: {e}")
            return

        # 예외 사용자 확인 (두 가지 방법으로 확인)
        is_exception = False

        # 방법 1: exception_manager 사용
        if exception_manager:
            try:
                is_exception = exception_manager.is_exception(member.id)
                print(f"🔍 exception_manager 확인: {member.display_name} -> 예외 사용자: {is_exception}")
            except Exception as e:
                print(f"⚠️ exception_manager 확인 오류: {e}")

        # 방법 2: scheduler의 is_exception_user 함수 사용 (fallback)
        if not is_exception and is_exception_user:
            try:
                is_exception = is_exception_user(member.id)
                print(f"🔍 scheduler 확인: {member.display_name} -> 예외 사용자: {is_exception}")
            except Exception as e:
                print(f"⚠️ scheduler 예외 확인 오류: {e}")

        # 예외 사용자 처리
        if is_exception:
            print(f"🚫 예외 사용자이므로 대기열 추가 제외: {member.display_name} ({member.id})")

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
                        print(f"📨 예외 사용자 환영 메시지 전송됨: {member.display_name}")
            except Exception as e:
                print(f"⚠️ 예외 사용자 환영 메시지 전송 실패: {e}")
            return

        # 대기열에 추가
        try:
            # 이미 대기열에 있는지 확인
            if hasattr(queue_manager, 'is_user_in_queue') and queue_manager.is_user_in_queue(member.id):
                print(f"ℹ️ 이미 대기열에 있음: {member.display_name}")
            else:
                queue_manager.add_user(member.id)
                print(f"✅ 대기열에 추가됨: {member.display_name} (현재 대기열: {queue_manager.get_queue_size()}명)")

                # 성공 채널에 알림 (선택사항)
                try:
                    success_channel = bot.get_channel(config.SUCCESS_CHANNEL_ID)
                    if success_channel:
                        await success_channel.send(f"📝 새 멤버 대기열 추가: {member.mention} (대기: {queue_manager.get_queue_size()}명)")
                except Exception as e:
                    print(f"⚠️ 대기열 추가 알림 전송 실패: {e}")
        except Exception as e:
            print(f"❌ 대기열 추가 실패: {member.display_name} - {e}")
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
                    print(f"📨 환영 메시지 전송됨: {member.display_name}")
            else:
                print(f"ℹ️ 환영 채널이 설정되지 않음 (WELCOME_CHANNEL_ID)")
        except Exception as e:
            print(f"⚠️ 환영 메시지 전송 실패: {e}")

    except Exception as e:
        print(f"❌ on_member_join 이벤트 처리 중 오류: {e}")
        import traceback
        traceback.print_exc()

@bot.event
async def on_error(event, *args, **kwargs):
    """오류 발생 시 로그"""
    import traceback
    print(f"❌ 이벤트 오류 발생: {event}")
    traceback.print_exc()

# 확장 로드 함수
async def load_extensions():
    """확장 모듈 로드"""
    extensions = ["commands"]  # scheduler는 별도로 처리하므로 제외
    
    print("📦 확장 로드 시작...")
    for extension in extensions:
        try:
            # 이미 로드된 경우 언로드 후 다시 로드
            if extension in bot.extensions:
                await bot.unload_extension(extension)
                print(f"🔄 기존 확장 언로드됨: {extension}")
                
            await bot.load_extension(extension)
            print(f"✅ 확장 로드됨: {extension}")
        except Exception as e:
            print(f"❌ 확장 로드 실패 {extension}: {e}")
            import traceback
            traceback.print_exc()
    
    print("📦 확장 로드 완료!")

async def main():
    """메인 실행 함수"""
    # 토큰 검증
    if not config.DISCORD_TOKEN:
        print("❌ Discord 토큰이 설정되지 않았습니다!")
        print("💡 .env 파일에 DISCORD_TOKEN을 설정해주세요.")
        return
        
    # 봇 실행
    try:
        async with bot:
            await bot.start(config.DISCORD_TOKEN)
    except discord.LoginFailure:
        print("❌ Discord 토큰이 잘못되었습니다!")
        print("💡 Discord Developer Portal에서 새로운 토큰을 생성해주세요.")
    except Exception as e:
        print(f"❌ 봇 실행 중 오류: {e}")
        import traceback
        traceback.print_exc()

# 메인 실행
if __name__ == "__main__":
    try:
        print("🚀 Discord Bot 시작 중...")
        config.print_config_status()
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 봇이 안전하게 종료됩니다...")
    except Exception as e:
        print(f"❌ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)