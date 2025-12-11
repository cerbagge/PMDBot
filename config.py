import os
from dotenv import load_dotenv
from typing import Optional, Union

class Config:
    """환경변수를 중앙에서 관리하는 클래스"""
    
    def __init__(self):
        # .env 파일 로드 (우선순위: 현재 디렉토리 > 상위 디렉토리)
        for env_path in ['.env', '../.env']:
            if os.path.exists(env_path):
                load_dotenv(env_path)
                print(f"🔧 환경변수 로드: {env_path}")
                break
        else:
            print("⚠️ .env 파일을 찾을 수 없습니다. 시스템 환경변수를 사용합니다.")
        
        # 환경변수 로드 및 검증
        self._load_and_validate()
    
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
        self.BASE_NATION = self._get_env("BASE_NATION", "Red_Mafia")  # Legacy: 이름 기반
        self.BASE_NATION_UUID = self._get_env("BASE_NATION_UUID", None)  # UUID 기반 (우선)
        self.REMOVE_ROLE_IF_WRONG_NATION = self._get_env_bool("REMOVE_ROLE_IF_WRONG_NATION", True)
        self.AUTO_ASSIGN_NATION_ROLES = self._get_env_bool("AUTO_ASSIGN_NATION_ROLES", False)
        
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
            ("BASE_NATION_UUID", self.BASE_NATION_UUID or "❌ 미설정 (이름으로 fallback)"),
            ("REMOVE_ROLE_IF_WRONG_NATION", self.REMOVE_ROLE_IF_WRONG_NATION),
            ("AUTO_ASSIGN_NATION_ROLES", self.AUTO_ASSIGN_NATION_ROLES),
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

    async def initialize_base_nation_uuid(self):
        """
        BASE_NATION 이름을 사용해서 UUID 조회 및 설정
        BASE_NATION_UUID가 없고 BASE_NATION만 있을 때 자동으로 UUID를 찾음
        """
        if self.BASE_NATION_UUID:
            print(f"✅ BASE_NATION_UUID 이미 설정됨: {self.BASE_NATION_UUID}")
            return True

        if not self.BASE_NATION:
            print("⚠️ BASE_NATION이 설정되지 않음")
            return False

        try:
            from pe_api_utils import pe_api

            print(f"🔍 BASE_NATION 이름으로 UUID 조회 중: {self.BASE_NATION}")
            nation_data = await pe_api.get_nation_by_name(self.BASE_NATION)

            if nation_data and 'uuid' in nation_data:
                self.BASE_NATION_UUID = nation_data['uuid']
                print(f"✅ BASE_NATION_UUID 설정 완료: {self.BASE_NATION_UUID}")

                # .env 파일 업데이트 제안 (선택적)
                print(f"💡 .env 파일에 추가 권장: BASE_NATION_UUID={self.BASE_NATION_UUID}")
                return True
            else:
                print(f"❌ BASE_NATION UUID 조회 실패: {self.BASE_NATION}")
                return False

        except Exception as e:
            print(f"❌ BASE_NATION UUID 초기화 실패: {e}")
            return False

    async def set_base_nation(self, nation_name: str) -> tuple[bool, str, Optional[str]]:
        """
        서버의 기본 국가를 변경합니다 (관리자 전용)

        Args:
            nation_name: 설정할 국가 이름

        Returns:
            tuple[bool, str, Optional[str]]: (성공 여부, 메시지, UUID)
        """
        try:
            from pe_api_utils import pe_api

            # 국가 정보 조회
            print(f"🔍 국가 정보 조회 중: {nation_name}")
            nation_data = await pe_api.get_nation_by_name(nation_name)

            if not nation_data:
                return False, f"❌ '{nation_name}' 국가를 찾을 수 없습니다. 정확한 국가명을 입력해주세요.", None

            if 'uuid' not in nation_data:
                return False, f"❌ '{nation_name}' 국가의 UUID를 가져올 수 없습니다.", None

            # 이전 설정 백업
            old_nation = self.BASE_NATION
            old_uuid = self.BASE_NATION_UUID

            # 새 국가로 설정
            self.BASE_NATION = nation_data.get('name', nation_name)
            self.BASE_NATION_UUID = nation_data['uuid']

            print(f"✅ BASE_NATION 변경: {old_nation} → {self.BASE_NATION}")
            print(f"✅ BASE_NATION_UUID 설정: {self.BASE_NATION_UUID}")

            # .env 파일 업데이트 권장 메시지
            update_msg = f"\n\n💡 .env 파일을 수동으로 업데이트해주세요:\n"
            update_msg += f"```\nBASE_NATION={self.BASE_NATION}\nBASE_NATION_UUID={self.BASE_NATION_UUID}\n```"

            return True, f"✅ 서버 국가가 **{self.BASE_NATION}**로 변경되었습니다!{update_msg}", self.BASE_NATION_UUID

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