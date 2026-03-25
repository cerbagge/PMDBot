# bulk_updater.py - PlanetEarth Bulk API 데이터 관리

import requests
import asyncio
import discord
from config import config
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import threading

# 여행 시스템 import
try:
    from travel_scheduler import is_user_traveling, get_user_travel_destination
    TRAVEL_ENABLED = True
    print("✅ travel_scheduler 모듈 로드됨 (bulk_updater.py)")
except ImportError:
    is_user_traveling = lambda x: False
    get_user_travel_destination = lambda x: None
    TRAVEL_ENABLED = False
    print("⚠️ travel_scheduler 모듈을 로드할 수 없습니다 (bulk_updater.py)")

class BulkDataManager:
    """PlanetEarth Bulk API 데이터를 주기적으로 가져와 캐시하는 관리자"""

    def __init__(self, update_interval_minutes: int = 15):
        """
        초기화

        Args:
            update_interval_minutes: 업데이트 주기 (분)
        """
        self.update_interval = update_interval_minutes * 60  # 초 단위로 변환
        self.bulk_data: Dict[str, dict] = {}  # UUID를 키로 하는 딕셔너리 (residents)
        self.nation_data: Dict[str, dict] = {}  # UUID를 키로 하는 딕셔너리 (nations)
        self.town_data: Dict[str, dict] = {}  # UUID를 키로 하는 딕셔너리 (towns)
        self.last_update: Optional[datetime] = None
        self.last_nation_update: Optional[datetime] = None
        self.last_town_update: Optional[datetime] = None
        self.is_running = False
        self.update_task = None
        self._auto_update_task = None  # 자동 업데이트 asyncio Task 참조
        self._lock = threading.Lock()
        self._bot = None  # Discord bot 인스턴스
        self._pending_updates: List[dict] = []  # 비동기 Discord 업데이트 대기열

        print(f"[OK] BulkDataManager 초기화 완료 (업데이트 주기: {update_interval_minutes}분)")

    def fetch_bulk_data(self, save_to_db: bool = True, force: bool = False) -> bool:
        """
        Bulk API에서 데이터를 가져옴

        Args:
            save_to_db: DB에 자동 저장 여부
            force: 강제 업데이트 (최근 업데이트 무시)

        Returns:
            성공 여부
        """
        # 최근 1분 이내 업데이트된 경우 스킵 (중복 호출 방지)
        if not force and self.last_update:
            elapsed = (datetime.now() - self.last_update).total_seconds()
            if elapsed < 60:
                return True  # 이미 최신 데이터

        # 이미 fetch 중이면 스킵
        if hasattr(self, '_fetching') and self._fetching:
            return True

        self._fetching = True
        try:
            import time as _time
            print("🔄 Bulk API 데이터 가져오는 중...")
            response = requests.get(
                "https://api.planetearth.kr/resident/bulk",
                params={"_t": int(_time.time())},  # 캐시 버스팅
                headers={
                    "User-Agent": config.USER_AGENT,
                    "Cache-Control": "no-cache, no-store",
                    "Pragma": "no-cache",
                },
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

            print(f"[OK] Bulk 데이터 업데이트 완료: {len(self.bulk_data)}명의 주민 정보 로드됨")

            # DB에 저장 및 변경사항 감지 (옵션)
            if save_to_db:
                saved_count, pending_updates = self.save_to_database_with_changes(residents)
                print(f"[DB] 저장 완료: {saved_count}명")

                # 변경사항이 있으면 대기열에 추가
                if pending_updates:
                    self._pending_updates.extend(pending_updates)
                    print(f"[QUEUE] Discord 업데이트 대기: {len(pending_updates)}명")

            return True

        except requests.exceptions.Timeout:
            print("[WARN] Bulk API 타임아웃 - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.ConnectionError:
            print("[WARN] Bulk API 연결 실패 (서버 오프라인) - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Bulk API 요청 실패: {e} - 기존 캐시 데이터 사용")
            return False
        except Exception as e:
            print(f"[ERROR] Bulk 데이터 가져오기 실패: {e}")
            return False
        finally:
            self._fetching = False

    def set_bot(self, bot):
        """Discord bot 인스턴스 설정"""
        self._bot = bot
        print("[OK] BulkDataManager에 Discord bot 연결됨")

    def save_to_database_with_changes(self, residents: List[dict]) -> tuple:
        """
        Bulk 데이터를 데이터베이스에 저장하고 변경사항 감지
        - all_players 테이블: 모든 플레이어 정보 저장
        - users/nation_history 테이블: Discord ID가 연결된 주민만 저장
        - 변경사항이 있는 유저는 Discord 업데이트 대기열에 추가

        Args:
            residents: 주민 정보 리스트

        Returns:
            (저장된 레코드 수, 변경사항 리스트)
        """
        pending_updates = []

        try:
            from database_manager import db_manager

            # 1. 모든 플레이어 정보를 all_players 테이블에 저장
            # nation/town 이름 → UUID 매핑 구축 (캐시에서)
            nation_name_to_uuid = {}
            town_name_to_uuid = {}
            with self._lock:
                for n_uuid, n_data in self.nation_data.items():
                    n_name = n_data.get('name')
                    if n_name:
                        nation_name_to_uuid[n_name] = n_uuid
                for t_uuid, t_data in self.town_data.items():
                    t_name = t_data.get('name')
                    if t_name:
                        town_name_to_uuid[t_name] = t_uuid

            # 각 주민에 nation_uuid, town_uuid 추가
            for resident in residents:
                r_nation = resident.get('nation') or None
                r_town = resident.get('town') or None
                resident['_nation_uuid'] = nation_name_to_uuid.get(r_nation) if r_nation else None
                resident['_town_uuid'] = town_name_to_uuid.get(r_town) if r_town else None

            all_players_saved = db_manager.upsert_all_players(residents)

            # 2. Discord ID가 연결된 플레이어는 기존 테이블에도 저장
            discord_linked_count = 0

            user_errors = 0
            for resident in residents:
                uuid = resident.get('uuid')
                name = resident.get('name')
                # 빈 문자열을 None으로 정규화 (API는 빈 문자열 반환, DB는 None 저장)
                nation = resident.get('nation') or None
                town = resident.get('town') or None
                nation_ranks = resident.get('nationRanks') or None
                town_ranks = resident.get('townRanks') or None

                if not uuid or not name:
                    continue

                # DB에서 해당 UUID를 가진 사용자 찾기
                user_data = db_manager.search_by_uuid(uuid)

                if user_data:
                  try:
                    discord_id = user_data['discord_id']
                    old_name = user_data.get('current_minecraft_name')

                    # 현재 국가/마을 정보 조회
                    current_nation_info = db_manager.get_current_nation(discord_id)
                    old_nation = current_nation_info.get('nation_name') if current_nation_info else None
                    old_nation_uuid = current_nation_info.get('nation_uuid') if current_nation_info else None
                    old_town = current_nation_info.get('town_name') if current_nation_info else None
                    old_town_uuid = current_nation_info.get('town_uuid') if current_nation_info else None

                    # 새 국가/마을 UUID 조회 (메모리 캐시에서)
                    nation_uuid = None
                    town_uuid = None

                    if nation:
                        nation_info = self.get_nation_by_name(nation)
                        if nation_info:
                            nation_uuid = nation_info.get('uuid')

                    if town:
                        town_info = self.get_town_by_name(town)
                        if town_info:
                            town_uuid = town_info.get('uuid')

                    # 이전 국가/마을 UUID가 DB에 없으면 캐시에서 조회 + DB에 보충 저장
                    backfill_nation_uuid = None
                    backfill_town_uuid = None

                    if not old_nation_uuid and old_nation:
                        old_nation_info = self.get_nation_by_name(old_nation)
                        if old_nation_info:
                            old_nation_uuid = old_nation_info.get('uuid')
                            backfill_nation_uuid = old_nation_uuid

                    if not old_town_uuid and old_town:
                        old_town_info = self.get_town_by_name(old_town)
                        if old_town_info:
                            old_town_uuid = old_town_info.get('uuid')
                            backfill_town_uuid = old_town_uuid

                    # 캐시에서 찾은 UUID를 DB에 보충 저장 (다음 조회 시 중복 캐시 조회 방지)
                    if backfill_nation_uuid or backfill_town_uuid:
                        db_manager.backfill_history_uuid(discord_id, backfill_nation_uuid, backfill_town_uuid)

                    # 변경사항 감지
                    name_changed = old_name != name

                    # 국가 변경 감지 (UUID 기반 - 이름 변경은 무시)
                    if nation_uuid or old_nation_uuid:
                        # UUID 비교 (한쪽이 None이면 국가 가입/탈퇴)
                        nation_changed = (nation_uuid != old_nation_uuid)
                        if not nation_changed and old_nation != nation:
                            print(f"  [RENAME] 국가 이름 변경 감지 (UUID 동일): {old_nation} -> {nation} (Discord ID: {discord_id})")
                    else:
                        # 둘 다 UUID 없음 (둘 다 무소속이거나 데이터 없음)
                        nation_changed = (old_nation != nation)

                    # 마을 변경 감지 (UUID 기반 - 이름 변경은 무시)
                    if town_uuid or old_town_uuid:
                        town_changed = (town_uuid != old_town_uuid)
                        if not town_changed and old_town != town:
                            print(f"  [RENAME] 마을 이름 변경 감지 (UUID 동일): {old_town} -> {town} (Discord ID: {discord_id})")
                    else:
                        town_changed = (old_town != town)

                    # 마인크래프트 이름이 변경되었으면 업데이트
                    if name_changed:
                        db_manager.add_or_update_user(discord_id, uuid, name)
                        print(f"  [NAME] {old_name} -> {name} (Discord ID: {discord_id})")

                    # 국가 히스토리 업데이트
                    db_manager.add_nation_history(
                        discord_id=discord_id,
                        nation_name=nation,
                        nation_uuid=nation_uuid,
                        town_name=town,
                        town_uuid=town_uuid,
                        nation_ranks=nation_ranks,
                        town_ranks=town_ranks
                    )

                    # users 테이블의 현재 국가/마을 정보 업데이트
                    db_manager.update_user_nation_info(
                        discord_id=discord_id,
                        nation=nation,
                        nation_uuid=nation_uuid,
                        town=town,
                        town_uuid=town_uuid
                    )

                    # 변경사항이 있으면 Discord 업데이트 대기열에 추가 (마을 변경 포함)
                    if name_changed or nation_changed or town_changed:
                        # joinedTownAt을 bulk 데이터에서 가져옴 (0이면 None 처리)
                        _joined_town_at = resident.get('joinedTownAt')
                        if _joined_town_at == 0:
                            _joined_town_at = None

                        pending_updates.append({
                            'discord_id': discord_id,
                            'new_name': name,
                            'old_name': old_name,
                            'new_nation': nation,
                            'new_nation_uuid': nation_uuid,
                            'old_nation': old_nation,
                            'old_nation_uuid': old_nation_uuid,
                            'new_town': town,
                            'new_town_uuid': town_uuid,
                            'old_town': old_town,
                            'old_town_uuid': old_town_uuid,
                            'name_changed': name_changed,
                            'nation_changed': nation_changed,
                            'town_changed': town_changed,
                            'nation_ranks': nation_ranks,
                            'town_ranks': town_ranks,
                            'joined_town_at': _joined_town_at
                        })

                        # user_changes 큐에 삽입 (다른 봇 전달용)
                        change_type = []
                        if name_changed:
                            change_type.append('name')
                        if nation_changed:
                            change_type.append('nation')
                        if town_changed:
                            change_type.append('town')
                        try:
                            db_manager.insert_user_change(
                                discord_id=discord_id,
                                change_type=','.join(change_type),
                                old_name=old_name, new_name=name,
                                old_nation=old_nation, new_nation=nation,
                                old_nation_uuid=old_nation_uuid, new_nation_uuid=nation_uuid,
                                old_town=old_town, new_town=town,
                                old_town_uuid=old_town_uuid, new_town_uuid=town_uuid,
                            )
                        except Exception:
                            pass

                    discord_linked_count += 1

                  except Exception as e:
                    user_errors += 1
                    if user_errors <= 5:
                        print(f"[ERROR] 유저 업데이트 실패 ({name}, Discord: {user_data.get('discord_id')}): {e}")
                    elif user_errors == 6:
                        print(f"[ERROR] 추가 유저 업데이트 오류 로그 생략...")

            if user_errors > 0:
                print(f"[WARN] 유저 업데이트 중 {user_errors}건 오류 발생 (정상 처리: {discord_linked_count}명)")

            return all_players_saved, pending_updates

        except Exception as e:
            print(f"[ERROR] DB 저장 실패: {e}")
            import traceback
            traceback.print_exc()
            return 0, []

    def save_to_database(self, residents: List[dict]) -> int:
        """하위 호환성을 위한 래퍼 함수"""
        saved_count, _ = self.save_to_database_with_changes(residents)
        return saved_count

    def fetch_nation_bulk_data(self, save_to_db: bool = True, force: bool = False) -> bool:
        """
        Nation Bulk API에서 데이터를 가져옴

        Args:
            save_to_db: DB에 자동 저장 여부
            force: 강제 업데이트 (최근 업데이트 무시)

        Returns:
            성공 여부
        """
        # 최근 1분 이내 업데이트된 경우 스킵 (중복 호출 방지)
        if not force and self.last_nation_update:
            elapsed = (datetime.now() - self.last_nation_update).total_seconds()
            if elapsed < 60:
                return True  # 이미 최신 데이터

        # 이미 fetch 중이면 스킵
        if hasattr(self, '_fetching_nation') and self._fetching_nation:
            return True

        self._fetching_nation = True
        try:
            print("🔄 Nation Bulk API 데이터 가져오는 중...")
            response = requests.get(
                "https://api.planetearth.kr/nation/bulk",
                headers={"User-Agent": config.USER_AGENT},
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'SUCCESS':
                print(f"⚠️ Nation Bulk API 응답 상태가 SUCCESS가 아닙니다: {data.get('status')}")
                return False

            nations = data.get('data', [])

            # UUID를 키로 하는 딕셔너리로 변환
            with self._lock:
                self.nation_data = {item['uuid']: item for item in nations}
                self.last_nation_update = datetime.now()

            print(f"[OK] Nation Bulk 데이터 업데이트 완료: {len(self.nation_data)}개의 국가 정보 로드됨")

            # BASE_NATION UUID로 국가 이름 변경 자동 감지 및 갱신 + JSON 저장
            try:
                base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)
                if base_nation_uuid and base_nation_uuid in self.nation_data:
                    nation_info = self.nation_data[base_nation_uuid]
                    api_nation_name = nation_info.get('name')
                    name_changed = api_nation_name and api_nation_name != config.BASE_NATION
                    if name_changed:
                        old_name = config.BASE_NATION
                        config.BASE_NATION = api_nation_name
                        print(f"[AUTO] BASE_NATION 이름 자동 갱신: {old_name} -> {api_nation_name} (UUID 동일: {base_nation_uuid[:8]}...)")
                    # JSON 파일 갱신 (이름 변경 여부와 관계없이 최신 정보 저장)
                    config.save_base_nation_json(nation_info)
            except Exception as e:
                print(f"[WARN] BASE_NATION 자동 갱신 실패: {e}")

            # DB에 저장 (옵션)
            if save_to_db:
                from database_manager import db_manager
                saved_count = db_manager.upsert_all_nations(nations)
                print(f"[DB] 국가 저장 완료: {saved_count}개")

            return True

        except requests.exceptions.Timeout:
            print("[WARN] Nation Bulk API 타임아웃 - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.ConnectionError:
            print("[WARN] Nation Bulk API 연결 실패 (서버 오프라인) - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Nation Bulk API 요청 실패: {e} - 기존 캐시 데이터 사용")
            return False
        except Exception as e:
            print(f"[ERROR] Nation Bulk 데이터 가져오기 실패: {e}")
            return False
        finally:
            self._fetching_nation = False

    def fetch_town_bulk_data(self, save_to_db: bool = True, force: bool = False) -> bool:
        """
        Town Bulk API에서 데이터를 가져옴

        Args:
            save_to_db: DB에 자동 저장 여부
            force: 강제 업데이트 (최근 업데이트 무시)

        Returns:
            성공 여부
        """
        # 최근 1분 이내 업데이트된 경우 스킵 (중복 호출 방지)
        if not force and self.last_town_update:
            elapsed = (datetime.now() - self.last_town_update).total_seconds()
            if elapsed < 60:
                return True  # 이미 최신 데이터

        # 이미 fetch 중이면 스킵
        if hasattr(self, '_fetching_town') and self._fetching_town:
            return True

        self._fetching_town = True
        try:
            print("🔄 Town Bulk API 데이터 가져오는 중...")
            response = requests.get(
                "https://api.planetearth.kr/town/bulk",
                headers={"User-Agent": config.USER_AGENT},
                timeout=30
            )
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'SUCCESS':
                print(f"⚠️ Town Bulk API 응답 상태가 SUCCESS가 아닙니다: {data.get('status')}")
                return False

            towns = data.get('data', [])

            # UUID를 키로 하는 딕셔너리로 변환
            with self._lock:
                self.town_data = {item['uuid']: item for item in towns}
                self.last_town_update = datetime.now()

            print(f"[OK] Town Bulk 데이터 업데이트 완료: {len(self.town_data)}개의 마을 정보 로드됨")

            # DB에 저장 (옵션)
            if save_to_db:
                from database_manager import db_manager
                saved_count = db_manager.upsert_all_towns(towns)
                print(f"[DB] 마을 저장 완료: {saved_count}개")

            return True

        except requests.exceptions.Timeout:
            print("[WARN] Town Bulk API 타임아웃 - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.ConnectionError:
            print("[WARN] Town Bulk API 연결 실패 (서버 오프라인) - 기존 캐시 데이터 사용")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Town Bulk API 요청 실패: {e} - 기존 캐시 데이터 사용")
            return False
        except Exception as e:
            print(f"[ERROR] Town Bulk 데이터 가져오기 실패: {e}")
            return False
        finally:
            self._fetching_town = False

    def fetch_all_bulk_data(self, save_to_db: bool = True, force: bool = False) -> bool:
        """
        모든 Bulk API 데이터를 가져옴 (nation, town 먼저 -> resident)
        nation/town을 먼저 로드해야 resident 처리 시 UUID 조회 가능

        Args:
            save_to_db: DB에 자동 저장 여부
            force: 강제 업데이트 (최근 업데이트 무시)

        Returns:
            성공 여부 (모두 성공 시 True)
        """
        # 1. nation/town 먼저 로드 (resident에서 UUID 조회에 필요)
        nation_result = self.fetch_nation_bulk_data(save_to_db=save_to_db, force=force)
        town_result = self.fetch_town_bulk_data(save_to_db=save_to_db, force=force)

        # 2. resident 로드 (nation/town UUID를 캐시에서 조회)
        resident_result = self.fetch_bulk_data(save_to_db=save_to_db, force=force)

        return resident_result and nation_result and town_result

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

    def get_nation_by_uuid(self, uuid: str) -> Optional[dict]:
        """
        UUID로 국가 정보 조회

        Args:
            uuid: 국가 UUID

        Returns:
            국가 정보 딕셔너리 또는 None
        """
        with self._lock:
            return self.nation_data.get(uuid)

    def get_nation_by_name(self, name: str) -> Optional[dict]:
        """
        이름으로 국가 정보 조회

        Args:
            name: 국가 이름

        Returns:
            국가 정보 딕셔너리 또는 None
        """
        with self._lock:
            for nation in self.nation_data.values():
                if nation.get('name', '').lower() == name.lower():
                    return nation
        return None

    def get_all_nations(self) -> List[dict]:
        """
        모든 국가 정보 반환

        Returns:
            국가 정보 리스트
        """
        with self._lock:
            return list(self.nation_data.values())

    def get_town_by_uuid(self, uuid: str) -> Optional[dict]:
        """
        UUID로 마을 정보 조회

        Args:
            uuid: 마을 UUID

        Returns:
            마을 정보 딕셔너리 또는 None
        """
        with self._lock:
            return self.town_data.get(uuid)

    def get_town_by_name(self, name: str) -> Optional[dict]:
        """
        이름으로 마을 정보 조회

        Args:
            name: 마을 이름

        Returns:
            마을 정보 딕셔너리 또는 None
        """
        with self._lock:
            for town in self.town_data.values():
                if town.get('name', '').lower() == name.lower():
                    return town
        return None

    def get_all_towns(self) -> List[dict]:
        """
        모든 마을 정보 반환

        Returns:
            마을 정보 리스트
        """
        with self._lock:
            return list(self.town_data.values())

    def get_towns_by_nation(self, nation_name: str) -> List[dict]:
        """
        국가에 속한 마을들 조회

        Args:
            nation_name: 국가 이름

        Returns:
            마을 정보 리스트
        """
        with self._lock:
            result = []
            for town in self.town_data.values():
                if town.get('nation', '').lower() == nation_name.lower():
                    result.append(town)
            return result

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
            print("[WARN] Bulk 자동 업데이트가 이미 실행 중입니다")
            return

        self.is_running = True
        print(f"[START] Bulk 자동 업데이트 시작 (주기: {self.update_interval // 60}분)")

        # 첫 데이터 로드 (resident, nation, town 모두)
        await asyncio.to_thread(self.fetch_all_bulk_data)

        # 첫 로드 후 Discord 업데이트 처리
        await self.process_discord_updates()

        # 주기적 업데이트
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval)

                if self.is_running:
                    await asyncio.to_thread(self.fetch_all_bulk_data)
                    # Discord 업데이트 처리
                    await self.process_discord_updates()

            except Exception as e:
                print(f"[ERROR] Bulk 자동 업데이트 오류: {e}")
                await asyncio.sleep(60)  # 오류 발생 시 1분 후 재시도

    async def process_discord_updates(self):
        """
        대기 중인 Discord 업데이트 처리
        - 마인크래프트 닉네임 변경 시 Discord 서버 별명 자동 변경
        - 국가 변경 시 역할 자동 변경 (설정에 따라)
        - 콜사인이 있으면 서버 별명에 포함
        - 2주 경과 뉴비 역할 자동 제거
        """
        if not self._bot:
            return

        # 먼저 만료된 뉴비 역할 처리 (업데이트 유무와 관계없이 항상 실행)
        await self._process_expired_newbies()

        if not self._pending_updates:
            return

        try:
            # 길드 가져오기
            guild = self._bot.get_guild(config.GUILD_ID)
            if not guild:
                print("[WARN] Discord 서버를 찾을 수 없습니다")
                return

            # 콜사인 매니저 가져오기 (있으면)
            try:
                from callsign_manager import callsign_manager
            except ImportError:
                callsign_manager = None

            updates_processed = 0
            updates_failed = 0

            # 대기열에서 업데이트 처리
            while self._pending_updates:
                update = self._pending_updates.pop(0)
                discord_id = update['discord_id']

                try:
                    member = guild.get_member(discord_id)
                    if not member:
                        continue

                    # 1. 닉네임 변경 처리
                    if update.get('name_changed'):
                        new_mc_name = update['new_name']
                        new_nation = update.get('new_nation')

                        # 역할 양식 조회
                        role_format = None
                        if callsign_manager:
                            # 역할 우선순위 순으로 정렬
                            sorted_roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
                            for role in sorted_roles:
                                format_str = callsign_manager.get_role_format(role.id)
                                if format_str:
                                    role_format = format_str
                                    print(f"  [FORMAT] {member.name}: 역할 양식 적용 - {role.name}")
                                    break

                        # 콜사인 조회
                        callsign = None
                        if callsign_manager:
                            callsign = callsign_manager.get_callsign(discord_id)

                        # 새 닉네임 생성
                        if role_format and callsign_manager:
                            # 역할 양식이 있으면 양식 적용
                            new_nick = callsign_manager.apply_format_to_nickname(
                                role_format,
                                mc_id=new_mc_name,
                                nation=new_nation,
                                town=update.get('new_town'),
                                callsign=callsign,
                                discord_joined_at=member.joined_at
                            )
                        elif callsign:
                            # 역할 양식 없으면 기본 형식
                            new_nick = f"{new_mc_name} | {callsign}"
                        else:
                            new_nick = new_mc_name

                        # 32자 제한 확인
                        if len(new_nick) > 32:
                            new_nick = new_nick[:32]

                        # 닉네임 변경 시도
                        if member.nick != new_nick:
                            try:
                                await member.edit(nick=new_nick)
                                print(f"  [NICK] {member.name}: {member.nick} -> {new_nick}")
                                updates_processed += 1
                            except Exception as e:
                                print(f"  [FAIL] {member.name} 닉네임 변경 실패: {e}")
                                updates_failed += 1

                    # 2. 국가 변경 시 역할 처리 (옵션)
                    if update.get('nation_changed'):
                        # 여행 중인 사용자는 역할 변경 건너뛰기
                        if TRAVEL_ENABLED and is_user_traveling(discord_id):
                            travel_dest = get_user_travel_destination(discord_id)
                            print(f"  [TRAVEL] {member.name}: 여행 중 (목적지: {travel_dest}) - 역할 변경 건너뛰기")
                            continue

                        new_nation = update['new_nation']
                        old_nation = update['old_nation']
                        new_nation_uuid = update.get('new_nation_uuid')
                        old_nation_uuid = update.get('old_nation_uuid')

                        # BASE_NATION과 비교 (UUID 기반)
                        base_nation = config.BASE_NATION
                        base_nation_uuid = getattr(config, 'BASE_NATION_UUID', None)
                        success_role_id = config.SUCCESS_ROLE_ID

                        # 뉴비 역할 ID (설정에서 가져오기)
                        try:
                            from newbie_config_manager import newbie_config_manager
                            NEWBIE_ROLE_ID = newbie_config_manager.get_newbie_role()
                        except ImportError:
                            NEWBIE_ROLE_ID = None

                        # UUID가 없으면 캐시에서 조회 + DB 보충 저장
                        if not new_nation_uuid and new_nation:
                            _info = self.get_nation_by_name(new_nation)
                            if _info:
                                new_nation_uuid = _info.get('uuid')
                                # users 테이블에 UUID 보충
                                try:
                                    from database_manager import db_manager as _db
                                    _db.update_user_nation_info(discord_id, nation=new_nation, nation_uuid=new_nation_uuid)
                                except Exception:
                                    pass
                        if not old_nation_uuid and old_nation:
                            _info = self.get_nation_by_name(old_nation)
                            if _info:
                                old_nation_uuid = _info.get('uuid')
                                # nation_history에 UUID 보충
                                try:
                                    from database_manager import db_manager as _db
                                    _db.backfill_history_uuid(discord_id, nation_uuid=old_nation_uuid)
                                except Exception:
                                    pass

                        # UUID 기반 비교 (UUID 없으면 이름 fallback)
                        if new_nation_uuid:
                            is_in_base_nation = (new_nation_uuid == base_nation_uuid)
                        else:
                            is_in_base_nation = (new_nation and base_nation and new_nation.lower() == base_nation.lower())

                        if old_nation_uuid:
                            was_in_base_nation = (old_nation_uuid == base_nation_uuid)
                        else:
                            was_in_base_nation = (old_nation and base_nation and old_nation.lower() == base_nation.lower())

                        # DB 매니저 가져오기
                        try:
                            from database_manager import db_manager
                        except ImportError:
                            db_manager = None

                        # 2-1. BASE_NATION에 새로 가입한 경우 -> joinedTownAt 조회 + 뉴비 판정 + 알림 전송
                        if is_in_base_nation and not was_in_base_nation:
                            # DB에서 기존 가입일 확인 (이미 값이 있으면 뉴비로 안 침)
                            existing_joined = None
                            if db_manager:
                                try:
                                    existing_joined = db_manager.get_red_mafia_joined(discord_id)
                                except Exception:
                                    pass

                            if existing_joined is not None:
                                # 이미 가입일이 있는 사용자 - 뉴비로 취급하지 않음
                                days_since = (datetime.now() - existing_joined).days
                                print(f"  [NEWBIE_SKIP] {member.name}: 이미 가입일 존재 ({days_since}일 전) - 뉴비 아님")
                                is_newbie = False
                                is_returning_member = True  # 알림 전송 방지
                            else:
                                # 이전에 7일 이상 소속된 적이 있는지 확인 (복귀 멤버)
                                is_returning_member = False
                                if db_manager:
                                    try:
                                        is_returning_member = db_manager.was_member_of_nation(
                                            discord_id, base_nation, min_days=7
                                        )
                                        if is_returning_member:
                                            print(f"  [RETURNING] {member.name}: 복귀 멤버 (이전 7일 이상 소속) - 뉴비 역할 제외")
                                    except Exception as e:
                                        print(f"  [WARN] 복귀 멤버 확인 실패: {e}")

                                # joinedTownAt: bulk 데이터에서 가져옴 (개별 API 호출 불필요)
                                joined_town_at_ts = update.get('joined_town_at')
                                joined_at_dt = None
                                is_newbie = False

                                if joined_town_at_ts:
                                    try:
                                        from datetime import datetime as _dt
                                        joined_at_dt = _dt.fromtimestamp(joined_town_at_ts / 1000)
                                        days_since_join = (_dt.now() - joined_at_dt).days
                                        is_newbie = days_since_join <= 14
                                        print(f"  [NEWBIE_CHECK] {member.name}: joinedTownAt={joined_at_dt.strftime('%Y-%m-%d')} ({days_since_join}일 전) → {'뉴비' if is_newbie else '뉴비 아님'}")
                                    except Exception as parse_err:
                                        print(f"  [WARN] joinedTownAt 파싱 실패: {parse_err}")
                                        is_newbie = True  # 파싱 실패 시 기본 뉴비 처리
                                else:
                                    is_newbie = True  # joinedTownAt 없으면 기본 뉴비 처리
                                    print(f"  [NEWBIE_CHECK] {member.name}: joinedTownAt 없음 - 기본 뉴비 처리")

                                # 뉴비 역할 부여 (복귀 멤버가 아니고 뉴비인 경우만)
                                newbie_role = guild.get_role(NEWBIE_ROLE_ID) if NEWBIE_ROLE_ID else None
                                if newbie_role and newbie_role not in member.roles and not is_returning_member and is_newbie:
                                    try:
                                        await member.add_roles(newbie_role)
                                        print(f"  [NEWBIE] {member.name}: 뉴비 역할 부여 (국가 가입: {new_nation})")
                                        updates_processed += 1
                                    except Exception as e:
                                        print(f"  [FAIL] {member.name} 뉴비 역할 부여 실패: {e}")
                                        updates_failed += 1

                                # DB에 가입일 저장 (joinedTownAt 또는 현재 시간)
                                if db_manager:
                                    save_dt = joined_at_dt if joined_at_dt else datetime.now()
                                    db_manager.set_red_mafia_joined(discord_id, save_dt)
                                    print(f"  [DB] {member.name}: 가입일 저장됨 (joinedTownAt: {save_dt.strftime('%Y-%m-%d %H:%M')})")

                            # 뉴비 알림 채널에 메시지 전송 (복귀 멤버가 아니고 뉴비인 경우에만)
                            if not is_returning_member and is_newbie:
                                await self._send_newbie_notification(
                                    guild=guild,
                                    member=member,
                                    discord_id=discord_id,
                                    mc_name=update['new_name'],
                                    old_nation=old_nation,
                                    new_nation=new_nation
                                )
                                # 뉴비 목록 메시지 업데이트
                                try:
                                    from commands.admin.scheduler.newbie_check import update_newbie_list_message
                                    await update_newbie_list_message(self._bot)
                                except Exception as e:
                                    print(f"  [WARN] 뉴비 목록 업데이트 실패: {e}")

                        # 2-1-2. 이미 BASE_NATION에 있지만 가입일이 없는 경우 -> bulk 데이터의 joinedTownAt으로 가입일 설정
                        elif is_in_base_nation and was_in_base_nation:
                            if db_manager:
                                existing_joined = db_manager.get_red_mafia_joined(discord_id)
                                if existing_joined is None:
                                    # bulk 데이터에서 joinedTownAt 가져옴 (개별 API 호출 불필요)
                                    _joined_ts = update.get('joined_town_at')
                                    _joined_dt = None

                                    if _joined_ts:
                                        try:
                                            _joined_dt = datetime.fromtimestamp(_joined_ts / 1000)
                                        except Exception:
                                            pass

                                    save_dt = _joined_dt if _joined_dt else datetime.now()
                                    db_manager.set_red_mafia_joined(discord_id, save_dt)
                                    print(f"  [DB] {member.name}: 가입일 보정 저장됨 (joinedTownAt: {save_dt.strftime('%Y-%m-%d %H:%M')})")

                        # 2-2. BASE_NATION을 떠난 경우 -> 역할 제거 + 뉴비 역할 제거 + DB 초기화
                        if was_in_base_nation and not is_in_base_nation:
                            # SUCCESS_ROLE 제거
                            if config.REMOVE_ROLE_IF_WRONG_NATION and success_role_id:
                                success_role = guild.get_role(success_role_id)
                                if success_role and success_role in member.roles:
                                    try:
                                        await member.remove_roles(success_role)
                                        print(f"  [ROLE] {member.name}: 역할 제거 (국가 변경: {old_nation} -> {new_nation})")
                                        updates_processed += 1
                                    except Exception as e:
                                        print(f"  [FAIL] {member.name} 역할 제거 실패: {e}")
                                        updates_failed += 1

                            # 뉴비 역할 제거 (2주 체크)
                            newbie_role = guild.get_role(NEWBIE_ROLE_ID) if NEWBIE_ROLE_ID else None
                            newbie_removed = False
                            should_remove_newbie = True

                            if newbie_role and newbie_role in member.roles and db_manager:
                                existing_joined = db_manager.get_red_mafia_joined(discord_id)
                                if existing_joined:
                                    days_since_join = (datetime.now() - existing_joined).days
                                    if days_since_join <= 14:
                                        should_remove_newbie = False
                                        print(f"  [NEWBIE] {member.name}: 뉴비 기간 내 ({days_since_join}일) - 역할 유지")

                            if should_remove_newbie:
                                if newbie_role and newbie_role in member.roles:
                                    try:
                                        await member.remove_roles(newbie_role)
                                        print(f"  [NEWBIE] {member.name}: 뉴비 역할 제거 (국가 탈퇴)")
                                        updates_processed += 1
                                        newbie_removed = True
                                    except Exception as e:
                                        print(f"  [FAIL] {member.name} 뉴비 역할 제거 실패: {e}")
                                        updates_failed += 1

                                # DB에서 가입일 초기화 (뉴비 기간 만료 시에만)
                                if db_manager:
                                    db_manager.clear_red_mafia_joined(discord_id)
                                    print(f"  [DB] {member.name}: Red Mafia 가입일 초기화됨")

                            # 뉴비 목록 메시지 업데이트
                            if newbie_removed:
                                try:
                                    from commands.admin.scheduler.newbie_check import update_newbie_list_message
                                    await update_newbie_list_message(self._bot)
                                except Exception as e:
                                    print(f"  [WARN] 뉴비 목록 업데이트 실패: {e}")

                    # 3. 마을 변경 시 역할 처리
                    if update.get('town_changed'):
                        new_town = update.get('new_town')
                        old_town = update.get('old_town')

                        # 여행 중인 사용자는 역할 변경 건너뛰기
                        if TRAVEL_ENABLED and is_user_traveling(discord_id):
                            print(f"  [TRAVEL] {member.name}: 여행 중 - 마을 역할 변경 건너뛰기")
                        else:
                            try:
                                from town_role_manager import town_role_manager as _trm
                                if _trm:
                                    # 이전 마을 역할 제거
                                    all_mapped_towns = _trm.get_all_mappings_flat()
                                    for mapping in all_mapped_towns:
                                        mapped_town = mapping['town_name']
                                        mapped_role_id = mapping['role_id']
                                        if mapped_town != new_town:
                                            mapped_role = guild.get_role(mapped_role_id)
                                            if mapped_role and mapped_role in member.roles:
                                                await member.remove_roles(mapped_role)
                                                print(f"  [TOWN] {member.name}: {mapped_town} 마을 역할 제거 (마을 변경)")
                                                updates_processed += 1

                                    # 새 마을 역할 부여
                                    if new_town and new_town not in ("무소속", "❌"):
                                        role_id = _trm.get_role_id_by_name(new_town)
                                        if role_id:
                                            town_role = guild.get_role(role_id)
                                            if town_role and town_role not in member.roles:
                                                await member.add_roles(town_role)
                                                print(f"  [TOWN] {member.name}: {new_town} 마을 역할 부여")
                                                updates_processed += 1
                            except ImportError:
                                pass
                            except Exception as e:
                                print(f"  [FAIL] {member.name} 마을 역할 처리 실패: {e}")
                                updates_failed += 1

                        # 마을 변경 시 닉네임도 갱신 (양식에 마을 포함될 수 있음)
                        if not update.get('name_changed'):
                            try:
                                mc_name = update['new_name']
                                new_nation = update.get('new_nation')

                                role_format = None
                                if callsign_manager:
                                    sorted_roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
                                    for role in sorted_roles:
                                        format_str = callsign_manager.get_role_format(role.id)
                                        if format_str:
                                            role_format = format_str
                                            break

                                callsign = callsign_manager.get_callsign(discord_id) if callsign_manager else None

                                if role_format and callsign_manager:
                                    new_nick = callsign_manager.apply_format_to_nickname(
                                        role_format,
                                        mc_id=mc_name,
                                        nation=new_nation,
                                        town=new_town,
                                        callsign=callsign,
                                        discord_joined_at=member.joined_at
                                    )
                                elif callsign:
                                    new_nick = f"{mc_name} | {callsign}"
                                else:
                                    new_nick = mc_name

                                if len(new_nick) > 32:
                                    new_nick = new_nick[:32]

                                if member.nick != new_nick:
                                    await member.edit(nick=new_nick)
                                    print(f"  [NICK] {member.name}: {member.nick} -> {new_nick} (마을 변경)")
                                    updates_processed += 1
                            except Exception as e:
                                print(f"  [FAIL] {member.name} 닉네임 갱신 실패 (마을 변경): {e}")
                                updates_failed += 1

                except Exception as e:
                    print(f"  [ERROR] Discord 업데이트 실패 (ID: {discord_id}): {e}")
                    updates_failed += 1

                # API 레이트 리밋 방지
                await asyncio.sleep(0.5)

            if updates_processed > 0 or updates_failed > 0:
                print(f"[DONE] Discord 업데이트 완료: 성공 {updates_processed}건, 실패 {updates_failed}건")

        except Exception as e:
            print(f"[ERROR] Discord 업데이트 처리 중 오류: {e}")
            import traceback
            traceback.print_exc()

    async def _send_newbie_notification(self, guild, member, discord_id: int, mc_name: str,
                                         old_nation: str, new_nation: str):
        """
        뉴비 알림 채널에 상세 정보 전송

        Args:
            guild: Discord 길드
            member: Discord 멤버
            discord_id: 디스코드 ID
            mc_name: 마인크래프트 닉네임
            old_nation: 이전 국가
            new_nation: 새 국가
        """
        try:
            from newbie_config_manager import newbie_config_manager
            from database_manager import db_manager
            from datetime import datetime

            # 알림 채널 확인
            channel_id = newbie_config_manager.get_notification_channel()
            if not channel_id:
                return

            channel = guild.get_channel(channel_id)
            if not channel:
                print(f"[WARN] 뉴비 알림 채널을 찾을 수 없습니다: {channel_id}")
                return

            # 사용자 정보 조회
            user_info = db_manager.get_user_info(discord_id)
            name_history = db_manager.get_name_history(discord_id, limit=5)
            nation_history = db_manager.get_nation_history(discord_id, limit=3)

            # 임베드 생성
            embed = discord.Embed(
                title="🆕 새로운 뉴비가 Red Mafia에 가입했습니다!",
                color=0x00ff00,
                timestamp=datetime.now()
            )

            # 기본 정보
            embed.add_field(
                name="👤 디스코드",
                value=f"{member.mention}\n`{member.name}`",
                inline=True
            )

            embed.add_field(
                name="🎮 마인크래프트",
                value=f"`{mc_name}`",
                inline=True
            )

            # 서버 최초 가입일 (first_seen)
            if user_info and user_info.get('first_seen'):
                first_seen = user_info['first_seen']
                if isinstance(first_seen, str):
                    first_seen = datetime.fromisoformat(first_seen)
                first_seen_str = first_seen.strftime('%Y-%m-%d %H:%M')
                days_ago = (datetime.now() - first_seen).days
                embed.add_field(
                    name="📅 서버 최초 가입",
                    value=f"`{first_seen_str}`\n({days_ago}일 전)",
                    inline=True
                )

            # 이전 국가/마을 정보
            if old_nation:
                # 이전 마을 정보도 가져오기
                old_town = None
                if nation_history and len(nation_history) > 0:
                    # 가장 최근 기록의 이전 기록 찾기
                    for hist in nation_history:
                        if hist.get('nation_name') == old_nation:
                            old_town = hist.get('town_name')
                            break

                prev_info = f"**국가:** `{old_nation}`"
                if old_town:
                    prev_info += f"\n**마을:** `{old_town}`"
                embed.add_field(
                    name="🔙 이전 소속",
                    value=prev_info,
                    inline=False
                )
            else:
                embed.add_field(
                    name="🔙 이전 소속",
                    value="무소속 (첫 국가 가입)",
                    inline=False
                )

            # 마크 닉네임 히스토리
            if name_history and len(name_history) > 1:
                history_lines = []
                for idx, hist in enumerate(name_history[:5]):
                    name = hist.get('minecraft_name', '알 수 없음')
                    changed_at = hist.get('changed_at')
                    if changed_at:
                        if isinstance(changed_at, str):
                            changed_at = datetime.fromisoformat(changed_at)
                        date_str = changed_at.strftime('%Y-%m-%d')
                    else:
                        date_str = "?"

                    if idx == 0:
                        history_lines.append(f"• `{name}` (현재)")
                    else:
                        history_lines.append(f"• `{name}` ({date_str})")

                embed.add_field(
                    name="📜 닉네임 히스토리",
                    value="\n".join(history_lines),
                    inline=False
                )

            # 국가 히스토리 (이전 국가들)
            if nation_history and len(nation_history) > 1:
                nation_lines = []
                for idx, hist in enumerate(nation_history[:3]):
                    nation = hist.get('nation_name') or '무소속'
                    town = hist.get('town_name') or '없음'
                    changed_at = hist.get('changed_at')
                    if changed_at:
                        if isinstance(changed_at, str):
                            changed_at = datetime.fromisoformat(changed_at)
                        date_str = changed_at.strftime('%Y-%m-%d')
                    else:
                        date_str = "?"

                    if idx == 0:
                        nation_lines.append(f"• `{nation}` / `{town}` (현재)")
                    else:
                        nation_lines.append(f"• `{nation}` / `{town}` ({date_str})")

                embed.add_field(
                    name="🏛️ 국가/마을 히스토리",
                    value="\n".join(nation_lines),
                    inline=False
                )

            embed.set_footer(text="뉴비 역할은 2주 후 자동으로 제거됩니다")

            # 썸네일 설정 (Discord 프로필)
            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)

            # 핑할 역할 목록 가져오기
            ping_roles = newbie_config_manager.get_ping_roles()

            # 스레드 이름 생성
            thread_name = f"🆕 {mc_name}"
            if len(thread_name) > 100:
                thread_name = thread_name[:100]

            # 이미 같은 이름의 스레드가 있는지 확인 (중복 방지)
            existing_thread = None
            try:
                # 활성 스레드에서 검색
                for thread in channel.threads:
                    if thread.name == thread_name or thread.name.startswith(f"🆕 {mc_name}"):
                        existing_thread = thread
                        break

                # 아카이브된 스레드에서도 검색
                if not existing_thread:
                    async for thread in channel.archived_threads(limit=50):
                        if thread.name == thread_name or thread.name.startswith(f"🆕 {mc_name}"):
                            existing_thread = thread
                            break
            except Exception as search_error:
                print(f"  [WARN] 스레드 검색 중 오류: {search_error}")

            # 이미 스레드가 있으면 생성하지 않음
            if existing_thread:
                print(f"  [INFO] 뉴비 스레드가 이미 존재함: {existing_thread.name} - 스레드 생성 건너뜀")
                return

            try:
                # 공개 스레드 생성
                thread = await channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread
                )

                # 멘션 메시지 생성
                mentions = [member.mention]  # 뉴비 본인
                if ping_roles:
                    for role_id in ping_roles:
                        role = guild.get_role(role_id)
                        if role:
                            mentions.append(role.mention)

                ping_content = " ".join(mentions)

                # 스레드에 임베드 + 멘션 메시지 전송
                await thread.send(content=ping_content, embed=embed)

                print(f"  [NOTIFY] 뉴비 스레드 생성됨: {thread.name}")

            except discord.Forbidden:
                # 스레드 생성 권한이 없으면 일반 메시지로 전송
                print(f"  [WARN] 스레드 생성 권한 없음, 일반 메시지로 전송")
                mentions = [member.mention]
                if ping_roles:
                    for role_id in ping_roles:
                        role = guild.get_role(role_id)
                        if role:
                            mentions.append(role.mention)

                ping_content = " ".join(mentions)
                await channel.send(content=ping_content, embed=embed)

            except Exception as thread_error:
                print(f"  [ERROR] 스레드 생성 실패: {thread_error}")
                # 스레드 생성 실패 시 일반 메시지로 전송
                await channel.send(embed=embed)

            print(f"  [NOTIFY] 뉴비 알림 전송됨: {member.name} -> #{channel.name}")

        except ImportError:
            # newbie_config_manager가 없으면 무시
            pass
        except Exception as e:
            print(f"[ERROR] 뉴비 알림 전송 실패: {e}")
            import traceback
            traceback.print_exc()

    async def _process_expired_newbies(self):
        """
        2주가 지난 뉴비들의 역할을 자동으로 제거
        """
        try:
            from database_manager import db_manager

            # 길드 가져오기
            guild = self._bot.get_guild(config.GUILD_ID)
            if not guild:
                return

            base_nation = config.BASE_NATION
            if not base_nation:
                return

            # 뉴비 역할 ID (설정에서 가져오기)
            try:
                from newbie_config_manager import newbie_config_manager
                NEWBIE_ROLE_ID = newbie_config_manager.get_newbie_role()
            except ImportError:
                NEWBIE_ROLE_ID = None

            if not NEWBIE_ROLE_ID:
                return

            newbie_role = guild.get_role(NEWBIE_ROLE_ID)
            if not newbie_role:
                return

            # 만료된 뉴비 목록 조회 (2주 경과)
            expired_newbies = db_manager.get_expired_newbies(base_nation, days=14)

            if not expired_newbies:
                return

            removed_count = 0
            failed_count = 0

            for newbie in expired_newbies:
                discord_id = newbie['discord_id']
                member = guild.get_member(discord_id)

                if not member:
                    continue

                # 뉴비 역할이 있으면 제거
                if newbie_role in member.roles:
                    try:
                        await member.remove_roles(newbie_role)
                        print(f"  [NEWBIE_EXPIRE] {member.name}: 뉴비 역할 제거 (2주 경과)")
                        removed_count += 1
                    except Exception as e:
                        print(f"  [FAIL] {member.name} 뉴비 역할 제거 실패: {e}")
                        failed_count += 1

                    # API 레이트 리밋 방지
                    await asyncio.sleep(0.5)

            if removed_count > 0 or failed_count > 0:
                print(f"[NEWBIE] 만료된 뉴비 역할 처리: 성공 {removed_count}건, 실패 {failed_count}건")
                # 뉴비 목록 메시지 업데이트
                if removed_count > 0:
                    try:
                        from commands.admin.scheduler.newbie_check import update_newbie_list_message
                        await update_newbie_list_message(self._bot)
                    except Exception as e:
                        print(f"  [WARN] 뉴비 목록 업데이트 실패: {e}")

        except Exception as e:
            print(f"[ERROR] 만료된 뉴비 처리 중 오류: {e}")

    def stop_auto_update(self):
        """자동 업데이트 중지"""
        if self.is_running:
            self.is_running = False

            # 자동 업데이트 태스크 취소
            if self._auto_update_task and not self._auto_update_task.done():
                self._auto_update_task.cancel()
                print("[STOP] Bulk 자동 업데이트 태스크 취소됨")

            print("[STOP] Bulk 자동 업데이트 중지됨")

    def get_stats(self) -> dict:
        """
        통계 정보 반환

        Returns:
            통계 딕셔너리
        """
        with self._lock:
            total_residents = len(self.bulk_data)
            total_nations = len(self.nation_data)
            total_towns = len(self.town_data)

            # 국가별 인원 집계 (resident 데이터 기준)
            nations_from_residents = {}
            towns_from_residents = {}

            for resident in self.bulk_data.values():
                nation = resident.get('nation', '무소속')
                town = resident.get('town', '무소속')

                nations_from_residents[nation] = nations_from_residents.get(nation, 0) + 1
                towns_from_residents[town] = towns_from_residents.get(town, 0) + 1

            return {
                'total_residents': total_residents,
                'total_nations': total_nations,
                'total_towns': total_towns,
                'nations_from_residents': len(nations_from_residents),
                'towns_from_residents': len(towns_from_residents),
                'last_update': self.last_update.strftime("%Y-%m-%d %H:%M:%S") if self.last_update else "없음",
                'last_nation_update': self.last_nation_update.strftime("%Y-%m-%d %H:%M:%S") if self.last_nation_update else "없음",
                'last_town_update': self.last_town_update.strftime("%Y-%m-%d %H:%M:%S") if self.last_town_update else "없음",
                'data_age': str(self.get_data_age()).split('.')[0] if self.last_update else "없음"
            }


# 전역 인스턴스
bulk_data_manager = BulkDataManager(update_interval_minutes=15)
print("[OK] BulkDataManager 전역 인스턴스 생성됨")
