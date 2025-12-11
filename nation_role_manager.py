# nation_role_manager.py
"""
국가 역할 관리 시스템
국가와 Discord 역할의 매핑을 JSON으로 저장하고 관리합니다.
"""

import json
import os
import discord
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class NationRoleManager:
    """국가 역할을 관리하는 클래스"""

    def __init__(self, filename: str = "data/nation_roles.json"):
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.filename = filename
        self._nation_roles: Dict[str, Dict] = {}  # nation_name -> role_info
        self.load_nation_roles()
    
    def load_nation_roles(self):
        """국가 역할 매핑을 파일에서 로드"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._nation_roles = data.get('nation_roles', {})
                print(f"✅ 국가 역할 매핑 로드: {len(self._nation_roles)}개")
            else:
                print(f"📁 국가 역할 파일이 없어서 새로 생성합니다: {self.filename}")
                self.save_nation_roles()
        except Exception as e:
            print(f"❌ 국가 역할 매핑 로드 실패: {e}")
            self._nation_roles = {}
    
    def save_nation_roles(self):
        """국가 역할 매핑을 파일에 저장"""
        try:
            data = {
                'nation_roles': self._nation_roles,
                'metadata': {
                    'last_updated': datetime.now().isoformat(),
                    'total_nations': len(self._nation_roles),
                    'description': '국가 이름과 Discord 역할 ID의 매핑 정보'
                }
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 국가 역할 매핑 저장: {len(self._nation_roles)}개")
        except Exception as e:
            print(f"❌ 국가 역할 매핑 저장 실패: {e}")
    
    def add_nation_role(self, nation_name: str, role_id: int, guild_id: int, auto_created: bool = True) -> bool:
        """국가 역할 매핑 추가"""
        role_info = {
            'role_id': role_id,
            'guild_id': guild_id,
            'created_at': datetime.now().isoformat(),
            'auto_created': auto_created,
            'last_used': datetime.now().isoformat()
        }
        
        self._nation_roles[nation_name] = role_info
        self.save_nation_roles()
        print(f"➕ 국가 역할 매핑 추가: {nation_name} -> {role_id}")
        return True
    
    def remove_nation_role(self, nation_name: str) -> bool:
        """국가 역할 매핑 제거"""
        if nation_name in self._nation_roles:
            del self._nation_roles[nation_name]
            self.save_nation_roles()
            print(f"➖ 국가 역할 매핑 제거: {nation_name}")
            return True
        return False
    
    def get_nation_role_id(self, nation_name: str) -> Optional[int]:
        """국가에 해당하는 역할 ID 반환"""
        role_info = self._nation_roles.get(nation_name)
        if role_info:
            return role_info.get('role_id')
        return None
    
    def get_nation_role_info(self, nation_name: str) -> Optional[Dict]:
        """국가 역할의 상세 정보 반환"""
        return self._nation_roles.get(nation_name)
    
    def update_last_used(self, nation_name: str):
        """역할의 마지막 사용 시간 업데이트"""
        if nation_name in self._nation_roles:
            self._nation_roles[nation_name]['last_used'] = datetime.now().isoformat()
            self.save_nation_roles()
    
    def is_nation_mapped(self, nation_name: str) -> bool:
        """국가가 역할과 매핑되어 있는지 확인"""
        return nation_name in self._nation_roles
    
    def get_all_nation_roles(self) -> Dict[str, Dict]:
        """모든 국가 역할 매핑 반환"""
        return self._nation_roles.copy()
    
    def get_mapped_nations(self) -> List[str]:
        """매핑된 국가 목록 반환"""
        return list(self._nation_roles.keys())
    
    def get_mapping_count(self) -> int:
        """매핑된 국가 개수 반환"""
        return len(self._nation_roles)
    
    def validate_roles(self, guild) -> Dict[str, any]:
        """길드에서 역할들의 유효성 검사"""
        valid_nations = []
        invalid_nations = []
        
        for nation_name, role_info in self._nation_roles.items():
            role_id = role_info.get('role_id')
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    valid_nations.append({
                        'nation': nation_name,
                        'role': role,
                        'role_info': role_info
                    })
                else:
                    invalid_nations.append({
                        'nation': nation_name,
                        'role_id': role_id,
                        'role_info': role_info
                    })
        
        return {
            'valid_nations': valid_nations,
            'invalid_nations': invalid_nations,
            'valid_count': len(valid_nations),
            'invalid_count': len(invalid_nations)
        }
    
    def cleanup_invalid_roles(self, guild) -> int:
        """유효하지 않은 역할 매핑 정리"""
        validation = self.validate_roles(guild)
        removed_count = 0
        
        for invalid_info in validation['invalid_nations']:
            nation_name = invalid_info['nation']
            if self.remove_nation_role(nation_name):
                removed_count += 1
                print(f"🗑️ 유효하지 않은 국가 역할 매핑 제거: {nation_name}")
        
        return removed_count
    
    def clear_all_mappings(self) -> int:
        """모든 국가 역할 매핑 삭제"""
        count = len(self._nation_roles)
        self._nation_roles.clear()
        self.save_nation_roles()
        print(f"🗑️ 모든 국가 역할 매핑 삭제: {count}개")
        return count

# 전역 국가 역할 관리자 인스턴스
nation_role_manager = NationRoleManager()

async def create_nation_role_if_needed(guild, nation_name: str) -> Optional[discord.Role]:
    """
    국가 역할이 없으면 자동으로 생성하고 JSON에 저장
    
    Args:
        guild: Discord 길드 객체
        nation_name: 국가 이름
    
    Returns:
        Discord Role 객체 (생성되거나 기존 역할)
    """
    try:
        # 기존 매핑 확인
        role_id = nation_role_manager.get_nation_role_id(nation_name)
        if role_id:
            role = guild.get_role(role_id)
            if role:
                print(f"  ℹ️ 기존 국가 역할 사용: {nation_name} ({role.name})")
                # 마지막 사용 시간 업데이트
                nation_role_manager.update_last_used(nation_name)
                return role
            else:
                print(f"  ⚠️ 매핑된 역할이 존재하지 않음: {nation_name} (ID: {role_id})")
                # 잘못된 매핑 제거
                nation_role_manager.remove_nation_role(nation_name)
        
        # 길드에서 동일한 이름의 역할 찾기
        for role in guild.roles:
            if role.name == nation_name:
                print(f"  🔗 기존 역할을 매핑에 추가: {nation_name}")
                nation_role_manager.add_nation_role(nation_name, role.id, guild.id, auto_created=False)
                return role
        
        # 새 역할 생성
        print(f"  🔧 새 국가 역할 생성 중: {nation_name}")
        
        # 국가별 색상 설정
        role_color = get_nation_color(nation_name)
        
        # 역할 생성
        new_role = await guild.create_role(
            name=nation_name,
            color=role_color,
            reason=f"자동 생성: {nation_name} 국가 역할"
        )
        
        # JSON에 매핑 저장
        nation_role_manager.add_nation_role(nation_name, new_role.id, guild.id, auto_created=True)
        
        print(f"  ✅ 국가 역할 생성 및 매핑 저장 완료: {nation_name} (ID: {new_role.id})")
        return new_role
        
    except discord.Forbidden:
        print(f"  ❌ 역할 생성 권한 없음: {nation_name}")
        return None
    except Exception as e:
        print(f"  ❌ 국가 역할 생성 실패 ({nation_name}): {e}")
        return None

def get_nation_color(nation_name: str) -> discord.Color:
    """국가별 색상 반환"""
    # 특별한 국가들에 대한 색상 설정
    color_map = {
        'Red_Mafia': discord.Color.red(),
        'Blue_Alliance': discord.Color.blue(),
        'Green_Empire': discord.Color.green(),
        'Yellow_Federation': discord.Color.gold(),
        'Purple_Kingdom': discord.Color.purple(),
        'Orange_Republic': discord.Color.orange(),
        'Pink_Nation': discord.Color.magenta(),
        'Dark_Empire': discord.Color.dark_grey(),
        'Light_Kingdom': discord.Color.light_grey(),
        'Teal_Federation': discord.Color.teal(),
    }
    
    if nation_name in color_map:
        return color_map[nation_name]
    
    # 국가 이름 기반 해시로 고유 색상 생성
    import hashlib
    hash_object = hashlib.md5(nation_name.encode())
    hash_hex = hash_object.hexdigest()
    
    # 해시의 첫 6자리를 RGB 값으로 사용
    r = int(hash_hex[0:2], 16)
    g = int(hash_hex[2:4], 16)
    b = int(hash_hex[4:6], 16)
    
    # 너무 어두운 색상 방지 (최소 밝기 보장)
    if r + g + b < 200:
        r = min(255, r + 100)
        g = min(255, g + 100)
        b = min(255, b + 100)
    
    return discord.Color.from_rgb(r, g, b)

def get_nation_role_status(nation_name: str, guild=None) -> Dict[str, any]:
    """국가의 역할 연동 상태를 반환"""
    role_info = nation_role_manager.get_nation_role_info(nation_name)
    
    status = {
        'nation_name': nation_name,
        'is_mapped': role_info is not None,
        'role_id': role_info.get('role_id') if role_info else None,
        'role_exists': False,
        'role_name': None,
        'role_mention': None,
        'auto_created': role_info.get('auto_created', False) if role_info else False,
        'created_at': role_info.get('created_at') if role_info else None,
        'last_used': role_info.get('last_used') if role_info else None
    }
    
    if role_info and guild:
        role_id = role_info.get('role_id')
        if role_id:
            role = guild.get_role(role_id)
            if role:
                status['role_exists'] = True
                status['role_name'] = role.name
                status['role_mention'] = role.mention
                status['member_count'] = len(role.members)
    
    return status

def format_nation_role_info(nation: str, guild=None) -> str:
    """국가 역할 정보를 포맷된 문자열로 반환"""
    status = get_nation_role_status(nation, guild)
    
    if not status['is_mapped']:
        return f"**{nation}** → ℹ️ 역할 매핑 안됨"
    elif status['role_exists']:
        member_count = status.get('member_count', 0)
        auto_tag = " (자동생성)" if status['auto_created'] else ""
        return f"**{nation}** → {status['role_mention']} ({member_count}명){auto_tag}"
    else:
        return f"**{nation}** → ⚠️ 역할 없음 (ID: {status['role_id']})"

# 테스트용 함수
if __name__ == "__main__":
    print("🧪 NationRoleManager 테스트")
    
    # 국가 역할 매핑 추가 테스트
    nation_role_manager.add_nation_role("TestNation", 123456789, 987654321)
    print(f"매핑 개수: {nation_role_manager.get_mapping_count()}")
    
    # 매핑 조회 테스트
    role_id = nation_role_manager.get_nation_role_id("TestNation")
    print(f"TestNation 역할 ID: {role_id}")
    
    # 상태 정보 테스트
    status = get_nation_role_status("TestNation")
    print(f"TestNation 상태: {status}")
    
    # 매핑 제거 테스트
    nation_role_manager.remove_nation_role("TestNation")
    print(f"매핑 개수: {nation_role_manager.get_mapping_count()}")
    
    print("✅ 테스트 완료")