# pe_api_utils.py
"""
Planet Earth API 유틸리티 함수
국가 및 마을 정보를 UUID 기반으로 관리
"""

import aiohttp
from typing import Optional, Dict, List
from config import config

class PEApiError(Exception):
    """PE API 관련 에러"""
    pass

class PEApiUtils:
    """Planet Earth API 유틸리티 클래스"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or config.MC_API_BASE
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Dict] = {}  # UUID 캐시

    async def _get_session(self) -> aiohttp.ClientSession:
        """aiohttp 세션 가져오기 (재사용)"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """세션 종료"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_nation_by_name(self, nation_name: str) -> Optional[Dict]:
        """
        국가 이름으로 국가 정보 조회

        Args:
            nation_name: 국가 이름 (어떤 언어든 가능)

        Returns:
            {
                'uuid': str,
                'name': str,  # 기본 이름
                'names': [str, ...],  # 모든 언어의 이름들
                'capital': str,
                'residents': int,
                ...
            }
            실패 시 None
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/nation?name={nation_name}"

            print(f"🌐 PE API 요청: {url}")

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    response_data = await response.json()

                    # 디버그: 응답 구조 출력
                    print(f"📥 PE API 응답 (처음 200자): {str(response_data)[:200]}")

                    # 응답 데이터 검증
                    if not response_data:
                        print(f"⚠️ 빈 응답: {nation_name}")
                        return None

                    # PE API는 {status: "SUCCESS", data: [...]} 형식으로 응답
                    if isinstance(response_data, dict) and 'data' in response_data:
                        data_list = response_data.get('data', [])
                        if not data_list or len(data_list) == 0:
                            print(f"⚠️ 빈 data 배열: {nation_name}")
                            return None
                        data = data_list[0]  # 첫 번째 결과 사용
                        print(f"✅ data 배열에서 첫 번째 결과 추출")
                    elif isinstance(response_data, list):
                        # 레거시: 직접 리스트로 응답하는 경우
                        if len(response_data) == 0:
                            print(f"⚠️ 빈 결과 리스트: {nation_name}")
                            return None
                        data = response_data[0]
                        print(f"📝 리스트에서 첫 번째 결과 선택")
                    else:
                        # 단일 객체 응답
                        data = response_data

                    if 'uuid' not in data:
                        print(f"⚠️ 국가 정보에 UUID가 없음: {nation_name}")
                        print(f"   응답 키들: {list(data.keys())}")
                        return None

                    # 캐시에 저장
                    uuid = data['uuid']
                    self._cache[f"nation:{uuid}"] = data
                    self._cache[f"nation:name:{nation_name.lower()}"] = data

                    print(f"✅ 국가 정보 조회 성공: {nation_name} (UUID: {uuid})")
                    return data

                elif response.status == 404:
                    print(f"❌ 국가를 찾을 수 없음: {nation_name}")
                    return None
                elif response.status == 502 or response.status == 503:
                    print(f"🔴 PE API 서버 응답 없음 (status {response.status})")
                    raise PEApiError(f"PE API 서버에 연결할 수 없습니다 (HTTP {response.status}). 서버가 일시적으로 닫혀있을 수 있습니다.")
                else:
                    print(f"❌ PE API 에러 (status {response.status}): {nation_name}")
                    return None

        except aiohttp.ClientConnectorError as e:
            print(f"🔴 PE API 서버 연결 실패: {e}")
            raise PEApiError("PE API 서버에 연결할 수 없습니다. 서버가 닫혀있거나 네트워크 문제가 있을 수 있습니다.")
        except aiohttp.ServerTimeoutError as e:
            print(f"⏱️ PE API 서버 타임아웃: {e}")
            raise PEApiError("PE API 서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.")
        except aiohttp.ClientError as e:
            print(f"❌ 네트워크 에러 (국가 조회): {e}")
            raise PEApiError(f"네트워크 오류가 발생했습니다: {str(e)}")
        except PEApiError:
            # 이미 처리된 에러는 그대로 전달
            raise
        except Exception as e:
            print(f"❌ 예상치 못한 에러 (국가 조회): {e}")
            return None

    async def get_town_by_name(self, town_name: str) -> Optional[Dict]:
        """
        마을 이름으로 마을 정보 조회

        Args:
            town_name: 마을 이름 (어떤 언어든 가능)

        Returns:
            {
                'uuid': str,
                'name': str,  # 기본 이름
                'names': [str, ...],  # 모든 언어의 이름들
                'nation': str,  # 소속 국가 UUID
                'mayor': str,
                'residents': int,
                ...
            }
            실패 시 None
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/town?name={town_name}"

            print(f"🌐 PE API 요청: {url}")

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    response_data = await response.json()

                    # 디버그: 응답 구조 출력
                    print(f"📥 PE API 응답 (처음 200자): {str(response_data)[:200]}")

                    # 응답 데이터 검증
                    if not response_data:
                        print(f"⚠️ 빈 응답: {town_name}")
                        return None

                    # PE API는 {status: "SUCCESS", data: [...]} 형식으로 응답
                    if isinstance(response_data, dict) and 'data' in response_data:
                        data_list = response_data.get('data', [])
                        if not data_list or len(data_list) == 0:
                            print(f"⚠️ 빈 data 배열: {town_name}")
                            return None
                        data = data_list[0]  # 첫 번째 결과 사용
                        print(f"✅ data 배열에서 첫 번째 결과 추출")
                    elif isinstance(response_data, list):
                        # 레거시: 직접 리스트로 응답하는 경우
                        if len(response_data) == 0:
                            print(f"⚠️ 빈 결과 리스트: {town_name}")
                            return None
                        data = response_data[0]
                        print(f"📝 리스트에서 첫 번째 결과 선택")
                    else:
                        # 단일 객체 응답
                        data = response_data

                    if 'uuid' not in data:
                        print(f"⚠️ 마을 정보에 UUID가 없음: {town_name}")
                        print(f"   응답 키들: {list(data.keys())}")
                        return None

                    # 캐시에 저장
                    uuid = data['uuid']
                    self._cache[f"town:{uuid}"] = data
                    self._cache[f"town:name:{town_name.lower()}"] = data

                    print(f"✅ 마을 정보 조회 성공: {town_name} (UUID: {uuid})")
                    return data

                elif response.status == 404:
                    print(f"❌ 마을을 찾을 수 없음: {town_name}")
                    return None
                elif response.status == 502 or response.status == 503:
                    print(f"🔴 PE API 서버 응답 없음 (status {response.status})")
                    raise PEApiError(f"PE API 서버에 연결할 수 없습니다 (HTTP {response.status}). 서버가 일시적으로 닫혀있을 수 있습니다.")
                else:
                    print(f"❌ PE API 에러 (status {response.status}): {town_name}")
                    return None

        except aiohttp.ClientConnectorError as e:
            print(f"🔴 PE API 서버 연결 실패: {e}")
            raise PEApiError("PE API 서버에 연결할 수 없습니다. 서버가 닫혀있거나 네트워크 문제가 있을 수 있습니다.")
        except aiohttp.ServerTimeoutError as e:
            print(f"⏱️ PE API 서버 타임아웃: {e}")
            raise PEApiError("PE API 서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.")
        except aiohttp.ClientError as e:
            print(f"❌ 네트워크 에러 (마을 조회): {e}")
            raise PEApiError(f"네트워크 오류가 발생했습니다: {str(e)}")
        except PEApiError:
            raise
        except Exception as e:
            print(f"❌ 예상치 못한 에러 (마을 조회): {e}")
            return None

    async def get_nation_by_uuid(self, nation_uuid: str) -> Optional[Dict]:
        """
        UUID로 국가 정보 조회

        Args:
            nation_uuid: 국가 UUID

        Returns:
            국가 정보 딕셔너리 또는 None
        """
        # 캐시 확인
        cache_key = f"nation:{nation_uuid}"
        if cache_key in self._cache:
            print(f"💾 캐시에서 국가 정보 로드: {nation_uuid}")
            return self._cache[cache_key]

        try:
            session = await self._get_session()
            url = f"{self.base_url}/nation?uuid={nation_uuid}"

            print(f"🌐 PE API 요청: {url}")

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    self._cache[cache_key] = data
                    print(f"✅ 국가 정보 조회 성공 (UUID): {nation_uuid}")
                    return data
                else:
                    print(f"❌ 국가 조회 실패 (UUID): {nation_uuid}")
                    return None

        except Exception as e:
            print(f"❌ 국가 조회 에러 (UUID): {e}")
            return None

    async def get_town_by_uuid(self, town_uuid: str) -> Optional[Dict]:
        """
        UUID로 마을 정보 조회

        Args:
            town_uuid: 마을 UUID

        Returns:
            마을 정보 딕셔너리 또는 None
        """
        # 캐시 확인
        cache_key = f"town:{town_uuid}"
        if cache_key in self._cache:
            print(f"💾 캐시에서 마을 정보 로드: {town_uuid}")
            return self._cache[cache_key]

        try:
            session = await self._get_session()
            url = f"{self.base_url}/town?uuid={town_uuid}"

            print(f"🌐 PE API 요청: {url}")

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    self._cache[cache_key] = data
                    print(f"✅ 마을 정보 조회 성공 (UUID): {town_uuid}")
                    return data
                else:
                    print(f"❌ 마을 조회 실패 (UUID): {town_uuid}")
                    return None

        except Exception as e:
            print(f"❌ 마을 조회 에러 (UUID): {e}")
            return None

    def get_all_nation_names(self, nation_data: Dict) -> List[str]:
        """
        국가 데이터에서 모든 언어의 이름 추출

        Args:
            nation_data: get_nation_by_name 등으로 받은 국가 데이터

        Returns:
            모든 언어의 국가 이름 리스트 (소문자 변환)
        """
        names = []

        # 기본 이름
        if 'name' in nation_data:
            names.append(nation_data['name'].lower())

        # 다국어 이름들
        if 'names' in nation_data and isinstance(nation_data['names'], list):
            names.extend([n.lower() for n in nation_data['names'] if n])

        # 중복 제거
        return list(set(names))

    def get_all_town_names(self, town_data: Dict) -> List[str]:
        """
        마을 데이터에서 모든 언어의 이름 추출

        Args:
            town_data: get_town_by_name 등으로 받은 마을 데이터

        Returns:
            모든 언어의 마을 이름 리스트 (소문자 변환)
        """
        names = []

        # 기본 이름
        if 'name' in town_data:
            names.append(town_data['name'].lower())

        # 다국어 이름들
        if 'names' in town_data and isinstance(town_data['names'], list):
            names.extend([n.lower() for n in town_data['names'] if n])

        # 중복 제거
        return list(set(names))

    def clear_cache(self):
        """캐시 초기화"""
        self._cache.clear()
        print("🗑️ PE API 캐시 초기화")

# 전역 인스턴스
pe_api = PEApiUtils()

# 테스트
if __name__ == "__main__":
    import asyncio

    async def test():
        print("🧪 PE API Utils 테스트")

        # 국가 조회 테스트
        nation = await pe_api.get_nation_by_name("Red_Mafia")
        if nation:
            print(f"국가 UUID: {nation.get('uuid')}")
            print(f"모든 이름: {pe_api.get_all_nation_names(nation)}")

        # 마을 조회 테스트
        town = await pe_api.get_town_by_name("TestTown")
        if town:
            print(f"마을 UUID: {town.get('uuid')}")
            print(f"모든 이름: {pe_api.get_all_town_names(town)}")

        await pe_api.close()
        print("✅ 테스트 완료")

    asyncio.run(test())
