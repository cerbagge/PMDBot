# bulk_updater.py - PlanetEarth Bulk API 데이터 관리

import requests
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import threading

class BulkDataManager:
    """PlanetEarth Bulk API 데이터를 주기적으로 가져와 캐시하는 관리자"""

    def __init__(self, update_interval_minutes: int = 15):
        """
        초기화

        Args:
            update_interval_minutes: 업데이트 주기 (분)
        """
        self.update_interval = update_interval_minutes * 60  # 초 단위로 변환
        self.bulk_data: Dict[str, dict] = {}  # UUID를 키로 하는 딕셔너리
        self.last_update: Optional[datetime] = None
        self.is_running = False
        self.update_task = None
        self._lock = threading.Lock()

        print(f"✅ BulkDataManager 초기화 완료 (업데이트 주기: {update_interval_minutes}분)")

    def fetch_bulk_data(self, save_to_db: bool = True) -> bool:
        """
        Bulk API에서 데이터를 가져옴

        Args:
            save_to_db: DB에 자동 저장 여부

        Returns:
            성공 여부
        """
        try:
            print("🔄 Bulk API 데이터 가져오는 중...")
            response = requests.get(
                "https://api.planetearth.kr/resident/bulk",
                timeout=30  # 30초 타임아웃
            )
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'SUCCESS':
                print(f"⚠️ Bulk API 응답 상태가 SUCCESS가 아닙니다: {data.get('status')}")
                return False

            residents = data.get('data', [])

            # UUID를 키로 하는 딕셔너리로 변환
            with self._lock:
                self.bulk_data = {item['uuid']: item for item in residents}
                self.last_update = datetime.now()

            print(f"✅ Bulk 데이터 업데이트 완료: {len(self.bulk_data)}명의 주민 정보 로드됨")

            # DB에 저장 (옵션)
            if save_to_db:
                saved_count = self.save_to_database(residents)
                print(f"💾 DB 저장 완료: {saved_count}명")

            return True

        except requests.exceptions.Timeout:
            print("⚠️ Bulk API 타임아웃 - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.ConnectionError:
            print("⚠️ Bulk API 연결 실패 (서버 오프라인) - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Bulk API 요청 실패: {e} - 기존 캐시 데이터 사용")
            return False
        except Exception as e:
            print(f"❌ Bulk 데이터 가져오기 실패: {e}")
            return False

    def save_to_database(self, residents: List[dict]) -> int:
        """
        Bulk 데이터를 데이터베이스에 저장
        - all_players 테이블: 모든 플레이어 정보 저장
        - users/nation_history 테이블: Discord ID가 연결된 주민만 저장

        Args:
            residents: 주민 정보 리스트

        Returns:
            저장된 레코드 수
        """
        try:
            from database_manager import db_manager

            # 1. 모든 플레이어 정보를 all_players 테이블에 저장
            all_players_saved = db_manager.upsert_all_players(residents)
            print(f"  💾 all_players 테이블: {all_players_saved}명 저장")

            # 2. Discord ID가 연결된 플레이어는 기존 테이블에도 저장
            discord_linked_count = 0

            for resident in residents:
                uuid = resident.get('uuid')
                name = resident.get('name')
                nation = resident.get('nation')
                town = resident.get('town')
                nation_ranks = resident.get('nationRanks', '')
                town_ranks = resident.get('townRanks', '')

                if not uuid or not name:
                    continue

                # DB에서 해당 UUID를 가진 사용자 찾기
                user_data = db_manager.search_by_uuid(uuid)

                if user_data:
                    discord_id = user_data['discord_id']

                    # 마인크래프트 이름이 변경되었으면 업데이트
                    if user_data.get('current_minecraft_name') != name:
                        db_manager.add_or_update_user(discord_id, uuid, name)

                    # 국가 히스토리 업데이트
                    db_manager.add_nation_history(
                        discord_id=discord_id,
                        nation_name=nation if nation else None,
                        nation_uuid=None,  # Bulk에서는 nation UUID 제공 안 함
                        town_name=town if town else None,
                        town_uuid=None,  # Bulk에서는 town UUID 제공 안 함
                        nation_ranks=nation_ranks if nation_ranks else None,
                        town_ranks=town_ranks if town_ranks else None
                    )

                    discord_linked_count += 1

            print(f"  💾 Discord 연동 유저: {discord_linked_count}명 업데이트")

            return all_players_saved

        except Exception as e:
            print(f"❌ DB 저장 실패: {e}")
            return 0

    def get_resident_by_uuid(self, uuid: str) -> Optional[dict]:
        """
        UUID로 주민 정보 조회

        Args:
            uuid: Minecraft UUID

        Returns:
            주민 정보 딕셔너리 또는 None
        """
        with self._lock:
            return self.bulk_data.get(uuid)

    def get_resident_by_name(self, name: str) -> Optional[dict]:
        """
        이름으로 주민 정보 조회

        Args:
            name: Minecraft 닉네임

        Returns:
            주민 정보 딕셔너리 또는 None
        """
        with self._lock:
            for resident in self.bulk_data.values():
                if resident.get('name', '').lower() == name.lower():
                    return resident
        return None

    def get_all_residents(self) -> List[dict]:
        """
        모든 주민 정보 반환

        Returns:
            주민 정보 리스트
        """
        with self._lock:
            return list(self.bulk_data.values())

    def is_data_available(self) -> bool:
        """
        데이터가 사용 가능한지 확인

        Returns:
            데이터 사용 가능 여부
        """
        with self._lock:
            return len(self.bulk_data) > 0

    def get_data_age(self) -> Optional[timedelta]:
        """
        데이터의 경과 시간 반환

        Returns:
            마지막 업데이트 이후 경과 시간
        """
        if self.last_update:
            return datetime.now() - self.last_update
        return None

    async def start_auto_update(self):
        """자동 업데이트 시작 (비동기)"""
        if self.is_running:
            print("⚠️ Bulk 자동 업데이트가 이미 실행 중입니다")
            return

        self.is_running = True
        print(f"🚀 Bulk 자동 업데이트 시작 (주기: {self.update_interval // 60}분)")

        # 첫 데이터 로드
        await asyncio.to_thread(self.fetch_bulk_data)

        # 주기적 업데이트
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval)

                if self.is_running:
                    await asyncio.to_thread(self.fetch_bulk_data)

            except Exception as e:
                print(f"❌ Bulk 자동 업데이트 오류: {e}")
                await asyncio.sleep(60)  # 오류 발생 시 1분 후 재시도

    def stop_auto_update(self):
        """자동 업데이트 중지"""
        if self.is_running:
            self.is_running = False
            print("🛑 Bulk 자동 업데이트 중지됨")

    def get_stats(self) -> dict:
        """
        통계 정보 반환

        Returns:
            통계 딕셔너리
        """
        with self._lock:
            total_residents = len(self.bulk_data)

            # 국가별 인원 집계
            nations = {}
            towns = {}

            for resident in self.bulk_data.values():
                nation = resident.get('nation', '무소속')
                town = resident.get('town', '무소속')

                nations[nation] = nations.get(nation, 0) + 1
                towns[town] = towns.get(town, 0) + 1

            return {
                'total_residents': total_residents,
                'total_nations': len(nations),
                'total_towns': len(towns),
                'last_update': self.last_update.strftime("%Y-%m-%d %H:%M:%S") if self.last_update else "없음",
                'data_age': str(self.get_data_age()).split('.')[0] if self.last_update else "없음"
            }


# 전역 인스턴스
bulk_data_manager = BulkDataManager(update_interval_minutes=15)
print("✅ BulkDataManager 전역 인스턴스 생성됨")
