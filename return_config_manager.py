# return_config_manager.py - 잠수/복귀 시스템 설정 관리

import json
import os
from typing import Optional, List, Dict
from datetime import datetime

INACTIVE_DAYS = 60  # 잠수 기준 일수


class ReturnConfigManager:
    """잠수/복귀 시스템 설정을 관리하는 클래스"""

    def __init__(self, config_file: str = "data/return_config.json"):
        os.makedirs("data", exist_ok=True)
        self.config_file = config_file
        self.config = self._load_config()
        # 기존 설정 파일에 누락된 키가 있으면 기본값으로 채움
        changed = False
        for key, val in self._default_config().items():
            if key not in self.config:
                self.config[key] = val
                changed = True
        if changed:
            self._save()
        print("[OK] ReturnConfigManager 초기화 완료")

    def _load_config(self) -> dict:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] 복귀 설정 파일 로드 실패: {e}")
        return self._default_config()

    def _default_config(self) -> dict:
        return {
            "inactive_role_id": None,        # 잠수 역할
            "return_role_id": None,          # 복귀 신청 중 역할 (티켓 오픈 시)
            "return_complete_role_id": None, # 복귀 완료 시 지급 역할
            "return_chat_role_id": None,     # 복귀채팅 접근 역할 (잠수 유저에게 자동 부여)
            "inactive_extra_roles": [],      # 잠수 시 추가 지급 역할 ID 목록
            "daily_channel_id": 1481318415703605279,  # 일일 복귀 안내 핑 채널
            "daily_ping_role_id": None,      # 일일 핑 대상 역할
            "ticket_source_channel_id": None,  # $ticket 명령어 처리 채널
            "ticket_category_id": None,      # 티켓 생성 카테고리
            "manager_role_id": None,         # 복귀 관리자 역할 (비관리자에게 권한 부여, 복귀채팅역할 겸용)
            "dm_sent_users": {},             # {discord_id_str: iso_timestamp} DM 보낸 유저
            "exceptions": [],                # 잠수 예외 유저 목록
            "list_message": None             # 리스트 메시지 {channel_id, message_id}
        }

    def _save(self) -> bool:
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] 복귀 설정 저장 실패: {e}")
            return False

    # ===== 잠수 역할 =====

    def set_inactive_role(self, role_id: int) -> bool:
        self.config["inactive_role_id"] = role_id
        return self._save()

    def get_inactive_role(self) -> Optional[int]:
        return self.config.get("inactive_role_id")

    def clear_inactive_role(self) -> bool:
        self.config["inactive_role_id"] = None
        return self._save()

    # ===== 복귀 역할 (신청 중) =====

    def set_return_role(self, role_id: int) -> bool:
        self.config["return_role_id"] = role_id
        return self._save()

    def get_return_role(self) -> Optional[int]:
        return self.config.get("return_role_id")

    # ===== 복귀 완료 역할 =====

    def set_return_complete_role(self, role_id: int) -> bool:
        self.config["return_complete_role_id"] = role_id
        return self._save()

    def get_return_complete_role(self) -> Optional[int]:
        return self.config.get("return_complete_role_id")

    # ===== 복귀채팅 역할 =====

    def set_return_chat_role(self, role_id: int) -> bool:
        self.config["return_chat_role_id"] = role_id
        return self._save()

    def get_return_chat_role(self) -> Optional[int]:
        return self.config.get("return_chat_role_id")

    # ===== 채널 설정 =====

    def set_daily_channel(self, channel_id: int) -> bool:
        self.config["daily_channel_id"] = channel_id
        return self._save()

    def get_daily_channel(self) -> Optional[int]:
        return self.config.get("daily_channel_id")

    def set_daily_ping_role(self, role_id: int) -> bool:
        self.config["daily_ping_role_id"] = role_id
        return self._save()

    def get_daily_ping_role(self) -> Optional[int]:
        return self.config.get("daily_ping_role_id")

    def set_ticket_source_channel(self, channel_id: int) -> bool:
        self.config["ticket_source_channel_id"] = channel_id
        return self._save()

    def get_ticket_source_channel(self) -> Optional[int]:
        return self.config.get("ticket_source_channel_id")

    def set_ticket_category(self, category_id: int) -> bool:
        self.config["ticket_category_id"] = category_id
        return self._save()

    def get_ticket_category(self) -> Optional[int]:
        return self.config.get("ticket_category_id")

    def set_manager_role(self, role_id: int) -> bool:
        self.config["manager_role_id"] = role_id
        return self._save()

    def get_manager_role(self) -> Optional[int]:
        return self.config.get("manager_role_id")

    # ===== 리스트 메시지 =====

    def set_list_message(self, channel_id: int, message_id: int) -> bool:
        self.config["list_message"] = {"channel_id": channel_id, "message_id": message_id}
        return self._save()

    def get_list_message(self) -> Optional[dict]:
        return self.config.get("list_message")

    def clear_list_message(self) -> bool:
        self.config["list_message"] = None
        return self._save()

    # ===== 잠수 추가 역할 =====

    def set_extra_inactive_roles(self, role_ids: List[int]) -> bool:
        self.config["inactive_extra_roles"] = role_ids
        return self._save()

    def get_extra_inactive_roles(self) -> List[int]:
        return self.config.get("inactive_extra_roles", [])

    # ===== DM 발송 기록 =====
    # dm_sent_users: {discord_id_str: last_notified_days}
    # 최초 60일, 이후 30일마다 DM 발송 (60 → 90 → 120 → ...)

    def mark_dm_sent(self, discord_id: int, days_threshold: int) -> bool:
        dm_sent = self.config.get("dm_sent_users", {})
        dm_sent[str(discord_id)] = days_threshold
        self.config["dm_sent_users"] = dm_sent
        return self._save()

    def should_send_dm(self, discord_id: int, current_days: int) -> bool:
        """현재 미접속 일수 기준으로 DM을 보내야 하는지 확인"""
        dm_sent = self.config.get("dm_sent_users", {})
        last_notified = dm_sent.get(str(discord_id))
        if last_notified is None:
            # 최초: 60일 이상이면 발송
            return current_days >= INACTIVE_DAYS
        # 기존 데이터가 문자열(이전 형식)이면 60일로 간주
        if isinstance(last_notified, str):
            last_notified = INACTIVE_DAYS
        # 마지막 알림 기준 + 30일 이상이면 재발송
        return current_days >= last_notified + 30

    def get_next_dm_threshold(self, discord_id: int) -> int:
        """다음 DM 발송 기준 일수 반환"""
        dm_sent = self.config.get("dm_sent_users", {})
        last_notified = dm_sent.get(str(discord_id))
        if last_notified is None:
            return INACTIVE_DAYS
        if isinstance(last_notified, str):
            return INACTIVE_DAYS + 30
        return last_notified + 30

    def has_dm_sent(self, discord_id: int) -> bool:
        return str(discord_id) in self.config.get("dm_sent_users", {})

    def clear_dm_sent(self, discord_id: int) -> bool:
        dm_sent = self.config.get("dm_sent_users", {})
        if str(discord_id) in dm_sent:
            del dm_sent[str(discord_id)]
            self.config["dm_sent_users"] = dm_sent
            return self._save()
        return True

    # ===== 예외 유저 =====

    def add_exception(self, discord_id: int) -> bool:
        exceptions = self.config.get("exceptions", [])
        if discord_id not in exceptions:
            exceptions.append(discord_id)
            self.config["exceptions"] = exceptions
            return self._save()
        return True

    def remove_exception(self, discord_id: int) -> bool:
        exceptions = self.config.get("exceptions", [])
        if discord_id in exceptions:
            exceptions.remove(discord_id)
            self.config["exceptions"] = exceptions
            return self._save()
        return True

    def get_exceptions(self) -> List[int]:
        return self.config.get("exceptions", [])

    def is_exception(self, discord_id: int) -> bool:
        return discord_id in self.config.get("exceptions", [])

    # ===== 설정 조회 =====

    def get_all_settings(self) -> dict:
        """dm_sent_users 제외한 모든 설정 반환"""
        return {k: v for k, v in self.config.items() if k != "dm_sent_users"}

    def is_configured(self) -> bool:
        """최소 설정 여부 확인 (잠수 역할이 설정되어 있어야 함)"""
        return self.config.get("inactive_role_id") is not None


# 전역 인스턴스
return_config_manager = ReturnConfigManager()
print("[OK] ReturnConfigManager 전역 인스턴스 생성됨")
