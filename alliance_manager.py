# alliance_manager.py
"""
동맹 국가/마을 관리 시스템 (UUID 기반)
기본 국가 외에 동맹 관계에 있는 국가들을 UUID로 관리하여
해당 국가 소속 사용자들도 국민 역할을 받을 수 있도록 합니다.
"""

import json
import os
from typing import List, Dict, Optional
from datetime import datetime

class AllianceManager:
    """동맹 국가/마을을 UUID 기반으로 관리하는 클래스"""

    def __init__(self, filename: str = "data/alliance_data.json"):
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.filename = filename
        # {uuid: {type: 'nation'|'town', name: str, names: [str], added_at: str}}
        self._alliances: Dict[str, Dict] = {}
        self.load_alliances()

    def load_alliances(self):
        """동맹 데이터를 파일에서 로드"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._alliances = data.get('alliances', {})
                print(f"✅ 동맹 데이터 로드: {len(self._alliances)}개 (UUID 기반)")
            else:
                print(f"📁 동맹 데이터 파일이 없어서 새로 생성합니다: {self.filename}")
                self.save_alliances()
        except Exception as e:
            print(f"❌ 동맹 데이터 로드 실패: {e}")
            self._alliances = {}

    def save_alliances(self):
        """동맹 데이터를 파일에 저장"""
        try:
            data = {
                'alliances': self._alliances,
                'count': len(self._alliances),
                'description': '동맹 관계에 있는 국가/마을 목록 (UUID 기반)',
                'last_updated': datetime.now().isoformat()
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 동맹 데이터 저장: {len(self._alliances)}개")
        except Exception as e:
            print(f"❌ 동맹 데이터 저장 실패: {e}")

    def add_alliance_by_uuid(
        self,
        uuid: str,
        entity_type: str,  # 'nation' or 'town'
        name: str,
        all_names: List[str] = None
    ) -> bool:
        """
        UUID로 동맹 추가

        Args:
            uuid: 국가/마을 UUID
            entity_type: 'nation' 또는 'town'
            name: 기본 이름
            all_names: 모든 언어의 이름들
        """
        if uuid not in self._alliances:
            self._alliances[uuid] = {
                'type': entity_type,
                'name': name,
                'names': all_names or [name],
                'added_at': datetime.now().isoformat()
            }
            self.save_alliances()
            print(f"➕ 동맹 추가: {name} (UUID: {uuid}, Type: {entity_type})")
            return True
        else:
            # 이미 존재하는 경우 정보 업데이트
            self._alliances[uuid].update({
                'name': name,
                'names': all_names or [name],
                'updated_at': datetime.now().isoformat()
            })
            self.save_alliances()
            print(f"🔄 동맹 정보 업데이트: {name} (UUID: {uuid})")
            return True

    def remove_alliance_by_uuid(self, uuid: str) -> bool:
        """UUID로 동맹 제거"""
        if uuid in self._alliances:
            name = self._alliances[uuid].get('name', uuid)
            del self._alliances[uuid]
            self.save_alliances()
            print(f"➖ 동맹 제거: {name} (UUID: {uuid})")
            return True
        return False

    def is_alliance_uuid(self, uuid: str) -> bool:
        """UUID가 동맹인지 확인"""
        return uuid in self._alliances

    def is_alliance_name(self, name: str) -> bool:
        """
        이름으로 동맹인지 확인 (모든 언어의 이름 검색)
        대소문자 구분 없이 검색
        """
        name_lower = name.lower()
        for alliance_data in self._alliances.values():
            # 기본 이름 확인
            if alliance_data.get('name', '').lower() == name_lower:
                return True
            # 모든 언어의 이름 확인
            if name_lower in [n.lower() for n in alliance_data.get('names', [])]:
                return True
        return False

    def get_alliance_uuid_by_name(self, name: str) -> Optional[str]:
        """이름으로 동맹 UUID 찾기"""
        name_lower = name.lower()
        for uuid, alliance_data in self._alliances.items():
            # 기본 이름 확인
            if alliance_data.get('name', '').lower() == name_lower:
                return uuid
            # 모든 언어의 이름 확인
            if name_lower in [n.lower() for n in alliance_data.get('names', [])]:
                return uuid
        return None

    def get_alliance_data(self, uuid: str) -> Optional[Dict]:
        """UUID로 동맹 데이터 가져오기"""
        return self._alliances.get(uuid)

    def get_all_alliances(self) -> Dict[str, Dict]:
        """모든 동맹 데이터 반환"""
        return self._alliances.copy()

    def get_alliances_list(self) -> List[Dict]:
        """동맹 목록을 리스트로 반환 (정렬됨)"""
        result = []
        for uuid, data in self._alliances.items():
            result.append({
                'uuid': uuid,
                **data
            })
        return sorted(result, key=lambda x: x.get('name', ''))

    def get_alliance_count(self) -> int:
        """동맹 개수 반환"""
        return len(self._alliances)

    def clear_all_alliances(self) -> int:
        """모든 동맹 관계 해제"""
        count = len(self._alliances)
        self._alliances.clear()
        self.save_alliances()
        print(f"🗑️ 모든 동맹 관계 해제: {count}개")
        return count

# 전역 동맹 관리자 인스턴스
alliance_manager = AllianceManager()

async def add_alliance_by_name(name: str, entity_type: str = 'nation') -> Optional[Dict]:
    """
    이름으로 동맹 추가 (PE API 사용)

    Args:
        name: 국가 또는 마을 이름
        entity_type: 'nation' 또는 'town'

    Returns:
        추가된 동맹 데이터 또는 None
    """
    try:
        from pe_api_utils import pe_api

        # PE API에서 정보 조회
        if entity_type == 'nation':
            data = await pe_api.get_nation_by_name(name)
        elif entity_type == 'town':
            data = await pe_api.get_town_by_name(name)
        else:
            print(f"❌ 잘못된 타입: {entity_type}")
            return None

        if not data:
            print(f"❌ {entity_type} 정보를 찾을 수 없음: {name}")
            return None

        # UUID 추출
        uuid = data.get('uuid')
        if not uuid:
            print(f"❌ UUID가 없음: {name}")
            return None

        # 모든 이름 추출
        all_names = []
        if 'name' in data:
            all_names.append(data['name'])
        if 'names' in data and isinstance(data['names'], list):
            all_names.extend(data['names'])

        # 동맹 추가
        alliance_manager.add_alliance_by_uuid(
            uuid=uuid,
            entity_type=entity_type,
            name=data.get('name', name),
            all_names=list(set(all_names))  # 중복 제거
        )

        return {
            'uuid': uuid,
            'type': entity_type,
            'name': data.get('name', name),
            'names': all_names
        }

    except Exception as e:
        print(f"❌ 동맹 추가 실패 ({name}): {e}")
        return None

def is_friendly_nation(nation_uuid: str = None, nation_name: str = None) -> bool:
    """
    우호 국가인지 확인하는 유틸리티 함수

    Args:
        nation_uuid: 국가 UUID (우선순위 높음)
        nation_name: 국가 이름

    Returns:
        기본 국가이거나 동맹 국가인 경우 True
    """
    try:
        from config import config

        # UUID로 확인 (우선)
        if nation_uuid:
            # 기본 국가 UUID 확인
            base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)
            if base_nation_uuid and nation_uuid == base_nation_uuid:
                return True
            # 동맹 UUID 확인
            return alliance_manager.is_alliance_uuid(nation_uuid)

        # 이름으로 확인 (fallback)
        if nation_name:
            # 기본 국가 이름 확인 (legacy)
            base_nation = getattr(config, 'BASE_NATION', None)
            if base_nation and nation_name == base_nation:
                return True
            # 동맹 이름 확인
            return alliance_manager.is_alliance_name(nation_name)

        return False

    except Exception as e:
        print(f"❌ 우호 국가 확인 실패: {e}")
        return False

async def create_nation_role_if_needed(guild, nation_name: str):
    """
    국가 역할이 없으면 자동으로 생성
    이제 nation_role_manager를 사용하여 JSON에 저장

    Args:
        guild: Discord 길드 객체
        nation_name: 국가 이름

    Returns:
        Discord Role 객체 (생성되거나 기존 역할)
    """
    try:
        # nation_role_manager 사용
        from nation_role_manager import nation_role_manager, create_nation_role_if_needed as create_role
        return await create_role(guild, nation_name)

    except ImportError:
        # nation_role_manager가 없으면 기본 방식 사용
        import discord
        print(f"  ⚠️ nation_role_manager 없음 - 기본 방식으로 역할 생성: {nation_name}")

        # 기존 역할 확인
        for role in guild.roles:
            if role.name == nation_name:
                print(f"  ℹ️ 기존 국가 역할 사용: {nation_name}")
                return role

        # 새 역할 생성
        print(f"  🔧 새 국가 역할 생성 중: {nation_name}")

        try:
            # 국가별 색상 설정 (옵션)
            role_color = discord.Color.blue()  # 기본 파란색

            # 특별한 국가들에 대한 색상 설정
            color_map = {
                'Red_Mafia': discord.Color.red(),
                'Blue_Alliance': discord.Color.blue(),
                'Green_Empire': discord.Color.green(),
                'Yellow_Federation': discord.Color.gold(),
                'Purple_Kingdom': discord.Color.purple(),
            }

            if nation_name in color_map:
                role_color = color_map[nation_name]

            # 역할 생성
            new_role = await guild.create_role(
                name=nation_name,
                color=role_color,
                reason=f"자동 생성: {nation_name} 국가 역할"
            )

            print(f"  ✅ 국가 역할 생성 완료: {nation_name} (ID: {new_role.id})")
            return new_role

        except discord.Forbidden:
            print(f"  ❌ 역할 생성 권한 없음: {nation_name}")
            return None
        except Exception as e:
            print(f"  ❌ 국가 역할 생성 실패 ({nation_name}): {e}")
            return None

def get_alliance_status_summary() -> dict:
    """동맹 상태 요약 정보 반환"""
    return {
        'total_alliances': alliance_manager.get_alliance_count(),
        'alliance_list': alliance_manager.get_alliances_list(),
        'filename': alliance_manager.filename,
        'file_exists': os.path.exists(alliance_manager.filename)
    }

# 테스트용 함수
if __name__ == "__main__":
    import asyncio

    async def test():
        print("🧪 AllianceManager 테스트 (UUID 기반)")

        # 동맹 추가 테스트 (이름으로)
        result = await add_alliance_by_name("Red_Mafia", "nation")
        if result:
            print(f"✅ 동맹 추가 성공: {result}")

        # 동맹 확인 테스트 (UUID)
        if result:
            is_ally = alliance_manager.is_alliance_uuid(result['uuid'])
            print(f"UUID로 동맹 확인: {is_ally}")

        # 동맹 확인 테스트 (이름)
        is_ally_name = alliance_manager.is_alliance_name("Red_Mafia")
        print(f"이름으로 동맹 확인: {is_ally_name}")

        # 우호국 확인 테스트
        if result:
            is_friendly = is_friendly_nation(nation_uuid=result['uuid'])
            print(f"우호국 확인: {is_friendly}")

        # 동맹 목록
        alliances = alliance_manager.get_alliances_list()
        print(f"동맹 목록: {alliances}")

        print("✅ 테스트 완료")

        # PE API 세션 종료
        from pe_api_utils import pe_api
        await pe_api.close()

    asyncio.run(test())