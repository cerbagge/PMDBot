# announcement_scheduler.py - 공지 예약 관리 및 스케줄러

import json
import os
import time
from discord.ext import tasks
from datetime import datetime
from typing import Optional, List

SCHEDULE_FILE = "data/announcement_schedule.json"

_bot_instance = None


class AnnouncementScheduleManager:
    """공지 예약을 JSON 파일로 관리하는 클래스"""

    def __init__(self, schedule_file: str = SCHEDULE_FILE):
        self.schedule_file = schedule_file
        self.schedules = self._load_schedules()

    def _load_schedules(self) -> list:
        """스케줄 파일 로드"""
        if os.path.exists(self.schedule_file):
            try:
                with open(self.schedule_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("scheduled", [])
            except Exception as e:
                print(f"[ERROR] 공지 스케줄 파일 로드 실패: {e}")
                return []
        return []

    def _save_schedules(self) -> bool:
        """스케줄 파일 저장"""
        try:
            os.makedirs(os.path.dirname(self.schedule_file), exist_ok=True)
            with open(self.schedule_file, 'w', encoding='utf-8') as f:
                json.dump({"scheduled": self.schedules}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] 공지 스케줄 파일 저장 실패: {e}")
            return False

    def add_schedule(self, channel_id: int, guild_id: int, text: str,
                     silent: bool, scheduled_time: str, created_by: int) -> Optional[dict]:
        """예약 추가"""
        schedule_id = f"ann_{int(time.time())}"
        entry = {
            "id": schedule_id,
            "channel_id": channel_id,
            "guild_id": guild_id,
            "text": text,
            "silent": silent,
            "scheduled_time": scheduled_time,
            "created_by": created_by,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.schedules.append(entry)
        if self._save_schedules():
            print(f"[ANNOUNCE] 공지 예약 추가: {schedule_id} ({scheduled_time})")
            return entry
        else:
            self.schedules.pop()
            return None

    def remove_schedule(self, schedule_id: str) -> bool:
        """예약 삭제"""
        for i, s in enumerate(self.schedules):
            if s["id"] == schedule_id:
                removed = self.schedules.pop(i)
                if self._save_schedules():
                    print(f"[ANNOUNCE] 공지 예약 삭제: {schedule_id}")
                    return True
                else:
                    self.schedules.insert(i, removed)
                    return False
        return False

    def get_due_schedules(self) -> List[dict]:
        """현재 시간 이전 또는 같은 시간의 예약 반환"""
        now = datetime.now()
        due = []
        for s in self.schedules:
            try:
                scheduled_dt = datetime.strptime(s["scheduled_time"], "%Y-%m-%d %H:%M")
                if scheduled_dt <= now:
                    due.append(s)
            except ValueError:
                print(f"[WARN] 잘못된 예약 시간 형식: {s.get('scheduled_time')}")
        return due

    def get_all_schedules(self) -> List[dict]:
        """모든 예약 반환"""
        return list(self.schedules)

    def get_schedule_count(self) -> int:
        """예약 개수 반환"""
        return len(self.schedules)


# 전역 인스턴스
announcement_schedule_manager = AnnouncementScheduleManager()


# ===== 백그라운드 스케줄러 =====

def setup_announcement_scheduler(bot):
    """공지 스케줄러 설정 및 시작"""
    global _bot_instance
    _bot_instance = bot

    if not check_announcement_schedule.is_running():
        check_announcement_schedule.start()
        print("[OK] 공지 스케줄러 시작됨")


def stop_announcement_scheduler():
    """공지 스케줄러 중지"""
    if check_announcement_schedule.is_running():
        check_announcement_schedule.cancel()
        print("[OK] 공지 스케줄러 중지됨")


@tasks.loop(seconds=30)
async def check_announcement_schedule():
    """30초마다 예약된 공지 확인 및 전송"""
    global _bot_instance

    if not _bot_instance:
        return

    try:
        due_schedules = announcement_schedule_manager.get_due_schedules()

        for schedule in due_schedules:
            try:
                channel = _bot_instance.get_channel(schedule["channel_id"])
                if not channel:
                    print(f"[ANNOUNCE] 채널을 찾을 수 없음: {schedule['channel_id']}")
                    announcement_schedule_manager.remove_schedule(schedule["id"])
                    continue

                # 공지 전송
                await channel.send(
                    content=schedule["text"],
                    silent=schedule.get("silent", False)
                )

                print(f"[ANNOUNCE] 공지 전송 완료: {schedule['id']} -> #{channel.name}")

                # 전송 완료된 예약 삭제
                announcement_schedule_manager.remove_schedule(schedule["id"])

            except Exception as e:
                print(f"[ANNOUNCE] 공지 전송 실패 ({schedule['id']}): {e}")
                # 실패한 예약도 삭제 (무한 재시도 방지)
                announcement_schedule_manager.remove_schedule(schedule["id"])

    except Exception as e:
        print(f"[ANNOUNCE] 스케줄 확인 중 오류: {e}")
