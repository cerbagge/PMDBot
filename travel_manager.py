# travel_manager.py - 여행 시스템 관리

import json
import os
from datetime import datetime, date
from typing import Optional, List, Dict
from enum import Enum


class TravelStatus(Enum):
    """여행 신청 상태"""
    PENDING = "pending"          # 대기중 (승인 대기)
    APPROVED = "approved"        # 승인됨
    REJECTED = "rejected"        # 기각됨
    ACTIVE = "active"            # 여행중 (기간 내)
    COMPLETED = "completed"      # 여행 완료 (기간 종료)
    CANCELLED = "cancelled"      # 취소됨


class TravelConfigManager:
    """여행 시스템 설정 관리"""

    def __init__(self, config_file: str = "data/travel_config.json"):
        os.makedirs("data", exist_ok=True)
        self.config_file = config_file
        self.config = self._load_config()
        print(f"[OK] TravelConfigManager 초기화 완료")

    def _load_config(self) -> dict:
        """설정 파일 로드"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] 여행 설정 파일 로드 실패: {e}")
                return self._get_default_config()
        return self._get_default_config()

    def _get_default_config(self) -> dict:
        """기본 설정 반환"""
        return {
            "request_channel_id": None,     # 여행 신청 알림 채널
            "log_channel_id": None,         # 로그 채널
            "manager_role_ids": [],         # 관리 역할 (수락/기각 가능)
            "enabled": True,               # 여행 시스템 활성화 여부
            "panel_channel_id": None,       # 여행 신청 패널 채널 ID
            "panel_message_id": None        # 여행 신청 패널 메시지 ID
        }

    def _save_config(self) -> bool:
        """설정 파일 저장"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] 여행 설정 파일 저장 실패: {e}")
            return False

    # ===== 채널 설정 =====

    def set_request_channel(self, channel_id: int) -> bool:
        """여행 신청 알림 채널 설정"""
        self.config["request_channel_id"] = channel_id
        success = self._save_config()
        if success:
            print(f"[OK] 여행 신청 채널 설정: {channel_id}")
        return success

    def get_request_channel(self) -> Optional[int]:
        """여행 신청 알림 채널 ID 조회"""
        return self.config.get("request_channel_id")

    def set_log_channel(self, channel_id: int) -> bool:
        """로그 채널 설정"""
        self.config["log_channel_id"] = channel_id
        success = self._save_config()
        if success:
            print(f"[OK] 여행 로그 채널 설정: {channel_id}")
        return success

    def get_log_channel(self) -> Optional[int]:
        """로그 채널 ID 조회"""
        return self.config.get("log_channel_id")

    # ===== 역할 설정 =====

    def add_manager_role(self, role_id: int) -> bool:
        """관리 역할 추가"""
        if role_id not in self.config["manager_role_ids"]:
            self.config["manager_role_ids"].append(role_id)
            success = self._save_config()
            if success:
                print(f"[OK] 여행 관리 역할 추가: {role_id}")
            return success
        return True

    def remove_manager_role(self, role_id: int) -> bool:
        """관리 역할 제거"""
        if role_id in self.config["manager_role_ids"]:
            self.config["manager_role_ids"].remove(role_id)
            success = self._save_config()
            if success:
                print(f"[OK] 여행 관리 역할 제거: {role_id}")
            return success
        return True

    def get_manager_roles(self) -> List[int]:
        """관리 역할 ID 목록 조회"""
        return self.config.get("manager_role_ids", [])

    def has_manager_role(self, role_id: int) -> bool:
        """해당 역할이 관리 역할인지 확인"""
        return role_id in self.config.get("manager_role_ids", [])

    def is_manager(self, member) -> bool:
        """멤버가 여행 관리자인지 확인"""
        if member.guild_permissions.administrator:
            return True
        manager_roles = self.get_manager_roles()
        return any(role.id in manager_roles for role in member.roles)

    # ===== 시스템 설정 =====

    def set_enabled(self, enabled: bool) -> bool:
        """여행 시스템 활성화/비활성화"""
        self.config["enabled"] = enabled
        return self._save_config()

    def is_enabled(self) -> bool:
        """여행 시스템 활성화 여부"""
        return self.config.get("enabled", True)

    def is_configured(self) -> bool:
        """시스템이 설정되어 있는지 확인"""
        return self.config.get("request_channel_id") is not None

    def get_all_settings(self) -> Dict:
        """모든 설정 조회"""
        return {
            "request_channel_id": self.config.get("request_channel_id"),
            "log_channel_id": self.config.get("log_channel_id"),
            "manager_role_ids": self.config.get("manager_role_ids", []),
            "enabled": self.config.get("enabled", True),
            "panel_channel_id": self.config.get("panel_channel_id"),
            "panel_message_id": self.config.get("panel_message_id")
        }

    # ===== 블랙리스트 =====

    def add_blacklist(self, discord_id: int, added_by: int, reason: str = None) -> bool:
        """블랙리스트 추가"""
        blacklist = self.config.setdefault("blacklist", {})
        blacklist[str(discord_id)] = {
            "added_at": datetime.now().isoformat(),
            "added_by": added_by,
            "reason": reason
        }
        success = self._save_config()
        if success:
            print(f"[OK] 여행 블랙리스트 추가: {discord_id}")
        return success

    def remove_blacklist(self, discord_id: int) -> bool:
        """블랙리스트 제거"""
        blacklist = self.config.get("blacklist", {})
        if str(discord_id) in blacklist:
            del blacklist[str(discord_id)]
            success = self._save_config()
            if success:
                print(f"[OK] 여행 블랙리스트 제거: {discord_id}")
            return success
        return False

    def is_blacklisted(self, discord_id: int) -> bool:
        """블랙리스트 여부 확인"""
        return str(discord_id) in self.config.get("blacklist", {})

    def get_blacklist_info(self, discord_id: int) -> Optional[Dict]:
        """블랙리스트 정보 조회"""
        return self.config.get("blacklist", {}).get(str(discord_id))

    def get_all_blacklist(self) -> Dict:
        """전체 블랙리스트 조회"""
        return self.config.get("blacklist", {})

    # ===== 여행 신청 패널 설정 =====

    def set_panel_info(self, channel_id: int, message_id: int) -> bool:
        """여행 신청 패널 정보 저장"""
        self.config["panel_channel_id"] = channel_id
        self.config["panel_message_id"] = message_id
        success = self._save_config()
        if success:
            print(f"[OK] 여행 신청 패널 설정: channel={channel_id}, message={message_id}")
        return success

    def get_panel_info(self) -> Optional[Dict]:
        """여행 신청 패널 정보 조회"""
        channel_id = self.config.get("panel_channel_id")
        message_id = self.config.get("panel_message_id")
        if channel_id and message_id:
            return {"channel_id": channel_id, "message_id": message_id}
        return None

    def clear_panel_info(self) -> bool:
        """여행 신청 패널 정보 초기화"""
        self.config["panel_channel_id"] = None
        self.config["panel_message_id"] = None
        return self._save_config()


class TravelManager:
    """여행 신청 데이터 관리"""

    def __init__(self, data_file: str = "data/travel_data.json"):
        os.makedirs("data", exist_ok=True)
        self.data_file = data_file
        self.data = self._load_data()
        print(f"[OK] TravelManager 초기화 완료")

    def _load_data(self) -> dict:
        """데이터 파일 로드"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] 여행 데이터 파일 로드 실패: {e}")
                return self._get_default_data()
        return self._get_default_data()

    def _get_default_data(self) -> dict:
        """기본 데이터 구조 반환"""
        return {
            "travels": {},        # travel_id -> travel_data
            "next_id": 1,         # 다음 여행 ID
            "user_travels": {}    # discord_id -> [travel_ids]
        }

    def _save_data(self) -> bool:
        """데이터 파일 저장"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] 여행 데이터 파일 저장 실패: {e}")
            return False

    def _generate_id(self) -> str:
        """새 여행 ID 생성"""
        travel_id = f"T{self.data['next_id']:06d}"
        self.data['next_id'] += 1
        self._save_data()
        return travel_id

    # ===== 여행 신청 관리 =====

    def create_travel_request(
        self,
        discord_id: int,
        minecraft_name: str,
        current_nation: str,
        current_town: str,
        destination_nation: str,
        start_date: str,
        end_date: str,
        callsign: str = None,
        message_id: int = None
    ) -> Optional[str]:
        """
        여행 신청 생성

        Args:
            discord_id: 디스코드 사용자 ID
            minecraft_name: 마인크래프트 닉네임
            current_nation: 현재 국가
            current_town: 현재 마을
            destination_nation: 여행 목적지 국가
            start_date: 시작일 (YYYY.MM.DD)
            end_date: 종료일 (YYYY.MM.DD)
            callsign: 콜사인 (선택)
            message_id: 신청 메시지 ID (선택)

        Returns:
            생성된 여행 ID (실패 시 None)
        """
        try:
            travel_id = self._generate_id()

            travel_data = {
                "id": travel_id,
                "discord_id": discord_id,
                "minecraft_name": minecraft_name,
                "current_nation": current_nation,
                "current_town": current_town,
                "destination_nation": destination_nation,
                "start_date": start_date,
                "end_date": end_date,
                "callsign": callsign,
                "status": TravelStatus.PENDING.value,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "reviewed_by": None,
                "review_reason": None,
                "reviewed_at": None,
                "message_id": message_id,
                "notified_1day": False,
                "notified_end": False
            }

            self.data["travels"][travel_id] = travel_data

            # 사용자별 여행 목록에 추가
            discord_id_str = str(discord_id)
            if discord_id_str not in self.data["user_travels"]:
                self.data["user_travels"][discord_id_str] = []
            self.data["user_travels"][discord_id_str].append(travel_id)

            self._save_data()
            print(f"[OK] 여행 신청 생성: {travel_id} (유저: {discord_id})")
            return travel_id

        except Exception as e:
            print(f"[ERROR] 여행 신청 생성 실패: {e}")
            return None

    def get_travel(self, travel_id: str) -> Optional[Dict]:
        """여행 정보 조회"""
        return self.data["travels"].get(travel_id)

    def get_user_travels(self, discord_id: int, status: TravelStatus = None) -> List[Dict]:
        """사용자의 여행 목록 조회"""
        discord_id_str = str(discord_id)
        travel_ids = self.data["user_travels"].get(discord_id_str, [])

        travels = []
        for tid in travel_ids:
            travel = self.data["travels"].get(tid)
            if travel:
                if status is None or travel["status"] == status.value:
                    travels.append(travel)

        return travels

    def get_active_travel(self, discord_id: int) -> Optional[Dict]:
        """사용자의 현재 활성 여행 조회 (승인됨 또는 여행중)"""
        travels = self.get_user_travels(discord_id)
        for travel in travels:
            if travel["status"] in [TravelStatus.APPROVED.value, TravelStatus.ACTIVE.value]:
                return travel
        return None

    def is_traveling(self, discord_id: int) -> bool:
        """사용자가 현재 여행 중인지 확인"""
        travel = self.get_active_travel(discord_id)
        if not travel:
            return False

        # 상태가 active이거나 approved이고 기간 내인 경우
        if travel["status"] == TravelStatus.ACTIVE.value:
            return True

        if travel["status"] == TravelStatus.APPROVED.value:
            today = date.today()
            try:
                start = datetime.strptime(travel["start_date"], "%Y.%m.%d").date()
                end = datetime.strptime(travel["end_date"], "%Y.%m.%d").date()
                return start <= today <= end
            except:
                return False

        return False

    def get_travel_destination(self, discord_id: int) -> Optional[str]:
        """사용자의 여행 목적지 국가 조회"""
        travel = self.get_active_travel(discord_id)
        if travel and self.is_traveling(discord_id):
            return travel.get("destination_nation")
        return None

    # ===== 여행 상태 관리 =====

    def approve_travel(self, travel_id: str, reviewer_id: int, reason: str = None) -> bool:
        """여행 승인"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["status"] = TravelStatus.APPROVED.value
        travel["reviewed_by"] = reviewer_id
        travel["review_reason"] = reason
        travel["reviewed_at"] = datetime.now().isoformat()
        travel["updated_at"] = datetime.now().isoformat()

        self._save_data()
        print(f"[OK] 여행 승인: {travel_id} (승인자: {reviewer_id})")
        return True

    def reject_travel(self, travel_id: str, reviewer_id: int, reason: str = None) -> bool:
        """여행 기각"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["status"] = TravelStatus.REJECTED.value
        travel["reviewed_by"] = reviewer_id
        travel["review_reason"] = reason
        travel["reviewed_at"] = datetime.now().isoformat()
        travel["updated_at"] = datetime.now().isoformat()

        self._save_data()
        print(f"[OK] 여행 기각: {travel_id} (기각자: {reviewer_id})")
        return True

    def set_original_nation(self, travel_id: str, nation: str) -> bool:
        """여행에 원래 소속 국가 정보 저장"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["original_nation"] = nation
        travel["updated_at"] = datetime.now().isoformat()

        self._save_data()
        print(f"[OK] 원래 국가 설정: {travel_id} → {nation}")
        return True

    def get_original_nation(self, travel_id: str) -> Optional[str]:
        """여행의 원래 소속 국가 조회"""
        travel = self.data["travels"].get(travel_id)
        if travel:
            return travel.get("original_nation")
        return None

    def activate_travel(self, travel_id: str) -> bool:
        """여행 활성화 (여행 시작)"""
        travel = self.data["travels"].get(travel_id)
        if not travel or travel["status"] != TravelStatus.APPROVED.value:
            return False

        travel["status"] = TravelStatus.ACTIVE.value
        travel["updated_at"] = datetime.now().isoformat()

        self._save_data()
        print(f"[OK] 여행 활성화: {travel_id}")
        return True

    def complete_travel(self, travel_id: str) -> bool:
        """여행 완료 (기간 종료)"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["status"] = TravelStatus.COMPLETED.value
        travel["updated_at"] = datetime.now().isoformat()

        self._save_data()
        print(f"[OK] 여행 완료: {travel_id}")
        return True

    def cancel_travel(self, travel_id: str) -> bool:
        """여행 취소"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["status"] = TravelStatus.CANCELLED.value
        travel["updated_at"] = datetime.now().isoformat()

        self._save_data()
        print(f"[OK] 여행 취소: {travel_id}")
        return True

    def update_message_id(self, travel_id: str, message_id: int) -> bool:
        """여행 신청 메시지 ID 업데이트"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["message_id"] = message_id
        self._save_data()
        return True

    def mark_notified_1day(self, travel_id: str) -> bool:
        """1일 전 알림 완료 표시"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["notified_1day"] = True
        self._save_data()
        return True

    def mark_notified_end(self, travel_id: str) -> bool:
        """종료일 알림 완료 표시"""
        travel = self.data["travels"].get(travel_id)
        if not travel:
            return False

        travel["notified_end"] = True
        self._save_data()
        return True

    # ===== 조회 기능 =====

    def get_pending_travels(self) -> List[Dict]:
        """대기 중인 여행 신청 목록"""
        return [t for t in self.data["travels"].values()
                if t["status"] == TravelStatus.PENDING.value]

    def get_active_travels(self) -> List[Dict]:
        """활성 여행 목록 (승인됨 + 여행중)"""
        return [t for t in self.data["travels"].values()
                if t["status"] in [TravelStatus.APPROVED.value, TravelStatus.ACTIVE.value]]

    def get_travels_ending_soon(self, days: int = 1) -> List[Dict]:
        """곧 종료되는 여행 목록"""
        result = []
        today = date.today()

        for travel in self.get_active_travels():
            try:
                end_date = datetime.strptime(travel["end_date"], "%Y.%m.%d").date()
                days_until = (end_date - today).days

                if 0 <= days_until <= days:
                    result.append({
                        **travel,
                        "days_until_end": days_until
                    })
            except Exception as e:
                print(f"[ERROR] 날짜 파싱 실패 ({travel['id']}): {e}")

        return result

    def get_expired_travels(self) -> List[Dict]:
        """기간이 만료된 여행 목록"""
        result = []
        today = date.today()

        for travel in self.get_active_travels():
            try:
                end_date = datetime.strptime(travel["end_date"], "%Y.%m.%d").date()
                if end_date < today:
                    result.append(travel)
            except Exception as e:
                print(f"[ERROR] 날짜 파싱 실패 ({travel['id']}): {e}")

        return result

    def get_travels_starting_today(self) -> List[Dict]:
        """오늘 시작하는 여행 목록"""
        result = []
        today = date.today()

        for travel in self.data["travels"].values():
            if travel["status"] == TravelStatus.APPROVED.value:
                try:
                    start_date = datetime.strptime(travel["start_date"], "%Y.%m.%d").date()
                    if start_date == today:
                        result.append(travel)
                except Exception as e:
                    print(f"[ERROR] 날짜 파싱 실패 ({travel['id']}): {e}")

        return result

    def calculate_travel_days(self, travel: Dict) -> int:
        """여행 일수 계산"""
        try:
            start = datetime.strptime(travel["start_date"], "%Y.%m.%d").date()
            end = datetime.strptime(travel["end_date"], "%Y.%m.%d").date()
            return (end - start).days + 1
        except:
            return 0

    def get_all_travels(self, limit: int = None) -> List[Dict]:
        """모든 여행 목록 조회"""
        travels = list(self.data["travels"].values())
        travels.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        if limit:
            return travels[:limit]
        return travels


# 전역 인스턴스
travel_config_manager = TravelConfigManager()
travel_manager = TravelManager()
print("[OK] 여행 시스템 매니저 전역 인스턴스 생성됨")
