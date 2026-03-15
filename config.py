import os
import shutil
import json
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Union

BASE_NATION_JSON = "data/base_nation.json"

class Config:
    """환경변수를 중앙에서 관리하는 클래스"""

    def __init__(self):
        # .env 파일 로드 (우선순위: 현재 디렉토리 > 상위 디렉토리)
        env_loaded = False
        for env_path in ['.env', '../.env']:
            if os.path.exists(env_path):
                load_dotenv(env_path)
                print(f"🔧 환경변수 로드: {env_path}")
                env_loaded = True
                break

        if not env_loaded:
            # .env 파일이 없을 때 .env.example에서 자동 생성
            env_created = self._create_env_from_example()
            if not env_created:
                print("⚠️ .env 파일을 찾을 수 없습니다. 시스템 환경변수를 사용합니다.")

        # 환경변수 로드 및 검증
        self._load_and_validate()

    def _create_env_from_example(self) -> bool:
        """
        .env.example 파일을 복사하여 .env 파일 생성

        Returns:
            bool: 파일 생성 성공 여부
        """
        for example_path, target_path in [('.env.example', '.env'), ('../.env.example', '../.env')]:
            if os.path.exists(example_path):
                shutil.copy(example_path, target_path)
                print("📝 .env 파일이 생성되었습니다.")
                print("⚠️  .env 파일을 수정해주세요. (실제 값으로 변경 필요)")
                load_dotenv(target_path)
                return True

        return False
    
    def _load_and_validate(self):
        """환경변수 로드 및 검증"""
        # Discord 토큰
        self.DISCORD_TOKEN = self._get_env("DISCORD_TOKEN") or self._get_env("BOT_TOKEN")
        if not self.DISCORD_TOKEN:
            raise ValueError("❌ DISCORD_TOKEN 또는 BOT_TOKEN이 필요합니다.")

        # API 설정
        self.MC_API_BASE = self._get_env("MC_API_BASE", "https://api.planetearth.kr")
        
        # Discord 서버 설정
        self.GUILD_ID = self._get_env_int("GUILD_ID")
        self.SUCCESS_ROLE_ID = self._get_env_int("SUCCESS_ROLE_ID")
        self.SUCCESS_ROLE_ID_OUT = self._get_env_int("SUCCESS_ROLE_ID_OUT", 0)  # 외국인 역할 ID 추가
        
        # 채널 설정
        self.LOG_CHANNEL_ID = self._get_env_int("LOG_CHANNEL_ID")
        self.SUCCESS_CHANNEL_ID = self._get_env_int("SUCCESS_CHANNEL_ID")
        self.FAILURE_CHANNEL_ID = self._get_env_int("FAILURE_CHANNEL_ID")
        self.WELCOME_CHANNEL_ID = self._get_env_int("WELCOME_CHANNEL_ID")
        
        # 자동 실행 설정
        self.AUTO_ROLE_IDS = self._get_env("AUTO_ROLE_IDS", "")
        self.AUTO_EXECUTION_DAY = self._get_env_int("AUTO_EXECUTION_DAY", 6)
        self.AUTO_EXECUTION_HOUR = self._get_env_int("AUTO_EXECUTION_HOUR", 2)
        self.AUTO_EXECUTION_MINUTE = self._get_env_int("AUTO_EXECUTION_MINUTE", 0)

        # 범위 유효성 검사
        if not (0 <= self.AUTO_EXECUTION_HOUR <= 23):
            raise ValueError("❌ AUTO_EXECUTION_HOUR는 0~23 사이여야 합니다.")
        if not (0 <= self.AUTO_EXECUTION_MINUTE <= 59):
            raise ValueError("❌ AUTO_EXECUTION_MINUTE는 0~59 사이여야 합니다.")
        
        # 추가 설정
        self.AUTO_ADD_NEW_MEMBERS = self._get_env_bool("AUTO_ADD_NEW_MEMBERS", True)

        # 인증 관련 설정
        self.BASE_NATION = self._get_env("BASE_NATION", "Red_Mafia")
        self.BASE_NATION_UUID = None  # JSON 또는 API에서 자동 설정
        self._load_base_nation_json()  # JSON에서 UUID 등 로드
        self.REMOVE_ROLE_IF_WRONG_NATION = self._get_env_bool("REMOVE_ROLE_IF_WRONG_NATION", True)
        self.AUTO_ASSIGN_NATION_ROLES = self._get_env_bool("AUTO_ASSIGN_NATION_ROLES", False)

        # 데이터베이스 설정
        self.DB_TYPE = self._get_env("DB_TYPE", "sqlite").lower()
        if self.DB_TYPE in ("postgresql", "postgres", "pg"):
            self.DB_TYPE = "postgresql"
        else:
            self.DB_TYPE = "sqlite"

        # 필수 항목 검증
        self._validate_config()
    
    def _get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """환경변수 가져오기"""
        return os.getenv(key, default)
    
    def _get_env_int(self, key: str, default: Optional[int] = None) -> Optional[int]:
        """환경변수를 int로 변환하여 가져오기"""
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            print(f"⚠️ {key}의 값 '{value}'을(를) 정수로 변환할 수 없습니다. 기본값 사용: {default}")
            return default
    
    def _get_env_bool(self, key: str, default: bool = False) -> bool:
        """환경변수를 bool로 변환하여 가져오기"""
        value = os.getenv(key, "").lower()
        return value in ("true", "1", "yes", "on") if value else default
    
    def _validate_config(self):
        """필수 환경변수 검증"""
        required_vars = {
            "DISCORD_TOKEN": self.DISCORD_TOKEN,
            "GUILD_ID": self.GUILD_ID,
            "SUCCESS_ROLE_ID": self.SUCCESS_ROLE_ID,
            "SUCCESS_CHANNEL_ID": self.SUCCESS_CHANNEL_ID,
            "FAILURE_CHANNEL_ID": self.FAILURE_CHANNEL_ID
        }
        
        missing_vars = []
        for var_name, var_value in required_vars.items():
            if var_value is None:
                missing_vars.append(var_name)
        
        if missing_vars:
            print(f"❌ 필수 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}")
            raise ValueError(f"필수 환경변수가 누락되었습니다: {', '.join(missing_vars)}")
    
    def print_config_status(self):
        """설정 상태 출력"""
        print("📋 환경변수 상태:")
        config_items = [
            ("DISCORD_TOKEN", "✅ 설정됨" if self.DISCORD_TOKEN else "❌ 누락"),
            ("MC_API_BASE", self.MC_API_BASE),
            ("GUILD_ID", self.GUILD_ID),
            ("SUCCESS_ROLE_ID", self.SUCCESS_ROLE_ID),
            ("SUCCESS_ROLE_ID_OUT", self.SUCCESS_ROLE_ID_OUT),  # 외국인 역할 ID 추가
            ("SUCCESS_CHANNEL_ID", self.SUCCESS_CHANNEL_ID),
            ("FAILURE_CHANNEL_ID", self.FAILURE_CHANNEL_ID),
            ("WELCOME_CHANNEL_ID", self.WELCOME_CHANNEL_ID),
            ("AUTO_ADD_NEW_MEMBERS", self.AUTO_ADD_NEW_MEMBERS),
            ("BASE_NATION", self.BASE_NATION),
            ("BASE_NATION_UUID", self.BASE_NATION_UUID or "⏳ API 조회 대기"),
            ("REMOVE_ROLE_IF_WRONG_NATION", self.REMOVE_ROLE_IF_WRONG_NATION),
            ("AUTO_ASSIGN_NATION_ROLES", self.AUTO_ASSIGN_NATION_ROLES),
            ("DB_TYPE", self.DB_TYPE),
        ]

        for name, value in config_items:
            print(f"   - {name}: {value if value is not None else '❌ 누락'}")
    
    def get_auto_role_ids(self) -> list[int]:
        """자동 역할 ID 리스트 반환"""
        if not self.AUTO_ROLE_IDS:
            return []

        role_ids = []
        for role_id_str in self.AUTO_ROLE_IDS.split(','):
            role_id_str = role_id_str.strip()
            if role_id_str:
                try:
                    role_ids.append(int(role_id_str))
                except ValueError:
                    print(f"⚠️ 잘못된 역할 ID: {role_id_str}")

        return role_ids

    def _load_base_nation_json(self):
        """JSON 파일에서 BASE_NATION 정보 로드"""
        if not os.path.exists(BASE_NATION_JSON):
            return

        try:
            with open(BASE_NATION_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # .env의 BASE_NATION과 JSON의 이름/UUID가 일치하는지 확인
            json_name = data.get('name')
            json_uuid = data.get('uuid')

            if not json_uuid:
                return

            # .env에서 BASE_NATION 이름이 변경됐으면 JSON 무시 (다시 API 조회)
            if json_name and self.BASE_NATION and json_name.lower() != self.BASE_NATION.lower():
                print(f"⚠️ .env BASE_NATION({self.BASE_NATION}) ≠ JSON({json_name}) → API에서 재조회 예정")
                return

            self.BASE_NATION_UUID = json_uuid
            # API에서 가져온 정확한 이름으로 갱신
            if json_name:
                self.BASE_NATION = json_name
            print(f"📂 base_nation.json 로드: {self.BASE_NATION} (UUID: {json_uuid[:8]}...)")
        except Exception as e:
            print(f"⚠️ base_nation.json 로드 실패: {e}")

    def save_base_nation_json(self, nation_data: dict = None):
        """BASE_NATION 정보를 JSON 파일로 저장"""
        os.makedirs("data", exist_ok=True)

        data = {
            "name": self.BASE_NATION,
            "uuid": self.BASE_NATION_UUID,
            "updated_at": datetime.now().isoformat(),
        }

        # API에서 받은 상세 정보가 있으면 추가
        if nation_data:
            for key in ('king', 'capital', 'residents', 'towns', 'allies', 'enemies', 'board'):
                if key in nation_data:
                    data[key] = nation_data[key]

        try:
            with open(BASE_NATION_JSON, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 base_nation.json 저장: {self.BASE_NATION} (UUID: {self.BASE_NATION_UUID[:8]}...)")
        except Exception as e:
            print(f"⚠️ base_nation.json 저장 실패: {e}")

    async def initialize_base_nation_uuid(self):
        """
        BASE_NATION UUID를 초기화.
        JSON 캐시에서 이미 로드됐으면 스킵, 없으면 API 조회 후 JSON 저장.
        """
        if self.BASE_NATION_UUID:
            print(f"✅ BASE_NATION_UUID 준비 완료: {self.BASE_NATION_UUID}")
            return True

        if not self.BASE_NATION:
            print("⚠️ BASE_NATION이 설정되지 않음")
            return False

        try:
            from pe_api_utils import pe_api

            print(f"🔍 BASE_NATION API 조회 중: {self.BASE_NATION}")
            nation_data = await pe_api.get_nation_by_name(self.BASE_NATION)

            if nation_data and 'uuid' in nation_data:
                self.BASE_NATION_UUID = nation_data['uuid']
                # API에서 받은 정확한 이름으로 갱신
                self.BASE_NATION = nation_data.get('name', self.BASE_NATION)
                self.save_base_nation_json(nation_data)
                print(f"✅ BASE_NATION 초기화 완료: {self.BASE_NATION} ({self.BASE_NATION_UUID})")
                return True
            else:
                print(f"❌ BASE_NATION UUID 조회 실패: {self.BASE_NATION}")
                return False

        except Exception as e:
            print(f"❌ BASE_NATION UUID 초기화 실패: {e}")
            return False

    async def set_base_nation(self, nation_name: str) -> tuple[bool, str, Optional[str]]:
        """서버의 기본 국가를 변경합니다 (관리자 전용)"""
        try:
            from pe_api_utils import pe_api

            print(f"🔍 국가 정보 조회 중: {nation_name}")
            nation_data = await pe_api.get_nation_by_name(nation_name)

            if not nation_data:
                return False, f"❌ '{nation_name}' 국가를 찾을 수 없습니다. 정확한 국가명을 입력해주세요.", None

            if 'uuid' not in nation_data:
                return False, f"❌ '{nation_name}' 국가의 UUID를 가져올 수 없습니다.", None

            old_nation = self.BASE_NATION

            self.BASE_NATION = nation_data.get('name', nation_name)
            self.BASE_NATION_UUID = nation_data['uuid']
            self.save_base_nation_json(nation_data)

            print(f"✅ BASE_NATION 변경: {old_nation} → {self.BASE_NATION}")

            return True, f"✅ 서버 국가가 **{self.BASE_NATION}**로 변경되었습니다!\n`UUID: {self.BASE_NATION_UUID}`", self.BASE_NATION_UUID

        except Exception as e:
            print(f"❌ BASE_NATION 설정 실패: {e}")
            import traceback
            traceback.print_exc()
            return False, f"❌ 국가 설정 중 오류가 발생했습니다: {str(e)}", None


# 전역 설정 인스턴스
try:
    config = Config()
    print("✅ 환경변수 설정 완료")
    config.print_config_status()
except Exception as e:
    print(f"❌ 환경변수 설정 실패: {e}")
    raise