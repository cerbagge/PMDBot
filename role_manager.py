# role_manager.py에 추가할 자동역할 관리 기능

import os
from typing import List, Set

class AutoRoleManager:
    """자동처리 역할을 관리하는 클래스"""

    def __init__(self, filename: str = "data/auto_roles.txt"):
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.filename = filename
        self._roles: Set[int] = set()
        self.load_roles()
    
    def load_roles(self):
        """auto_roles.txt 파일에서 역할 목록을 로드"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        line = line.strip()
                        if line and line.isdigit():
                            self._roles.add(int(line))
                print(f"✅ 자동처리 역할 목록 로드: {len(self._roles)}개")
            else:
                print(f"📁 자동처리 역할 파일이 없어서 새로 생성합니다: {self.filename}")
                self.save_roles()
        except Exception as e:
            print(f"❌ 자동처리 역할 목록 로드 실패: {e}")
            self._roles = set()

    def reload(self):
        """파일에서 역할 목록을 다시 로드 (메모리 갱신)"""
        self._roles.clear()
        self.load_roles()
        print(f"🔄 자동처리 역할 목록 다시 로드됨: {len(self._roles)}개")
    
    def save_roles(self):
        """역할 목록을 auto_roles.txt 파일에 저장"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                for role_id in sorted(self._roles):
                    f.write(f"{role_id}\n")
            print(f"💾 자동처리 역할 목록 저장: {len(self._roles)}개")
        except Exception as e:
            print(f"❌ 자동처리 역할 목록 저장 실패: {e}")
    
    def add_role(self, role_id: int) -> bool:
        """자동처리 역할 목록에 역할 추가"""
        if role_id not in self._roles:
            self._roles.add(role_id)
            self.save_roles()
            print(f"➕ 자동처리 역할 추가: {role_id}")
            return True
        return False
    
    def remove_role(self, role_id: int) -> bool:
        """자동처리 역할 목록에서 역할 제거"""
        if role_id in self._roles:
            self._roles.remove(role_id)
            self.save_roles()
            print(f"➖ 자동처리 역할 제거: {role_id}")
            return True
        return False
    
    def has_role(self, role_id: int) -> bool:
        """역할이 자동처리 목록에 있는지 확인"""
        return role_id in self._roles
    
    def get_roles(self) -> List[int]:
        """자동처리 역할 목록 반환 (정렬된 리스트)"""
        return sorted(list(self._roles))
    
    def get_count(self) -> int:
        """자동처리 역할 개수 반환"""
        return len(self._roles)
    
    def clear_all(self) -> int:
        """모든 자동처리 역할 삭제 및 삭제된 개수 반환"""
        count = len(self._roles)
        self._roles.clear()
        self.save_roles()
        print(f"🗑️ 모든 자동처리 역할 삭제: {count}개")
        return count
    
    def is_empty(self) -> bool:
        """자동처리 역할 목록이 비어있는지 확인"""
        return len(self._roles) == 0
    
    def get_role_info(self, guild) -> List[dict]:
        """길드에서 자동처리 역할들의 정보를 반환"""
        role_info = []
        for role_id in sorted(self._roles):
            role = guild.get_role(role_id) if guild else None
            info = {
                'role_id': role_id,
                'role_exists': role is not None,
                'role_name': role.name if role else None,
                'role_mention': role.mention if role else None,
                'member_count': len(role.members) if role else 0
            }
            role_info.append(info)
        return role_info
    
    def validate_roles(self, guild) -> dict:
        """길드에서 역할들의 유효성을 검사"""
        valid_roles = []
        invalid_roles = []
        total_members = 0
        
        for role_id in self._roles:
            role = guild.get_role(role_id) if guild else None
            if role:
                valid_roles.append({
                    'role_id': role_id,
                    'role_name': role.name,
                    'member_count': len(role.members)
                })
                total_members += len(role.members)
            else:
                invalid_roles.append(role_id)
        
        return {
            'valid_roles': valid_roles,
            'invalid_roles': invalid_roles,
            'total_members': total_members,
            'valid_count': len(valid_roles),
            'invalid_count': len(invalid_roles)
        }

# 전역 자동처리 역할 관리자 인스턴스 (기존 role_manager.py에 추가)
auto_role_manager = AutoRoleManager()

def get_auto_role_status() -> dict:
    """자동처리 역할 상태 정보 반환"""
    return {
        'total_roles': auto_role_manager.get_count(),
        'is_empty': auto_role_manager.is_empty(),
        'filename': auto_role_manager.filename,
        'file_exists': os.path.exists(auto_role_manager.filename)
    }

def format_role_info(role_info: dict) -> str:
    """역할 정보를 포맷된 문자열로 반환"""
    if role_info['role_exists']:
        return f"{role_info['role_mention']} ({role_info['member_count']}명)"
    else:
        return f"⚠️ 역할 없음 (ID: {role_info['role_id']})"

def cleanup_invalid_roles(guild) -> int:
    """유효하지 않은 역할들을 자동으로 정리"""
    validation = auto_role_manager.validate_roles(guild)
    removed_count = 0
    
    for invalid_role_id in validation['invalid_roles']:
        if auto_role_manager.remove_role(invalid_role_id):
            removed_count += 1
            print(f"🗑️ 유효하지 않은 역할 자동 제거: {invalid_role_id}")
    
    return removed_count

# 기존 role_manager.py 파일에 위의 코드들을 추가하세요.
# 이미 assign_role_and_nick 함수가 있다면 그대로 두고, 
# 위의 AutoRoleManager 클래스와 관련 함수들만 추가하면 됩니다.

"""
기존 role_manager.py 파일 구조:
1. 기존의 assign_role_and_nick 함수
2. 기존의 SUCCESS_ROLE_ID 관련 코드들
3. [새로 추가] AutoRoleManager 클래스
4. [새로 추가] auto_role_manager 인스턴스
5. [새로 추가] 관련 유틸리티 함수들

이렇게 하면 기존 기능은 그대로 유지하면서 
새로운 자동역할 관리 기능이 추가됩니다.
"""