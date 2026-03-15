# newbie_config_manager.py - 뉴비 알림 설정 관리

import json
import os
from typing import Optional, List, Dict

class NewbieConfigManager:
    """뉴비 알림 채널 및 역할 설정을 관리하는 클래스"""

    def __init__(self, config_file: str = "newbie_config.json"):
        """
        초기화

        Args:
            config_file: 설정 파일 경로
        """
        self.config_file = config_file
        self.config = self._load_config()
        print(f"[OK] NewbieConfigManager 초기화 완료")

    def _load_config(self) -> dict:
        """설정 파일 로드"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] 뉴비 설정 파일 로드 실패: {e}")
                return self._get_default_config()
        return self._get_default_config()

    def _get_default_config(self) -> dict:
        """기본 설정 반환"""
        return {
            "notification_channel_id": None,
            "ping_role_ids": [],
            "newbie_role_id": None,
            "list_message_id": None,
            "list_channel_id": None
        }

    def _save_config(self) -> bool:
        """설정 파일 저장"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] 뉴비 설정 파일 저장 실패: {e}")
            return False

    # ===== 채널 설정 =====

    def set_notification_channel(self, channel_id: int) -> bool:
        """
        뉴비 알림 채널 설정

        Args:
            channel_id: 채널 ID

        Returns:
            성공 여부
        """
        self.config["notification_channel_id"] = channel_id
        success = self._save_config()
        if success:
            print(f"[OK] 뉴비 알림 채널 설정: {channel_id}")
        return success

    def get_notification_channel(self) -> Optional[int]:
        """
        뉴비 알림 채널 ID 조회

        Returns:
            채널 ID (없으면 None)
        """
        return self.config.get("notification_channel_id")

    def clear_notification_channel(self) -> bool:
        """
        뉴비 알림 채널 설정 해제

        Returns:
            성공 여부
        """
        self.config["notification_channel_id"] = None
        success = self._save_config()
        if success:
            print(f"[OK] 뉴비 알림 채널 설정 해제됨")
        return success

    # ===== 뉴비 역할 설정 =====

    def set_newbie_role(self, role_id: int) -> bool:
        """
        뉴비 역할 설정

        Args:
            role_id: 역할 ID

        Returns:
            성공 여부
        """
        self.config["newbie_role_id"] = role_id
        success = self._save_config()
        if success:
            print(f"[OK] 뉴비 역할 설정: {role_id}")
        return success

    def get_newbie_role(self) -> Optional[int]:
        """
        뉴비 역할 ID 조회

        Returns:
            역할 ID (없으면 None)
        """
        return self.config.get("newbie_role_id")

    def clear_newbie_role(self) -> bool:
        """
        뉴비 역할 설정 해제

        Returns:
            성공 여부
        """
        self.config["newbie_role_id"] = None
        success = self._save_config()
        if success:
            print(f"[OK] 뉴비 역할 설정 해제됨")
        return success

    # ===== 핑 역할 설정 =====

    def add_ping_role(self, role_id: int) -> bool:
        """
        핑할 역할 추가

        Args:
            role_id: 역할 ID

        Returns:
            성공 여부
        """
        if role_id not in self.config["ping_role_ids"]:
            self.config["ping_role_ids"].append(role_id)
            success = self._save_config()
            if success:
                print(f"[OK] 뉴비 알림 핑 역할 추가: {role_id}")
            return success
        return True  # 이미 있으면 성공으로 처리

    def remove_ping_role(self, role_id: int) -> bool:
        """
        핑할 역할 제거

        Args:
            role_id: 역할 ID

        Returns:
            성공 여부
        """
        if role_id in self.config["ping_role_ids"]:
            self.config["ping_role_ids"].remove(role_id)
            success = self._save_config()
            if success:
                print(f"[OK] 뉴비 알림 핑 역할 제거: {role_id}")
            return success
        return True  # 없으면 성공으로 처리

    def get_ping_roles(self) -> List[int]:
        """
        핑할 역할 ID 목록 조회

        Returns:
            역할 ID 리스트
        """
        return self.config.get("ping_role_ids", [])

    def has_ping_role(self, role_id: int) -> bool:
        """
        해당 역할이 핑 목록에 있는지 확인

        Args:
            role_id: 역할 ID

        Returns:
            존재 여부
        """
        return role_id in self.config.get("ping_role_ids", [])

    def clear_all_ping_roles(self) -> bool:
        """
        모든 핑 역할 제거

        Returns:
            성공 여부
        """
        self.config["ping_role_ids"] = []
        success = self._save_config()
        if success:
            print(f"[OK] 모든 뉴비 알림 핑 역할 제거됨")
        return success

    # ===== 뉴비 목록 메시지 설정 =====

    def set_list_message(self, channel_id: int, message_id: int) -> bool:
        """
        뉴비 목록 메시지 설정

        Args:
            channel_id: 채널 ID
            message_id: 메시지 ID

        Returns:
            성공 여부
        """
        self.config["list_channel_id"] = channel_id
        self.config["list_message_id"] = message_id
        success = self._save_config()
        if success:
            print(f"[OK] 뉴비 목록 메시지 설정: 채널={channel_id}, 메시지={message_id}")
        return success

    def get_list_message(self) -> tuple:
        """
        뉴비 목록 메시지 정보 조회

        Returns:
            (channel_id, message_id) 튜플 (없으면 (None, None))
        """
        return (
            self.config.get("list_channel_id"),
            self.config.get("list_message_id")
        )

    def clear_list_message(self) -> bool:
        """
        뉴비 목록 메시지 설정 해제

        Returns:
            성공 여부
        """
        self.config["list_channel_id"] = None
        self.config["list_message_id"] = None
        success = self._save_config()
        if success:
            print(f"[OK] 뉴비 목록 메시지 설정 해제됨")
        return success

    # ===== 설정 조회 =====

    def get_all_settings(self) -> Dict:
        """
        모든 설정 조회

        Returns:
            설정 딕셔너리
        """
        return {
            "notification_channel_id": self.config.get("notification_channel_id"),
            "ping_role_ids": self.config.get("ping_role_ids", []),
            "newbie_role_id": self.config.get("newbie_role_id"),
            "list_channel_id": self.config.get("list_channel_id"),
            "list_message_id": self.config.get("list_message_id")
        }

    def is_configured(self) -> bool:
        """
        알림 채널이 설정되어 있는지 확인

        Returns:
            설정 여부
        """
        return self.config.get("notification_channel_id") is not None


# 전역 인스턴스
newbie_config_manager = NewbieConfigManager()
print("[OK] NewbieConfigManager 전역 인스턴스 생성됨")
