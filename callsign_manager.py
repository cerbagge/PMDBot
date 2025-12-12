# callsign_manager.py - 콜사인 관리 기능

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

class CallsignManager:
    def __init__(self, filename: str = "data/callsigns.json", banned_file: str = "data/callsign_banned.json"):
        """
        콜사인 관리자 초기화

        Args:
            filename: 콜사인 데이터 저장 파일
            banned_file: 콜사인 사용 금지 사용자 목록 파일
        """
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.filename = filename
        self.banned_file = banned_file
        self.callsigns = self.load_callsigns()
        self.banned_users = self.load_banned_users()
        self.cooldowns = self.load_cooldowns()
    
    def load_callsigns(self) -> Dict:
        """콜사인 데이터 로드"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_callsigns(self):
        """콜사인 데이터 저장"""
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.callsigns, f, ensure_ascii=False, indent=2)
    
    def load_banned_users(self) -> Dict:
        """콜사인 사용 금지 사용자 목록 로드"""
        if os.path.exists(self.banned_file):
            try:
                with open(self.banned_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_banned_users(self):
        """콜사인 사용 금지 사용자 목록 저장"""
        with open(self.banned_file, 'w', encoding='utf-8') as f:
            json.dump(self.banned_users, f, ensure_ascii=False, indent=2)
    
    def load_cooldowns(self) -> Dict:
        """쿨타임 데이터 로드"""
        cooldown_file = "callsign_cooldowns.json"
        if os.path.exists(cooldown_file):
            try:
                with open(cooldown_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # ISO 형식 문자열을 datetime 객체로 변환
                    cooldowns = {}
                    for user_id, timestamp in data.items():
                        try:
                            cooldowns[user_id] = datetime.fromisoformat(timestamp)
                        except:
                            pass
                    return cooldowns
            except:
                return {}
        return {}
    
    def save_cooldowns(self):
        """쿨타임 데이터 저장"""
        cooldown_file = "callsign_cooldowns.json"
        # datetime 객체를 ISO 형식 문자열로 변환
        data = {}
        for user_id, timestamp in self.cooldowns.items():
            data[user_id] = timestamp.isoformat()
        
        with open(cooldown_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def ban_user(self, user_id: int, banned_by: int, reason: str = "관리자 결정") -> Tuple[bool, str]:
        """
        사용자의 콜사인 사용 권한 제거
        
        Args:
            user_id: 금지할 사용자 ID
            banned_by: 금지를 실행한 관리자 ID
            reason: 금지 사유
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        # 이미 금지된 사용자인지 확인
        if user_id_str in self.banned_users:
            return False, "이미 콜사인 사용이 금지된 사용자입니다."
        
        # 금지 정보 저장
        self.banned_users[user_id_str] = {
            "banned_at": datetime.now().isoformat(),
            "banned_by": banned_by,
            "reason": reason
        }

        self.save_banned_users()

        # 기존 콜사인이 있는지 확인 (제거하지 않음)
        if user_id_str in self.callsigns:
            current_callsign = self.callsigns[user_id_str]["callsign"]
            return True, f"콜사인 변경 권한이 박탈되었습니다. (현재 콜사인 '{current_callsign}'은 유지됨)"

        return True, "콜사인 변경 권한이 박탈되었습니다."
    
    def unban_user(self, user_id: int) -> Tuple[bool, str]:
        """
        사용자의 콜사인 사용 권한 복구
        
        Args:
            user_id: 금지 해제할 사용자 ID
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        if user_id_str not in self.banned_users:
            return False, "콜사인 사용이 금지되지 않은 사용자입니다."
        
        del self.banned_users[user_id_str]
        self.save_banned_users()
        return True, "콜사인 사용 권한이 복구되었습니다."
    
    def is_banned(self, user_id: int) -> bool:
        """사용자가 콜사인 사용 금지 상태인지 확인"""
        return str(user_id) in self.banned_users
    
    def get_ban_info(self, user_id: int) -> Optional[Dict]:
        """사용자의 금지 정보 조회"""
        return self.banned_users.get(str(user_id))
    
    def get_banned_users_list(self) -> list:
        """전체 금지 사용자 목록 조회"""
        banned_list = []
        for user_id, info in self.banned_users.items():
            banned_list.append({
                "user_id": user_id,
                "banned_at": info.get("banned_at"),
                "banned_by": info.get("banned_by"),
                "reason": info.get("reason", "사유 없음")
            })
        return banned_list
    
    def set_callsign(self, user_id: int, callsign: str, force: bool = False, admin_override: bool = False) -> Tuple[bool, str]:
        """
        사용자 콜사인 설정 (권한 체크 포함)
        
        Args:
            user_id: 사용자 ID
            callsign: 설정할 콜사인
            force: 쿨타임 무시 여부 (관리자용)
            admin_override: 관리자 권한으로 금지 상태 무시 여부
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        # 금지된 사용자 체크 (관리자 권한으로 무시 가능)
        if not admin_override and self.is_banned(user_id):
            ban_info = self.get_ban_info(user_id)
            return False, f"콜사인 사용이 금지되어 있습니다.\n사유: {ban_info.get('reason', '관리자 결정')}"
        
        # 쿨타임 체크 (force가 False일 때만)
        if not force and user_id_str in self.cooldowns:
            cooldown_end = self.cooldowns[user_id_str]
            if datetime.now() < cooldown_end:
                remaining = cooldown_end - datetime.now()
                days = remaining.days
                hours = remaining.seconds // 3600
                return False, f"쿨타임 중입니다. {days}일 {hours}시간 후에 다시 시도해주세요."
        
        # 콜사인 저장
        self.callsigns[user_id_str] = {
            "callsign": callsign,
            "set_at": datetime.now().isoformat(),
            "admin_override": admin_override  # 관리자가 강제로 설정했는지 기록
        }
        
        # 쿨타임 설정 (15일) - force나 admin_override가 아닐 때만
        if not force and not admin_override:
            self.cooldowns[user_id_str] = datetime.now() + timedelta(days=15)
            self.save_cooldowns()
        
        self.save_callsigns()
        
        # 메시지 생성
        if admin_override:
            return True, f"관리자 권한으로 콜사인이 '{callsign}'(으)로 설정되었습니다."
        else:
            return True, f"콜사인이 '{callsign}'(으)로 설정되었습니다."
    
    def admin_set_callsign(self, user_id: int, callsign: str, admin_id: int) -> Tuple[bool, str]:
        """
        관리자 전용 콜사인 설정 함수 (모든 제약 무시)
        
        Args:
            user_id: 대상 사용자 ID
            callsign: 설정할 콜사인
            admin_id: 관리자 ID
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        # 기존 금지 상태 확인
        was_banned = self.is_banned(user_id)
        ban_info = None
        if was_banned:
            ban_info = self.get_ban_info(user_id)
        
        # 콜사인 설정 (모든 제약 무시)
        success, message = self.set_callsign(
            user_id=user_id, 
            callsign=callsign, 
            force=True,  # 쿨타임 무시
            admin_override=True  # 금지 상태 무시
        )
        
        if success and was_banned:
            # 금지 상태였다면 로그에 기록
            log_message = f"관리자가 권한 박탈된 사용자에게 콜사인을 강제 설정했습니다."
            if ban_info:
                log_message += f"\n이전 금지 사유: {ban_info.get('reason', '사유 없음')}"
            log_message += f"\n설정된 콜사인: '{callsign}'"
            
            return True, f"{message}\n⚠️ 주의: 이 사용자는 콜사인 사용이 금지된 상태입니다."
        
        return success, message
    
    def get_callsign(self, user_id: int) -> Optional[str]:
        """사용자 콜사인 조회"""
        return self.callsigns.get(str(user_id), {}).get("callsign")
    
    def get_callsign_info(self, user_id: int) -> Optional[Dict]:
        """사용자 콜사인 정보 전체 조회"""
        return self.callsigns.get(str(user_id))
    
    def remove_callsign(self, user_id: int) -> bool:
        """사용자 콜사인 제거 (관리자용)"""
        user_id_str = str(user_id)
        if user_id_str in self.callsigns:
            del self.callsigns[user_id_str]
            # 쿨타임도 제거
            if user_id_str in self.cooldowns:
                del self.cooldowns[user_id_str]
                self.save_cooldowns()
            self.save_callsigns()
            return True
        return False
    
    def get_callsign_count(self) -> int:
        """설정된 콜사인 개수"""
        return len(self.callsigns)
    
    def check_cooldown(self, user_id: int) -> Tuple[bool, int]:
        """
        콜사인 쿨타임 확인

        Returns:
            (사용 가능 여부, 남은 일수)
        """
        user_id_str = str(user_id)

        if user_id_str not in self.cooldowns:
            return True, 0

        cooldown_end = self.cooldowns[user_id_str]
        now = datetime.now()

        if now >= cooldown_end:
            # 쿨타임이 끝났으면 제거
            del self.cooldowns[user_id_str]
            self.save_cooldowns()
            return True, 0

        remaining = cooldown_end - now
        remaining_days = remaining.days
        if remaining.seconds > 0:
            remaining_days += 1

        return False, remaining_days

    def reset_cooldown(self, user_id: int) -> Tuple[bool, str]:
        """
        특정 사용자의 쿨타임 초기화

        Args:
            user_id: 사용자 ID

        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)

        if user_id_str in self.cooldowns:
            del self.cooldowns[user_id_str]
            self.save_cooldowns()
            return True, "쿨타임이 초기화되었습니다."
        else:
            return False, "쿨타임이 설정되어 있지 않습니다."

    def reset_all_cooldowns(self) -> int:
        """
        모든 사용자의 쿨타임 초기화

        Returns:
            초기화된 사용자 수
        """
        count = len(self.cooldowns)
        self.cooldowns.clear()
        self.save_cooldowns()
        return count


# 콜사인 검증 함수
def validate_callsign(callsign: str) -> Tuple[bool, str]:
    """
    콜사인 유효성 검증
    
    Args:
        callsign: 검증할 콜사인
    
    Returns:
        (유효 여부, 오류 메시지)
    """
    if not callsign or not callsign.strip():
        return False, "콜사인은 비어있을 수 없습니다."
    
    if len(callsign) > 20:
        return False, "콜사인은 20자 이하여야 합니다."
    
    # 금지된 문자 확인
    forbidden_chars = ['@', '#', '`', '\\', '/', '\n', '\r', '\t']
    for char in forbidden_chars:
        if char in callsign:
            return False, f"콜사인에 사용할 수 없는 문자가 포함되어 있습니다: {char}"
    
    # 디스코드 멘션 형식 차단
    if callsign.startswith('<') and callsign.endswith('>'):
        return False, "콜사인은 멘션 형식일 수 없습니다."
    
    # 이모지는 허용하되 너무 많은 이모지는 차단
    import re
    emoji_pattern = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+")
    emojis = emoji_pattern.findall(callsign)
    if len(''.join(emojis)) > 10:
        return False, "이모지가 너무 많습니다. (최대 10자)"
    
    return True, ""


# 사용자 표시 정보 가져오기
def get_user_display_info(user_id: int, mc_id: str = None, nation: str = None) -> str:
    """
    사용자 표시 정보 생성 (콜사인 또는 국가명)
    
    Args:
        user_id: 사용자 ID
        mc_id: 마인크래프트 ID
        nation: 국가명
    
    Returns:
        표시할 문자열
    """
    if not mc_id:
        return "Unknown"
    
    # 콜사인 확인
    if callsign_manager:
        callsign = callsign_manager.get_callsign(user_id)
        if callsign:
            return f"{mc_id} ㅣ {callsign}"
    
    # 콜사인이 없으면 국가명 사용
    if nation:
        return f"{mc_id} ㅣ {nation}"
    
    return mc_id


# 싱글톤 인스턴스 생성
callsign_manager = CallsignManager()
print("✅ CallsignManager 인스턴스 생성됨")