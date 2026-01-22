# bulk_updater.py - PlanetEarth Bulk API 데이터 관리

import requests
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, TYPE_CHECKING
import threading

if TYPE_CHECKING:
    import discord

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
            all_players_saved = db_manager.upsert_all_players(residents)

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
                    old_name = user_data.get('current_minecraft_name')

                    # 현재 국가 정보 조회
                    current_nation_info = db_manager.get_current_nation(discord_id)
                    old_nation = current_nation_info.get('nation_name') if current_nation_info else None

                    # 변경사항 감지
                    name_changed = old_name != name
                    nation_changed = old_nation != nation

                    # 마인크래프트 이름이 변경되었으면 업데이트
                    if name_changed:
                        db_manager.add_or_update_user(discord_id, uuid, name)
                        print(f"  [NAME] {old_name} -> {name} (Discord ID: {discord_id})")

                    # 국가 히스토리 업데이트
                    db_manager.add_nation_history(
                        discord_id=discord_id,
                        nation_name=nation if nation else None,
                        nation_uuid=None,
                        town_name=town if town else None,
                        town_uuid=None,
                        nation_ranks=nation_ranks if nation_ranks else None,
                        town_ranks=town_ranks if town_ranks else None
                    )

                    # 변경사항이 있으면 Discord 업데이트 대기열에 추가
                    if name_changed or nation_changed:
                        pending_updates.append({
                            'discord_id': discord_id,
                            'new_name': name,
                            'old_name': old_name,
                            'new_nation': nation,
                            'old_nation': old_nation,
                            'name_changed': name_changed,
                            'nation_changed': nation_changed
                        })

                    discord_linked_count += 1

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
            print("[WARN] Bulk 자동 업데이트가 이미 실행 중입니다")
            return

        self.is_running = True
        print(f"[START] Bulk 자동 업데이트 시작 (주기: {self.update_interval // 60}분)")

        # 첫 데이터 로드
        await asyncio.to_thread(self.fetch_bulk_data)

        # 첫 로드 후 Discord 업데이트 처리
        await self.process_discord_updates()

        # 주기적 업데이트
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval)

                if self.is_running:
                    await asyncio.to_thread(self.fetch_bulk_data)
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
        """
        if not self._bot or not self._pending_updates:
            return

        try:
            from config import config

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

                        # 콜사인이 있으면 포함
                        callsign = None
                        if callsign_manager:
                            callsign = callsign_manager.get_callsign(discord_id)

                        # 새 닉네임 생성
                        if callsign:
                            new_nick = f"[{callsign}] {new_mc_name}"
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
                    if update.get('nation_changed') and config.REMOVE_ROLE_IF_WRONG_NATION:
                        new_nation = update['new_nation']
                        old_nation = update['old_nation']

                        # BASE_NATION과 비교
                        base_nation = config.BASE_NATION
                        success_role_id = config.SUCCESS_ROLE_ID

                        if success_role_id:
                            success_role = guild.get_role(success_role_id)
                            if success_role:
                                has_role = success_role in member.roles
                                is_in_base_nation = (new_nation == base_nation) if new_nation else False

                                # 국가를 떠났는데 역할이 있으면 제거
                                if has_role and not is_in_base_nation:
                                    try:
                                        await member.remove_roles(success_role)
                                        print(f"  [ROLE] {member.name}: 역할 제거 (국가 변경: {old_nation} -> {new_nation})")
                                        updates_processed += 1
                                    except Exception as e:
                                        print(f"  [FAIL] {member.name} 역할 제거 실패: {e}")
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

    def stop_auto_update(self):
        """자동 업데이트 중지"""
        if self.is_running:
            self.is_running = False
            print("[STOP] Bulk 자동 업데이트 중지됨")

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
print("[OK] BulkDataManager 전역 인스턴스 생성됨")
