# town_role_manager.py
"""
마을-역할 매핑 관리 시스템 (UUID 기반)
기존 Discord 역할과 마인크래프트 마을을 연동하는 기능을 제공합니다.
"""

import json
import os
import aiohttp
from typing import Dict, List, Optional, Tuple

class TownRoleManager:
    """마을-역할 매핑을 관리하는 클래스 (UUID 기반)"""

    def __init__(self, filename: str = "data/town_role_mapping.json"):
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.filename = filename
        self._mapping: Dict[str, Dict] = {}  # nation_uuid -> { town_uuid -> { role_id, town_name, nation_name } }
        self.load_mapping()

    def load_mapping(self):
        """마을-역할 매핑을 파일에서 로드"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 새 형식(UUID 기반) 확인
                    if 'version' in data and data['version'] == '2.0':
                        self._mapping = data.get('mappings', {})
                        print(f"✅ 마을 역할 매핑 로드 (UUID): {self._count_total_towns()}개")
                    else:
                        # 구 형식(이름 기반) - 마이그레이션 필요
                        print(f"⚠️ 구 형식의 매핑 파일 감지. UUID 기반으로 마이그레이션이 필요합니다.")
                        self._mapping = {}
                        self.save_mapping()
            else:
                print(f"📁 마을 역할 매핑 파일이 없어서 새로 생성합니다: {self.filename}")
                self.save_mapping()
        except Exception as e:
            print(f"❌ 마을 역할 매핑 로드 실패: {e}")
            self._mapping = {}

    def save_mapping(self):
        """마을-역할 매핑을 파일에 저장"""
        try:
            data = {
                'version': '2.0',
                'description': 'UUID 기반 마을-역할 매핑 (국가 UUID -> 마을 UUID -> 역할 정보)',
                'mappings': self._mapping,
                'total_nations': len(self._mapping),
                'total_towns': self._count_total_towns()
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 마을 역할 매핑 저장: {data['total_towns']}개 마을")
        except Exception as e:
            print(f"❌ 마을 역할 매핑 저장 실패: {e}")

    def _count_total_towns(self) -> int:
        """전체 매핑된 마을 수 계산"""
        count = 0
        for nation_data in self._mapping.values():
            count += len(nation_data)
        return count

    def add_mapping(
        self,
        nation_uuid: str,
        town_uuid: str,
        role_id: int,
        nation_name: str,
        town_name: str
    ) -> bool:
        """마을-역할 매핑 추가 (UUID 기반)"""
        if nation_uuid not in self._mapping:
            self._mapping[nation_uuid] = {}

        self._mapping[nation_uuid][town_uuid] = {
            'role_id': role_id,
            'town_name': town_name,
            'nation_name': nation_name
        }

        self.save_mapping()
        print(f"➕ 마을 역할 매핑 추가: {nation_name}/{town_name} (UUID: {town_uuid}) -> {role_id}")
        return True

    def remove_mapping(self, nation_uuid: str, town_uuid: str) -> bool:
        """마을-역할 매핑 제거 (UUID 기반)"""
        if nation_uuid in self._mapping and town_uuid in self._mapping[nation_uuid]:
            town_info = self._mapping[nation_uuid][town_uuid]
            del self._mapping[nation_uuid][town_uuid]

            # 국가에 더 이상 마을이 없으면 국가 키도 제거
            if not self._mapping[nation_uuid]:
                del self._mapping[nation_uuid]

            self.save_mapping()
            print(f"➖ 마을 역할 매핑 제거: {town_info['nation_name']}/{town_info['town_name']}")
            return True
        return False

    def remove_mapping_by_name(self, town_name: str) -> bool:
        """마을-역할 매핑 제거 (이름 기반, 하위 호환용)"""
        for nation_uuid, towns in self._mapping.items():
            for town_uuid, town_info in towns.items():
                if town_info['town_name'] == town_name:
                    return self.remove_mapping(nation_uuid, town_uuid)
        return False

    def get_role_id(self, nation_uuid: str, town_uuid: str) -> Optional[int]:
        """마을에 해당하는 역할 ID 반환 (UUID 기반)"""
        if nation_uuid in self._mapping and town_uuid in self._mapping[nation_uuid]:
            return self._mapping[nation_uuid][town_uuid]['role_id']
        return None

    def get_role_id_by_name(self, town_name: str) -> Optional[int]:
        """마을에 해당하는 역할 ID 반환 (이름 기반, 하위 호환용)"""
        for nation_data in self._mapping.values():
            for town_info in nation_data.values():
                if town_info['town_name'] == town_name:
                    return town_info['role_id']
        return None

    def get_town_info(self, nation_uuid: str, town_uuid: str) -> Optional[Dict]:
        """마을 정보 반환"""
        if nation_uuid in self._mapping and town_uuid in self._mapping[nation_uuid]:
            return self._mapping[nation_uuid][town_uuid].copy()
        return None

    def get_town_info_by_name(self, town_name: str) -> Optional[Dict]:
        """마을 정보 반환 (이름 기반)"""
        for nation_uuid, nation_data in self._mapping.items():
            for town_uuid, town_info in nation_data.items():
                if town_info['town_name'] == town_name:
                    return {
                        'nation_uuid': nation_uuid,
                        'town_uuid': town_uuid,
                        **town_info
                    }
        return None

    def get_all_mappings(self) -> Dict[str, Dict]:
        """모든 매핑 반환 (UUID 기반)"""
        return self._mapping.copy()

    def get_all_mappings_flat(self) -> List[Dict]:
        """모든 매핑을 평면화된 리스트로 반환"""
        result = []
        for nation_uuid, nation_data in self._mapping.items():
            for town_uuid, town_info in nation_data.items():
                result.append({
                    'nation_uuid': nation_uuid,
                    'town_uuid': town_uuid,
                    **town_info
                })
        return result

    def get_mapped_towns_in_nation(self, nation_uuid: str) -> List[Dict]:
        """특정 국가의 매핑된 마을 목록 반환"""
        if nation_uuid not in self._mapping:
            return []

        result = []
        for town_uuid, town_info in self._mapping[nation_uuid].items():
            result.append({
                'town_uuid': town_uuid,
                **town_info
            })
        return result

    def get_mapped_towns(self) -> List[str]:
        """매핑된 마을 이름 목록 반환 (하위 호환용)"""
        towns = []
        for nation_data in self._mapping.values():
            for town_info in nation_data.values():
                towns.append(town_info['town_name'])
        return towns

    def get_mapping_count(self) -> int:
        """매핑된 마을-역할 개수 반환"""
        return self._count_total_towns()

    def is_town_mapped(self, nation_uuid: str, town_uuid: str) -> bool:
        """마을이 역할과 매핑되어 있는지 확인 (UUID 기반)"""
        return nation_uuid in self._mapping and town_uuid in self._mapping[nation_uuid]

    def is_town_mapped_by_name(self, town_name: str) -> bool:
        """마을이 역할과 매핑되어 있는지 확인 (이름 기반)"""
        for nation_data in self._mapping.values():
            for town_info in nation_data.values():
                if town_info['town_name'] == town_name:
                    return True
        return False

    def clear_all_mappings(self) -> int:
        """모든 매핑 삭제 및 삭제된 개수 반환"""
        count = self._count_total_towns()
        self._mapping.clear()
        self.save_mapping()
        print(f"🗑️ 모든 마을 역할 매핑 삭제: {count}개")
        return count

    def update_town_name(self, nation_uuid: str, town_uuid: str, new_town_name: str) -> bool:
        """마을 이름 업데이트"""
        if nation_uuid in self._mapping and town_uuid in self._mapping[nation_uuid]:
            self._mapping[nation_uuid][town_uuid]['town_name'] = new_town_name
            self.save_mapping()
            print(f"✏️ 마을 이름 업데이트: {town_uuid} -> {new_town_name}")
            return True
        return False

    def update_nation_name(self, nation_uuid: str, new_nation_name: str) -> int:
        """국가 이름 업데이트 (해당 국가의 모든 마을)"""
        if nation_uuid not in self._mapping:
            return 0

        count = 0
        for town_info in self._mapping[nation_uuid].values():
            town_info['nation_name'] = new_nation_name
            count += 1

        self.save_mapping()
        print(f"✏️ 국가 이름 업데이트: {nation_uuid} -> {new_nation_name} ({count}개 마을)")
        return count

# 전역 마을 역할 관리자 인스턴스
town_role_manager = TownRoleManager()

async def get_towns_in_nation(nation_name: str = None, nation_uuid: str = None) -> List[Dict]:
    """특정 국가의 마을 목록 조회 (UUID 기반)"""
    try:
        # config에서 API 베이스 URL 가져오기
        try:
            from config import config
            api_base = config.MC_API_BASE
        except:
            import os
            api_base = os.getenv("MC_API_BASE", "https://api.planetearth.kr")

        async with aiohttp.ClientSession() as session:
            # UUID 우선, 없으면 이름 사용
            if nation_uuid:
                url = f"{api_base}/nation?uuid={nation_uuid}"
            elif nation_name:
                url = f"{api_base}/nation?name={nation_name}"
            else:
                print("❌ 국가 이름 또는 UUID가 필요합니다")
                return []

            print(f"🔍 국가 정보 조회: {url}")

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    print(f"❌ 국가 정보 조회 실패: HTTP {response.status}")
                    return []

                data = await response.json()
                if not data.get('data') or not data['data']:
                    print(f"❌ 국가 데이터 없음")
                    return []

                nation_data = data['data'][0]
                nation_uuid_result = nation_data.get('uuid')
                nation_name_result = nation_data.get('name')
                towns = nation_data.get('towns', [])

                if not towns:
                    print(f"ℹ️ {nation_name_result}에 마을이 없습니다.")
                    return []

                # 마을 정보를 { name, uuid } 형태로 변환
                town_list = []
                for town in towns:
                    if isinstance(town, dict):
                        town_list.append({
                            'name': town.get('name'),
                            'uuid': town.get('uuid'),
                            'nation_name': nation_name_result,
                            'nation_uuid': nation_uuid_result
                        })
                    else:
                        # 레거시: 문자열만 있는 경우
                        town_list.append({
                            'name': town,
                            'uuid': None,
                            'nation_name': nation_name_result,
                            'nation_uuid': nation_uuid_result
                        })

                print(f"✅ {nation_name_result} 마을 목록: {len(town_list)}개")
                return town_list

    except Exception as e:
        print(f"❌ 마을 목록 조회 오류: {e}")
        return []

def get_town_role_status(town_name: str = None, nation_uuid: str = None, town_uuid: str = None, guild=None) -> Dict:
    """마을의 역할 연동 상태를 반환"""

    # UUID 기반 조회 우선
    if nation_uuid and town_uuid:
        role_id = town_role_manager.get_role_id(nation_uuid, town_uuid)
        town_info = town_role_manager.get_town_info(nation_uuid, town_uuid)
        if town_info:
            town_name = town_info['town_name']
    # 이름 기반 조회 (하위 호환)
    elif town_name:
        role_id = town_role_manager.get_role_id_by_name(town_name)
        town_info = town_role_manager.get_town_info_by_name(town_name)
    else:
        return {
            'town_name': 'Unknown',
            'is_mapped': False,
            'role_id': None,
            'role_exists': False,
            'role_name': None,
            'role_mention': None
        }

    status = {
        'town_name': town_name,
        'is_mapped': role_id is not None,
        'role_id': role_id,
        'role_exists': False,
        'role_name': None,
        'role_mention': None,
        'town_uuid': town_uuid if town_uuid else (town_info.get('town_uuid') if town_info else None),
        'nation_uuid': nation_uuid if nation_uuid else (town_info.get('nation_uuid') if town_info else None)
    }

    if role_id and guild:
        role = guild.get_role(role_id)
        if role:
            status['role_exists'] = True
            status['role_name'] = role.name
            status['role_mention'] = role.mention

    return status

# 유틸리티 함수들
def format_town_role_info(town: str = None, nation_uuid: str = None, town_uuid: str = None, guild=None) -> str:
    """마을 역할 정보를 포맷된 문자열로 반환"""
    status = get_town_role_status(town_name=town, nation_uuid=nation_uuid, town_uuid=town_uuid, guild=guild)

    if not status['is_mapped']:
        return f"**{status['town_name']}** → ℹ️ 역할 연동 안됨"
    elif status['role_exists']:
        return f"**{status['town_name']}** → {status['role_mention']}"
    else:
        return f"**{status['town_name']}** → ⚠️ 역할 없음 (ID: {status['role_id']})"

def get_unmapped_towns(all_towns: List[Dict]) -> List[Dict]:
    """매핑되지 않은 마을 목록 반환"""
    unmapped = []
    for town in all_towns:
        nation_uuid = town.get('nation_uuid')
        town_uuid = town.get('uuid')

        if nation_uuid and town_uuid:
            if not town_role_manager.is_town_mapped(nation_uuid, town_uuid):
                unmapped.append(town)
        elif town.get('name'):
            if not town_role_manager.is_town_mapped_by_name(town['name']):
                unmapped.append(town)

    return unmapped

def get_mapped_towns_with_roles(guild) -> List[Dict]:
    """매핑된 마을들의 역할 정보 반환"""
    results = []
    for town_data in town_role_manager.get_all_mappings_flat():
        role_id = town_data['role_id']
        role = guild.get_role(role_id) if guild else None
        results.append({
            'town_name': town_data['town_name'],
            'town_uuid': town_data['town_uuid'],
            'nation_name': town_data['nation_name'],
            'nation_uuid': town_data['nation_uuid'],
            'role_id': role_id,
            'role': role,
            'role_exists': role is not None
        })
    return results

if __name__ == "__main__":
    # 테스트 코드
    print("🧪 TownRoleManager 테스트 (UUID 기반)")

    # 매핑 추가 테스트
    town_role_manager.add_mapping(
        nation_uuid="nation-uuid-123",
        town_uuid="town-uuid-456",
        role_id=123456789,
        nation_name="TestNation",
        town_name="TestTown"
    )
    print(f"매핑 개수: {town_role_manager.get_mapping_count()}")

    # 매핑 조회 테스트
    role_id = town_role_manager.get_role_id("nation-uuid-123", "town-uuid-456")
    print(f"TestTown 역할 ID: {role_id}")

    # 이름 기반 조회 테스트
    role_id_by_name = town_role_manager.get_role_id_by_name("TestTown")
    print(f"TestTown 역할 ID (이름 기반): {role_id_by_name}")

    # 상태 정보 테스트
    status = get_town_role_status(nation_uuid="nation-uuid-123", town_uuid="town-uuid-456")
    print(f"TestTown 상태: {status}")

    # 매핑 제거 테스트
    town_role_manager.remove_mapping("nation-uuid-123", "town-uuid-456")
    print(f"매핑 개수: {town_role_manager.get_mapping_count()}")

    print("✅ 테스트 완료")
