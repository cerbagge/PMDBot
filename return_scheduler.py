# 잠수/복귀 시스템 스케줄러
# 기능:
#   1. 매일 03:00 - 국민 중 60일 이상 미접속자 잠수 역할 부여 (DM은 별도)
#   2. 매일 16:00 - 잠수 역할 보유자에게 단계별 DM 전송 (60일 → 90일 → 120일 → 30일마다)
#   3. 매일 09:00 - 복귀채팅 채널에 핑 + 복귀 절차 안내 메시지 전송

import discord
from discord.ext import tasks
from datetime import datetime, timedelta

INACTIVE_DAYS = 60  # 잠수 기준 일수

_bot_instance = None


def setup_return_scheduler(bot):
    """복귀 스케줄러 설정 및 시작"""
    global _bot_instance
    _bot_instance = bot

    if not check_inactive_users.is_running():
        check_inactive_users.start()
        print("[OK] 잠수 체크 스케줄러 시작됨 (매일 03:00)")

    if not send_inactive_dms.is_running():
        send_inactive_dms.start()
        print("[OK] 잠수 DM 스케줄러 시작됨 (매일 16:00)")

    if not send_daily_return_ping.is_running():
        send_daily_return_ping.start()
        print("[OK] 일일 복귀 핑 스케줄러 시작됨 (매일 03:00)")


def stop_return_scheduler():
    """복귀 스케줄러 중지"""
    if check_inactive_users.is_running():
        check_inactive_users.cancel()
    if send_inactive_dms.is_running():
        send_inactive_dms.cancel()
    if send_daily_return_ping.is_running():  # noqa: 비활성화됨, 혹시 수동 시작된 경우 대비
        send_daily_return_ping.cancel()
    print("[OK] 복귀 스케줄러 중지됨")


@tasks.loop(hours=24)
async def check_inactive_users():
    """매일 03:00 - 60일 이상 미접속 국민을 찾아 잠수 역할 부여"""
    global _bot_instance
    if not _bot_instance:
        return

    try:
        from config import config
        from return_config_manager import return_config_manager
        from database_manager import db_manager

        guild = _bot_instance.get_guild(config.GUILD_ID)
        if not guild:
            return

        inactive_role_id = return_config_manager.get_inactive_role()
        if not inactive_role_id:
            print("[INACTIVE] 잠수 역할이 설정되지 않아 체크 건너뜀")
            return

        inactive_role = guild.get_role(inactive_role_id)
        if not inactive_role:
            print(f"[INACTIVE] 잠수 역할을 찾을 수 없음 (ID: {inactive_role_id})")
            return

        # 복귀채팅 역할 (잠수 시 함께 부여)
        return_chat_role_id = return_config_manager.get_return_chat_role()
        return_chat_role = guild.get_role(return_chat_role_id) if return_chat_role_id else None

        # 추가 역할
        extra_role_ids = return_config_manager.get_extra_inactive_roles()
        extra_roles = [r for rid in extra_role_ids if (r := guild.get_role(rid))]

        # 국민 역할 (SUCCESS_ROLE_ID)
        success_role = guild.get_role(config.SUCCESS_ROLE_ID) if config.SUCCESS_ROLE_ID else None

        # bulk 데이터
        bulk_data_manager = getattr(_bot_instance, 'bulk_data_manager', None)

        now = datetime.now()
        processed = 0

        print(f"[INACTIVE] 잠수 체크 시작 (기준: {INACTIVE_DAYS}일)")

        for member in guild.members:
            if member.bot:
                continue

            # 국민인지 확인
            if success_role and success_role not in member.roles:
                continue

            # 예외 유저 확인
            if return_config_manager.is_exception(member.id):
                continue

            # 이미 잠수 역할이 있으면 스킵
            if inactive_role in member.roles:
                continue

            # DB에서 마인크래프트 계정 확인
            user_info = db_manager.get_user_info(member.id)
            if not user_info or not user_info.get('current_minecraft_name'):
                continue

            mc_name = user_info.get('current_minecraft_name')

            # bulk_data에서 lastOnline 확인
            last_online_ts = None
            if bulk_data_manager:
                resident = bulk_data_manager.get_resident_by_name(mc_name)
                if resident:
                    last_online_ts = resident.get('lastOnline')

            if not last_online_ts:
                continue

            # 경과 일수 계산
            try:
                last_online_dt = datetime.fromtimestamp(last_online_ts / 1000)
                days_diff = (now - last_online_dt).days
            except Exception:
                continue

            if days_diff < INACTIVE_DAYS:
                continue

            # 잠수 처리: 역할 부여 (DM은 16:00 별도 태스크에서 발송)
            roles_to_add = [inactive_role] + extra_roles
            if return_chat_role:
                roles_to_add.append(return_chat_role)

            try:
                await member.add_roles(*roles_to_add, reason=f"60일 이상 미접속 ({days_diff}일)")
                processed += 1
                print(f"[INACTIVE] 잠수 처리: {member.display_name} ({days_diff}일 미접속)")
            except discord.Forbidden:
                print(f"[WARN] 역할 부여 권한 없음: {member.display_name}")
            except Exception as e:
                print(f"[ERROR] 역할 부여 실패: {member.display_name} - {e}")

        print(f"[INACTIVE] 잠수 체크 완료: {processed}명 처리됨")

    except Exception as e:
        import traceback
        print(f"[ERROR] 잠수 체크 실패: {e}")
        traceback.print_exc()


@tasks.loop(hours=24)
async def send_inactive_dms():
    """매일 16:00 - 잠수 역할 보유자에게 단계별 DM 전송 (60일 → 90일 → 120일 → ...)"""
    global _bot_instance
    if not _bot_instance:
        return

    try:
        from config import config
        from return_config_manager import return_config_manager
        from database_manager import db_manager

        guild = _bot_instance.get_guild(config.GUILD_ID)
        if not guild:
            return

        inactive_role_id = return_config_manager.get_inactive_role()
        if not inactive_role_id:
            return

        inactive_role = guild.get_role(inactive_role_id)
        if not inactive_role:
            return

        bulk_data_manager = getattr(_bot_instance, 'bulk_data_manager', None)
        now = datetime.now()
        dm_sent_count = 0

        print("[INACTIVE_DM] 잠수 DM 발송 시작")

        for member in guild.members:
            if member.bot:
                continue

            # 잠수 역할이 없으면 스킵
            if inactive_role not in member.roles:
                continue

            # 부계정이면 DM 스킵 (본계정에게만 DM 전송)
            if db_manager.get_main_account(member.id):
                continue

            # 경과 일수 계산
            days_diff = 0
            user_info = db_manager.get_user_info(member.id)
            if user_info and user_info.get('current_minecraft_name') and bulk_data_manager:
                resident = bulk_data_manager.get_resident_by_name(user_info['current_minecraft_name'])
                if resident and resident.get('lastOnline'):
                    try:
                        last_dt = datetime.fromtimestamp(resident['lastOnline'] / 1000)
                        days_diff = (now - last_dt).days
                    except Exception:
                        pass

            if days_diff < INACTIVE_DAYS:
                continue

            # 이 유저에게 DM을 보내야 하는지 확인 (60 → 90 → 120 → ...)
            if not return_config_manager.should_send_dm(member.id, days_diff):
                continue

            next_threshold = return_config_manager.get_next_dm_threshold(member.id)

            # DM 전송
            try:
                embed = discord.Embed(
                    title="⚠️ 장기 미접속 알림",
                    description=(
                        f"안녕하세요, **{member.display_name}**님!\n\n"
                        f"마인크래프트 서버에 **{days_diff}일** 동안 접속하지 않으셨습니다.\n"
                        f"이에 따라 잠수 역할이 부여되었습니다.\n\n"
                        f"복귀를 원하시면 서버의 **복귀 채널**을 확인해주세요."
                    ),
                    color=0xff6600
                )
                embed.set_footer(text="PlanetEarth 서버")
                await member.send(embed=embed)
                return_config_manager.mark_dm_sent(member.id, next_threshold)
                dm_sent_count += 1
                print(f"[INACTIVE_DM] DM 전송: {member.display_name} ({days_diff}일, 기준: {next_threshold}일)")
            except discord.Forbidden:
                print(f"[WARN] DM 차단됨: {member.display_name}")
                # DM 차단이어도 발송 기록 남김 (무한 재시도 방지)
                return_config_manager.mark_dm_sent(member.id, next_threshold)
            except Exception as e:
                print(f"[WARN] DM 전송 실패: {member.display_name} - {e}")

        print(f"[INACTIVE_DM] DM 발송 완료: {dm_sent_count}명")

    except Exception as e:
        import traceback
        print(f"[ERROR] 잠수 DM 발송 실패: {e}")
        traceback.print_exc()


@tasks.loop(hours=24)
async def send_daily_return_ping():
    """매일 13:00 - 복귀채팅 채널에 핑 + 안내 메시지 전송"""
    global _bot_instance
    if not _bot_instance:
        return

    try:
        from return_config_manager import return_config_manager

        channel_id = return_config_manager.get_daily_channel()
        if not channel_id:
            return

        channel = _bot_instance.get_channel(channel_id)
        if not channel:
            return

        ping_role_id = return_config_manager.get_daily_ping_role()
        ping_text = f"<@&{ping_role_id}>" if ping_role_id else None

        if not ping_text:
            return

        await channel.send(content=ping_text)
        print(f"[RETURN] 일일 복귀 핑 전송 완료: 채널 {channel.name}")

    except Exception as e:
        import traceback
        print(f"[ERROR] 일일 복귀 핑 전송 실패: {e}")
        traceback.print_exc()


@check_inactive_users.before_loop
async def before_inactive_check():
    """03:00에 시작하도록 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    wait_seconds = (target - now).total_seconds()
    print(f"[INACTIVE] 첫 실행까지 {wait_seconds/3600:.1f}시간 대기 (목표: {target.strftime('%H:%M')})")
    import asyncio
    await asyncio.sleep(wait_seconds)


@send_inactive_dms.before_loop
async def before_inactive_dms():
    """16:00에 시작하도록 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    wait_seconds = (target - now).total_seconds()
    print(f"[INACTIVE_DM] 첫 실행까지 {wait_seconds/3600:.1f}시간 대기 (목표: {target.strftime('%H:%M')})")
    import asyncio
    await asyncio.sleep(wait_seconds)


@send_daily_return_ping.before_loop
async def before_daily_ping():
    """03:00에 시작하도록 대기"""
    if _bot_instance:
        await _bot_instance.wait_until_ready()
    now = datetime.now()
    target = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    wait_seconds = (target - now).total_seconds()
    print(f"[RETURN] 일일 핑 첫 실행까지 {wait_seconds/3600:.1f}시간 대기 (목표: {target.strftime('%H:%M')})")
    import asyncio
    await asyncio.sleep(wait_seconds)
