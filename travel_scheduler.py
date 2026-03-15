# travel_scheduler.py - 여행 만료 알림 및 처리 스케줄러

import discord
from discord.ext import tasks
from datetime import datetime, date, timedelta
import asyncio

# 봇 인스턴스 참조
_bot_instance = None


async def restore_travel_roles(member: discord.Member, travel: dict, guild: discord.Guild):
    """여행 종료 시 original_nation 기반으로 역할 복원"""
    original_nation = travel.get("original_nation")
    if not original_nation:
        return

    try:
        from config import config

        success_role_id = config.SUCCESS_ROLE_ID
        success_role_out_id = config.SUCCESS_ROLE_ID_OUT
        base_nation = config.BASE_NATION
        base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)

        if not success_role_id:
            return

        # 원래 국가가 base nation인지 확인
        is_base = False
        if base_nation_uuid:
            try:
                from bulk_updater import bulk_data_manager
                nation_info = bulk_data_manager.get_nation_by_name(original_nation)
                if nation_info and nation_info.get('uuid') == base_nation_uuid:
                    is_base = True
                elif base_nation and original_nation.lower() == base_nation.lower():
                    is_base = True
            except Exception:
                if base_nation and original_nation.lower() == base_nation.lower():
                    is_base = True
        else:
            if base_nation and original_nation.lower() == base_nation.lower():
                is_base = True

        changes = []

        if is_base:
            # 국민 복원 → 조직원 추가, 외국인 제거
            success_role = guild.get_role(success_role_id)
            if success_role and success_role not in member.roles:
                await member.add_roles(success_role)
                changes.append(f"+{success_role.name}")

            if success_role_out_id:
                out_role = guild.get_role(success_role_out_id)
                if out_role and out_role in member.roles:
                    await member.remove_roles(out_role)
                    changes.append(f"-{out_role.name}")
        else:
            # 외국인 복원 → 외국인 추가, 조직원 제거
            if success_role_out_id:
                out_role = guild.get_role(success_role_out_id)
                if out_role and out_role not in member.roles:
                    await member.add_roles(out_role)
                    changes.append(f"+{out_role.name}")

            success_role = guild.get_role(success_role_id)
            if success_role and success_role in member.roles:
                await member.remove_roles(success_role)
                changes.append(f"-{success_role.name}")

        role_type = "국민(조직원)" if is_base else "외국인"
        print(f"[TRAVEL] 역할 복원: {member.display_name} → {role_type} [{', '.join(changes)}]")
    except Exception as e:
        print(f"[TRAVEL] 역할 복원 실패 ({member.display_name}): {e}")


def setup_travel_scheduler(bot):
    """여행 스케줄러 설정"""
    global _bot_instance
    _bot_instance = bot

    # 스케줄러 시작
    if not check_travel_status.is_running():
        check_travel_status.start()
        print("[OK] 여행 스케줄러 시작됨")


def stop_travel_scheduler():
    """여행 스케줄러 중지"""
    if check_travel_status.is_running():
        check_travel_status.cancel()
        print("[OK] 여행 스케줄러 중지됨")


@tasks.loop(hours=1)
async def check_travel_status():
    """매시간 여행 상태 체크"""
    global _bot_instance

    if not _bot_instance:
        return

    try:
        from travel_manager import travel_manager, travel_config_manager
        from database_manager import db_manager
        from config import config

        print("[TRAVEL] 여행 상태 체크 시작...")

        guild_id = getattr(config, 'GUILD_ID', None)
        if not guild_id:
            print("[TRAVEL] GUILD_ID가 설정되지 않음")
            return

        guild = _bot_instance.get_guild(guild_id)
        if not guild:
            print(f"[TRAVEL] 길드를 찾을 수 없음: {guild_id}")
            return

        log_channel_id = travel_config_manager.get_log_channel()
        log_channel = guild.get_channel(log_channel_id) if log_channel_id else None

        today = date.today()

        # 1. 오늘 시작하는 여행 활성화
        starting_today = travel_manager.get_travels_starting_today()
        for travel in starting_today:
            travel_manager.activate_travel(travel['id'])
            db_manager.set_user_traveling(travel['discord_id'], True)
            print(f"[TRAVEL] 여행 활성화: {travel['id']} (유저: {travel['discord_id']})")

            # 로그 채널에 알림
            if log_channel:
                embed = discord.Embed(
                    title="🛫 여행 시작",
                    description=f"<@{travel['discord_id']}>님의 여행이 시작되었습니다.",
                    color=0x00ff00
                )
                embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                embed.add_field(name="목적지", value=travel['destination_nation'], inline=True)
                embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=False)

                await log_channel.send(embed=embed)

            # 신청자 DM 발송
            dm_failed = False
            try:
                member = guild.get_member(travel['discord_id'])
                if member:
                    dm_embed = discord.Embed(
                        title="🛫 여행이 시작되었습니다!",
                        description=f"오늘부터 **{travel['destination_nation']}**로의 여행이 시작됩니다.\n"
                                   f"여행 기간 동안 역할/닉네임 변동이 적용되지 않습니다.",
                        color=0x00ff00
                    )
                    dm_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=False)
                    await member.send(embed=dm_embed)
            except discord.Forbidden:
                dm_failed = True

            # DM 실패 시 로그 채널에 알림
            if dm_failed and log_channel:
                manager_roles = travel_config_manager.get_manager_roles()
                role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                dm_fail_embed = discord.Embed(
                    title="⚠️ DM 전송 실패",
                    description=f"<@{travel['discord_id']}>님에게 여행 시작 알림을 전송할 수 없습니다.\n**DM이 차단되어 있습니다.**",
                    color=0xff9900
                )
                dm_fail_embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                dm_fail_embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                await log_channel.send(content=role_mentions if role_mentions else None, embed=dm_fail_embed)

        # 2. 만료된 여행 처리
        expired_travels = travel_manager.get_expired_travels()
        for travel in expired_travels:
            travel_manager.complete_travel(travel['id'])
            db_manager.set_user_traveling(travel['discord_id'], False)
            print(f"[TRAVEL] 여행 완료: {travel['id']} (유저: {travel['discord_id']})")

            # 원래 국가 기반 역할 복원
            try:
                member = guild.get_member(travel['discord_id'])
                if member and travel.get('original_nation'):
                    await restore_travel_roles(member, travel, guild)
            except Exception as e:
                print(f"[TRAVEL] 역할 복원 오류: {e}")

            # 로그 채널에 알림 (관리 역할 멘션)
            if log_channel:
                # 관리 역할 멘션 생성
                manager_roles = travel_config_manager.get_manager_roles()
                role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles])

                embed = discord.Embed(
                    title="🛬 여행 종료",
                    description=f"<@{travel['discord_id']}>님의 여행이 종료되었습니다.\n"
                               f"이제부터 역할/닉네임 변동이 정상적으로 적용됩니다.",
                    color=0xe74c3c
                )
                embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                embed.add_field(name="목적지", value=travel['destination_nation'], inline=True)
                embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=False)
                if travel.get('original_nation'):
                    embed.add_field(name="원래 국가", value=travel['original_nation'], inline=True)

                content = role_mentions if role_mentions else None
                await log_channel.send(content=content, embed=embed)

            # 신청자 DM 발송
            dm_failed = False
            try:
                member = guild.get_member(travel['discord_id'])
                if member:
                    dm_embed = discord.Embed(
                        title="🛬 여행이 종료되었습니다!",
                        description=f"**{travel['destination_nation']}**로의 여행이 종료되었습니다.\n"
                                   f"이제부터 역할/닉네임 변동이 정상적으로 적용됩니다.",
                        color=0xe74c3c
                    )
                    dm_embed.add_field(name="기간", value=f"{travel['start_date']} ~ {travel['end_date']}", inline=False)
                    await member.send(embed=dm_embed)
            except discord.Forbidden:
                dm_failed = True

            # DM 실패 시 로그 채널에 알림
            if dm_failed and log_channel:
                manager_roles = travel_config_manager.get_manager_roles()
                role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                dm_fail_embed = discord.Embed(
                    title="⚠️ DM 전송 실패",
                    description=f"<@{travel['discord_id']}>님에게 여행 종료 알림을 전송할 수 없습니다.\n**DM이 차단되어 있습니다.**",
                    color=0xff9900
                )
                dm_fail_embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                dm_fail_embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                await log_channel.send(content=role_mentions if role_mentions else None, embed=dm_fail_embed)

        # 3. 1일 전 알림 (아직 알림 안 보낸 여행)
        ending_soon = travel_manager.get_travels_ending_soon(days=1)
        for travel in ending_soon:
            if travel.get('notified_1day'):
                continue

            days_until = travel.get('days_until_end', 0)

            # 정확히 1일 남은 경우만
            if days_until == 1:
                travel_manager.mark_notified_1day(travel['id'])
                print(f"[TRAVEL] 1일 전 알림: {travel['id']}")

                # 로그 채널에 알림
                if log_channel:
                    embed = discord.Embed(
                        title="⏰ 여행 종료 1일 전",
                        description=f"<@{travel['discord_id']}>님의 여행이 **내일** 종료됩니다.",
                        color=0xf39c12
                    )
                    embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                    embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                    embed.add_field(name="목적지", value=travel['destination_nation'], inline=True)
                    embed.add_field(name="종료일", value=travel['end_date'], inline=True)

                    await log_channel.send(embed=embed)

                # 신청자 DM 발송
                dm_failed = False
                try:
                    member = guild.get_member(travel['discord_id'])
                    if member:
                        dm_embed = discord.Embed(
                            title="⏰ 여행 종료 1일 전 알림",
                            description=f"**{travel['destination_nation']}**로의 여행이 **내일** 종료됩니다.\n"
                                       f"종료 후에는 역할/닉네임 변동이 정상적으로 적용됩니다.",
                            color=0xf39c12
                        )
                        dm_embed.add_field(name="종료일", value=travel['end_date'], inline=False)
                        await member.send(embed=dm_embed)
                except discord.Forbidden:
                    dm_failed = True

                # DM 실패 시 로그 채널에 알림
                if dm_failed and log_channel:
                    manager_roles = travel_config_manager.get_manager_roles()
                    role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                    dm_fail_embed = discord.Embed(
                        title="⚠️ DM 전송 실패",
                        description=f"<@{travel['discord_id']}>님에게 여행 1일 전 알림을 전송할 수 없습니다.\n**DM이 차단되어 있습니다.**",
                        color=0xff9900
                    )
                    dm_fail_embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                    dm_fail_embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                    await log_channel.send(content=role_mentions if role_mentions else None, embed=dm_fail_embed)

        # 4. 당일 알림 (아직 종료 알림 안 보낸 여행 중 당일인 것)
        for travel in ending_soon:
            if travel.get('notified_end'):
                continue

            days_until = travel.get('days_until_end', 0)

            # 오늘 종료인 경우
            if days_until == 0:
                travel_manager.mark_notified_end(travel['id'])
                print(f"[TRAVEL] 당일 알림: {travel['id']}")

                # 로그 채널에 알림 (관리 역할 멘션)
                if log_channel:
                    manager_roles = travel_config_manager.get_manager_roles()
                    role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles])

                    embed = discord.Embed(
                        title="🔔 여행 종료일",
                        description=f"<@{travel['discord_id']}>님의 여행이 **오늘** 종료됩니다.",
                        color=0xe74c3c
                    )
                    embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                    embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                    embed.add_field(name="목적지", value=travel['destination_nation'], inline=True)

                    content = role_mentions if role_mentions else None
                    await log_channel.send(content=content, embed=embed)

                # 신청자 DM 발송
                dm_failed = False
                try:
                    member = guild.get_member(travel['discord_id'])
                    if member:
                        dm_embed = discord.Embed(
                            title="🔔 여행 종료일 알림",
                            description=f"**{travel['destination_nation']}**로의 여행이 **오늘** 종료됩니다.\n"
                                       f"자정 이후부터 역할/닉네임 변동이 정상적으로 적용됩니다.",
                            color=0xe74c3c
                        )
                        await member.send(embed=dm_embed)
                except discord.Forbidden:
                    dm_failed = True

                # DM 실패 시 로그 채널에 알림
                if dm_failed and log_channel:
                    manager_roles = travel_config_manager.get_manager_roles()
                    role_mentions = " ".join([f"<@&{role_id}>" for role_id in manager_roles]) if manager_roles else ""

                    dm_fail_embed = discord.Embed(
                        title="⚠️ DM 전송 실패",
                        description=f"<@{travel['discord_id']}>님에게 여행 당일 알림을 전송할 수 없습니다.\n**DM이 차단되어 있습니다.**",
                        color=0xff9900
                    )
                    dm_fail_embed.add_field(name="신청 ID", value=f"`{travel['id']}`", inline=True)
                    dm_fail_embed.add_field(name="마크 닉네임", value=travel['minecraft_name'], inline=True)
                    await log_channel.send(content=role_mentions if role_mentions else None, embed=dm_fail_embed)

        print("[TRAVEL] 여행 상태 체크 완료")

    except Exception as e:
        import traceback
        print(f"[ERROR] 여행 스케줄러 오류: {e}")
        traceback.print_exc()


@check_travel_status.before_loop
async def before_check_travel_status():
    """스케줄러 시작 전 봇 준비 대기"""
    global _bot_instance
    if _bot_instance:
        await _bot_instance.wait_until_ready()


def is_user_traveling(discord_id: int) -> bool:
    """
    사용자가 현재 여행 중인지 확인

    Args:
        discord_id: 디스코드 사용자 ID

    Returns:
        여행 중 여부
    """
    try:
        from travel_manager import travel_manager
        return travel_manager.is_traveling(discord_id)
    except Exception as e:
        print(f"[ERROR] 여행 상태 확인 실패: {e}")
        return False


def get_user_travel_destination(discord_id: int) -> str:
    """
    사용자의 여행 목적지 조회

    Args:
        discord_id: 디스코드 사용자 ID

    Returns:
        여행 목적지 국가 (여행 중이 아니면 None)
    """
    try:
        from travel_manager import travel_manager
        return travel_manager.get_travel_destination(discord_id)
    except Exception as e:
        print(f"[ERROR] 여행 목적지 조회 실패: {e}")
        return None


async def run_travel_check_now():
    """수동으로 여행 상태 체크 실행"""
    await check_travel_status()
