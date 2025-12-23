# callsign_manager.py - 콜사인 관리 기능

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

class CallsignManager:
    def __init__(self, filename: str = "data/callsigns.json", banned_file: str = "data/callsign_banned.json", role_format_file: str = "data/role_formats.json"):
        """
        콜사인 관리자 초기화

        Args:
            filename: 콜사인 데이터 저장 파일
            banned_file: 콜사인 사용 금지 사용자 목록 파일
            role_format_file: 역할별 닉네임 양식 저장 파일
        """
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.filename = filename
        self.banned_file = banned_file
        self.role_format_file = role_format_file
        self.callsigns = self.load_callsigns()
        self.banned_users = self.load_banned_users()
        self.cooldowns = self.load_cooldowns()
        self.role_formats = self.load_role_formats()

        # database_manager import
        try:
            from database_manager import db_manager
            self.db_manager = db_manager
            print("✅ callsign_manager: database_manager 연동 완료")
        except ImportError:
            self.db_manager = None
            print("⚠️ callsign_manager: database_manager 비활성화")
    
    def load_callsigns(self) -> Dict:
        """콜사인 데이터 로드"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_callsigns(self):
        """콜사인 데이터 저장 (JSON + DB)"""
        # JSON 파일에 저장
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.callsigns, f, ensure_ascii=False, indent=2)

        # DB에도 저장 (활성화된 경우)
        if self.db_manager:
            for user_id_str, data in self.callsigns.items():
                try:
                    user_id = int(user_id_str)
                    callsign = data.get('callsign', '')
                    admin_override = data.get('admin_override', False)
                    self.db_manager.set_callsign(user_id, callsign, admin_override)
                except Exception as e:
                    print(f"⚠️ DB 콜사인 저장 실패 ({user_id_str}): {e}")
    
    def load_banned_users(self) -> Dict:
        """콜사인 사용 금지 사용자 목록 로드"""
        if os.path.exists(self.banned_file):
            try:
                with open(self.banned_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_banned_users(self):
        """콜사인 사용 금지 사용자 목록 저장"""
        with open(self.banned_file, 'w', encoding='utf-8') as f:
            json.dump(self.banned_users, f, ensure_ascii=False, indent=2)
    
    def load_cooldowns(self) -> Dict:
        """쿨타임 데이터 로드"""
        cooldown_file = "callsign_cooldowns.json"
        if os.path.exists(cooldown_file):
            try:
                with open(cooldown_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # ISO 형식 문자열을 datetime 객체로 변환
                    cooldowns = {}
                    for user_id, timestamp in data.items():
                        try:
                            cooldowns[user_id] = datetime.fromisoformat(timestamp)
                        except:
                            pass
                    return cooldowns
            except:
                return {}
        return {}
    
    def save_cooldowns(self):
        """쿨타임 데이터 저장"""
        cooldown_file = "callsign_cooldowns.json"
        # datetime 객체를 ISO 형식 문자열로 변환
        data = {}
        for user_id, timestamp in self.cooldowns.items():
            data[user_id] = timestamp.isoformat()
        
        with open(cooldown_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def ban_user(self, user_id: int, banned_by: int, reason: str = "관리자 결정") -> Tuple[bool, str]:
        """
        사용자의 콜사인 사용 권한 제거
        
        Args:
            user_id: 금지할 사용자 ID
            banned_by: 금지를 실행한 관리자 ID
            reason: 금지 사유
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        # 이미 금지된 사용자인지 확인
        if user_id_str in self.banned_users:
            return False, "이미 콜사인 사용이 금지된 사용자입니다."
        
        # 금지 정보 저장
        self.banned_users[user_id_str] = {
            "banned_at": datetime.now().isoformat(),
            "banned_by": banned_by,
            "reason": reason
        }

        self.save_banned_users()

        # 기존 콜사인이 있는지 확인 (제거하지 않음)
        if user_id_str in self.callsigns:
            current_callsign = self.callsigns[user_id_str]["callsign"]
            return True, f"콜사인 변경 권한이 박탈되었습니다. (현재 콜사인 '{current_callsign}'은 유지됨)"

        return True, "콜사인 변경 권한이 박탈되었습니다."
    
    def unban_user(self, user_id: int) -> Tuple[bool, str]:
        """
        사용자의 콜사인 사용 권한 복구
        
        Args:
            user_id: 금지 해제할 사용자 ID
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        if user_id_str not in self.banned_users:
            return False, "콜사인 사용이 금지되지 않은 사용자입니다."
        
        del self.banned_users[user_id_str]
        self.save_banned_users()
        return True, "콜사인 사용 권한이 복구되었습니다."
    
    def is_banned(self, user_id: int) -> bool:
        """사용자가 콜사인 사용 금지 상태인지 확인"""
        return str(user_id) in self.banned_users
    
    def get_ban_info(self, user_id: int) -> Optional[Dict]:
        """사용자의 금지 정보 조회"""
        return self.banned_users.get(str(user_id))
    
    def get_banned_users_list(self) -> list:
        """전체 금지 사용자 목록 조회"""
        banned_list = []
        for user_id, info in self.banned_users.items():
            banned_list.append({
                "user_id": user_id,
                "banned_at": info.get("banned_at"),
                "banned_by": info.get("banned_by"),
                "reason": info.get("reason", "사유 없음")
            })
        return banned_list
    
    def set_callsign(self, user_id: int, callsign: str, force: bool = False, admin_override: bool = False) -> Tuple[bool, str]:
        """
        사용자 콜사인 설정 (권한 체크 포함)
        
        Args:
            user_id: 사용자 ID
            callsign: 설정할 콜사인
            force: 쿨타임 무시 여부 (관리자용)
            admin_override: 관리자 권한으로 금지 상태 무시 여부
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        # 금지된 사용자 체크 (관리자 권한으로 무시 가능)
        if not admin_override and self.is_banned(user_id):
            ban_info = self.get_ban_info(user_id)
            return False, f"콜사인 사용이 금지되어 있습니다.\n사유: {ban_info.get('reason', '관리자 결정')}"
        
        # 쿨타임 체크 (force가 False일 때만)
        if not force and user_id_str in self.cooldowns:
            cooldown_end = self.cooldowns[user_id_str]
            if datetime.now() < cooldown_end:
                remaining = cooldown_end - datetime.now()
                days = remaining.days
                hours = remaining.seconds // 3600
                return False, f"쿨타임 중입니다. {days}일 {hours}시간 후에 다시 시도해주세요."
        
        # 콜사인 저장 (JSON)
        self.callsigns[user_id_str] = {
            "callsign": callsign,
            "set_at": datetime.now().isoformat(),
            "admin_override": admin_override  # 관리자가 강제로 설정했는지 기록
        }

        # 쿨타임 설정 (15일) - force나 admin_override가 아닐 때만
        if not force and not admin_override:
            self.cooldowns[user_id_str] = datetime.now() + timedelta(days=15)
            self.save_cooldowns()

        # JSON 파일에 저장
        self.save_callsigns()

        # DB에도 저장 (활성화된 경우)
        if self.db_manager:
            try:
                self.db_manager.set_callsign(user_id, callsign, admin_override)
            except Exception as e:
                print(f"⚠️ DB 콜사인 저장 실패 ({user_id}): {e}")
        
        # 메시지 생성
        if admin_override:
            return True, f"관리자 권한으로 콜사인이 '{callsign}'(으)로 설정되었습니다."
        else:
            return True, f"콜사인이 '{callsign}'(으)로 설정되었습니다."
    
    def admin_set_callsign(self, user_id: int, callsign: str, admin_id: int) -> Tuple[bool, str]:
        """
        관리자 전용 콜사인 설정 함수 (모든 제약 무시)
        
        Args:
            user_id: 대상 사용자 ID
            callsign: 설정할 콜사인
            admin_id: 관리자 ID
        
        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)
        
        # 기존 금지 상태 확인
        was_banned = self.is_banned(user_id)
        ban_info = None
        if was_banned:
            ban_info = self.get_ban_info(user_id)
        
        # 콜사인 설정 (모든 제약 무시)
        success, message = self.set_callsign(
            user_id=user_id, 
            callsign=callsign, 
            force=True,  # 쿨타임 무시
            admin_override=True  # 금지 상태 무시
        )
        
        if success and was_banned:
            # 금지 상태였다면 로그에 기록
            log_message = f"관리자가 권한 박탈된 사용자에게 콜사인을 강제 설정했습니다."
            if ban_info:
                log_message += f"\n이전 금지 사유: {ban_info.get('reason', '사유 없음')}"
            log_message += f"\n설정된 콜사인: '{callsign}'"
            
            return True, f"{message}\n⚠️ 주의: 이 사용자는 콜사인 사용이 금지된 상태입니다."
        
        return success, message
    
    def get_callsign(self, user_id: int) -> Optional[str]:
        """사용자 콜사인 조회"""
        return self.callsigns.get(str(user_id), {}).get("callsign")
    
    def get_callsign_info(self, user_id: int) -> Optional[Dict]:
        """사용자 콜사인 정보 전체 조회"""
        return self.callsigns.get(str(user_id))
    
    def remove_callsign(self, user_id: int) -> bool:
        """사용자 콜사인 제거 (관리자용)"""
        user_id_str = str(user_id)
        if user_id_str in self.callsigns:
            del self.callsigns[user_id_str]
            # 쿨타임도 제거
            if user_id_str in self.cooldowns:
                del self.cooldowns[user_id_str]
                self.save_cooldowns()
            self.save_callsigns()
            return True
        return False
    
    def get_callsign_count(self) -> int:
        """설정된 콜사인 개수"""
        return len(self.callsigns)
    
    def check_cooldown(self, user_id: int) -> Tuple[bool, int]:
        """
        콜사인 쿨타임 확인

        Returns:
            (사용 가능 여부, 남은 일수)
        """
        user_id_str = str(user_id)

        if user_id_str not in self.cooldowns:
            return True, 0

        cooldown_end = self.cooldowns[user_id_str]
        now = datetime.now()

        if now >= cooldown_end:
            # 쿨타임이 끝났으면 제거
            del self.cooldowns[user_id_str]
            self.save_cooldowns()
            return True, 0

        remaining = cooldown_end - now
        remaining_days = remaining.days
        if remaining.seconds > 0:
            remaining_days += 1

        return False, remaining_days

    def reset_cooldown(self, user_id: int) -> Tuple[bool, str]:
        """
        특정 사용자의 쿨타임 초기화

        Args:
            user_id: 사용자 ID

        Returns:
            (성공 여부, 메시지)
        """
        user_id_str = str(user_id)

        if user_id_str in self.cooldowns:
            del self.cooldowns[user_id_str]
            self.save_cooldowns()
            return True, "쿨타임이 초기화되었습니다."
        else:
            return False, "쿨타임이 설정되어 있지 않습니다."

    def reset_all_cooldowns(self) -> int:
        """
        모든 사용자의 쿨타임 초기화

        Returns:
            초기화된 사용자 수
        """
        count = len(self.cooldowns)
        self.cooldowns.clear()
        self.save_cooldowns()
        return count

    # ===== 역할별 닉네임 양식 관리 =====

    def load_role_formats(self) -> Dict:
        """역할별 닉네임 양식 데이터 로드"""
        if os.path.exists(self.role_format_file):
            try:
                with open(self.role_format_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_role_formats(self):
        """역할별 닉네임 양식 데이터 저장"""
        with open(self.role_format_file, 'w', encoding='utf-8') as f:
            json.dump(self.role_formats, f, ensure_ascii=False, indent=2)

    def set_role_format(self, role_id: int, format_string: str) -> Tuple[bool, str]:
        """
        역할별 닉네임 양식 설정

        Args:
            role_id: 역할 ID
            format_string: 닉네임 양식 문자열
                          사용 가능한 변수: {MF}, {NN}, {TT}, {CC}, {NN/TT}

        Returns:
            (성공 여부, 메시지)
        """
        role_id_str = str(role_id)

        # 양식 유효성 검증
        valid_vars = ['{MF}', '{NN}', '{TT}', '{CC}', '{NN/TT}']

        # 양식 길이 제한 (치환 전 최대 100자)
        if len(format_string) > 100:
            return False, "양식이 너무 깁니다. (최대 100자)"

        # 양식 저장
        self.role_formats[role_id_str] = {
            "format": format_string,
            "set_at": datetime.now().isoformat()
        }

        self.save_role_formats()
        return True, f"역할 닉네임 양식이 설정되었습니다: `{format_string}`"

    def get_role_format(self, role_id: int) -> Optional[str]:
        """역할별 닉네임 양식 조회"""
        role_data = self.role_formats.get(str(role_id))
        if role_data and isinstance(role_data, dict):
            return role_data.get("format")
        return None

    def remove_role_format(self, role_id: int) -> Tuple[bool, str]:
        """역할별 닉네임 양식 제거"""
        role_id_str = str(role_id)
        if role_id_str in self.role_formats:
            old_format = self.role_formats[role_id_str].get("format", "알 수 없음")
            del self.role_formats[role_id_str]
            self.save_role_formats()
            return True, f"양식이 제거되었습니다. (이전 양식: `{old_format}`)"
        return False, "설정된 양식이 없습니다."

    def get_all_role_formats(self) -> Dict:
        """모든 역할 양식 조회"""
        return self.role_formats.copy()

    def apply_format_to_nickname(self, format_string: str, mc_id: str = None, nation: str = None,
                                 town: str = None, callsign: str = None) -> str:
        """
        양식 문자열에 실제 값을 치환하여 닉네임 생성

        새로운 문법 지원:
        - {CC}, {NN}, {TT}, {MC} - 기본 변수
        - [A/B/C] - A → B → C 순서로 폴백 (값이 없으면 다음 옵션)
        - "텍스트" 또는 '텍스트' - 리터럴 텍스트

        Args:
            format_string: 양식 문자열
            mc_id: 마인크래프트 닉네임
            nation: PlanetEarth 국가 이름
            town: PlanetEarth 마을 이름
            callsign: 콜사인

        Returns:
            완성된 닉네임
        """
        import re

        # 변수 값 매핑
        variables = {
            'CC': callsign if callsign else None,
            'NN': nation if nation and nation not in ['', '❌', '무소속'] else None,
            'TT': town if town and town not in ['', '❌', '무소속'] else None,
            'MC': mc_id if mc_id and mc_id not in ['', '❌', 'Unknown'] else None,
            'MF': mc_id if mc_id and mc_id not in ['', '❌', 'Unknown'] else None,
        }

        def evaluate_expression(expr: str) -> str:
            """표현식을 평가하여 값 반환 (복합 표현식 지원)"""
            expr = expr.strip()

            # 단순 문자열 리터럴
            if (expr.startswith('"') and expr.endswith('"')) or \
               (expr.startswith("'") and expr.endswith("'")):
                return expr[1:-1]

            # 단순 변수
            if expr.startswith('{') and expr.endswith('}'):
                var_name = expr[1:-1]
                value = variables.get(var_name)
                return value if value else None

            # 복합 표현식: {CC}" /" 같은 형태
            # 변수와 리터럴을 찾아서 조합
            import re
            parts = []
            last_pos = 0
            failed = False

            # 변수 {VAR} 또는 리터럴 "text"/'text' 찾기
            pattern = r'\{([A-Z]+)\}|"([^"]*)"|\'([^\']*)\''

            for match in re.finditer(pattern, expr):
                # 매치 사이의 공백이나 텍스트도 포함
                if match.start() > last_pos:
                    between_text = expr[last_pos:match.start()]
                    if between_text.strip():  # 공백만 있으면 무시
                        # 매치되지 않은 텍스트가 있으면 복합 표현식으로 처리 불가
                        pass

                last_pos = match.end()

                # 변수
                if match.group(1):
                    var_name = match.group(1)
                    value = variables.get(var_name)
                    if value:
                        parts.append(value)
                    else:
                        # 변수 값이 없으면 전체 표현식 실패
                        failed = True
                        break
                # 큰따옴표 리터럴
                elif match.group(2) is not None:
                    parts.append(match.group(2))
                # 작은따옴표 리터럴
                elif match.group(3) is not None:
                    parts.append(match.group(3))

            if failed or not parts:
                return None

            return ''.join(parts)

        def process_fallback(match) -> str:
            """[A/B/C] 형식의 폴백 처리 (따옴표 안의 / 무시)"""
            content = match.group(1)

            # 스마트 분할: 따옴표 안의 /는 무시
            import re
            options = []
            current = []
            in_quote = None

            i = 0
            while i < len(content):
                char = content[i]

                # 따옴표 시작/종료
                if char in ('"', "'"):
                    if in_quote is None:
                        in_quote = char
                        current.append(char)
                    elif in_quote == char:
                        in_quote = None
                        current.append(char)
                    else:
                        current.append(char)
                # 따옴표 밖의 / → 구분자
                elif char == '/' and in_quote is None:
                    options.append(''.join(current))
                    current = []
                else:
                    current.append(char)

                i += 1

            # 마지막 옵션 추가
            if current or not options:
                options.append(''.join(current))

            # 각 옵션을 순서대로 시도
            for option in options:
                result = evaluate_expression(option.strip())
                if result:
                    return result

            # 모든 옵션 실패 시 빈 문자열
            return ''

        # [A/B/C] 형식의 폴백 처리 (따옴표 안의 [] 무시)
        def find_and_replace_brackets(text: str) -> str:
            """따옴표 밖의 [...] 패턴만 찾아서 처리"""
            result = []
            i = 0
            in_quote = None

            while i < len(text):
                char = text[i]

                # 따옴표 추적
                if char in ('"', "'") and (i == 0 or text[i-1] != '\\'):
                    if in_quote is None:
                        in_quote = char
                    elif in_quote == char:
                        in_quote = None
                    result.append(char)
                    i += 1
                # 따옴표 밖의 [ 발견
                elif char == '[' and in_quote is None:
                    # 닫는 ]를 찾기
                    depth = 1
                    j = i + 1
                    content_start = j
                    inner_quote = None

                    while j < len(text) and depth > 0:
                        if text[j] in ('"', "'") and (j == 0 or text[j-1] != '\\'):
                            if inner_quote is None:
                                inner_quote = text[j]
                            elif inner_quote == text[j]:
                                inner_quote = None
                        elif text[j] == '[' and inner_quote is None:
                            depth += 1
                        elif text[j] == ']' and inner_quote is None:
                            depth -= 1
                        j += 1

                    if depth == 0:
                        # 매칭되는 [...] 발견
                        content = text[content_start:j-1]
                        # 임시 객체로 process_fallback 호출
                        class Match:
                            def group(self, n):
                                return content
                        replacement = process_fallback(Match())
                        result.append(replacement)
                        i = j
                    else:
                        # 닫는 ] 없음
                        result.append(char)
                        i += 1
                else:
                    result.append(char)
                    i += 1

            return ''.join(result)

        result = find_and_replace_brackets(format_string)

        # {NN/TT} 레거시 변수 처리 (국가 우선, 없으면 마을)
        if '{NN/TT}' in result:
            nn_tt_value = variables.get('NN') or variables.get('TT') or ''
            result = result.replace('{NN/TT}', nn_tt_value)

        # 남은 단순 변수 치환
        for var_name, var_value in variables.items():
            if var_value:
                result = result.replace('{' + var_name + '}', var_value)
            else:
                result = result.replace('{' + var_name + '}', '')

        # 연속된 공백 제거 및 trim
        result = ' '.join(result.split())

        # 디스코드 닉네임 길이 제한 (32자)
        if len(result) > 32:
            result = result[:32]

        return result


# 콜사인 검증 함수
def validate_callsign(callsign: str) -> Tuple[bool, str]:
    """
    콜사인 유효성 검증
    
    Args:
        callsign: 검증할 콜사인
    
    Returns:
        (유효 여부, 오류 메시지)
    """
    if not callsign or not callsign.strip():
        return False, "콜사인은 비어있을 수 없습니다."
    
    if len(callsign) > 20:
        return False, "콜사인은 20자 이하여야 합니다."
    
    # 금지된 문자 확인
    forbidden_chars = ['@', '#', '`', '\\', '/', '\n', '\r', '\t']
    for char in forbidden_chars:
        if char in callsign:
            return False, f"콜사인에 사용할 수 없는 문자가 포함되어 있습니다: {char}"
    
    # 디스코드 멘션 형식 차단
    if callsign.startswith('<') and callsign.endswith('>'):
        return False, "콜사인은 멘션 형식일 수 없습니다."
    
    # 이모지는 허용하되 너무 많은 이모지는 차단
    import re
    emoji_pattern = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+")
    emojis = emoji_pattern.findall(callsign)
    if len(''.join(emojis)) > 10:
        return False, "이모지가 너무 많습니다. (최대 10자)"
    
    return True, ""


# 사용자 표시 정보 가져오기
def get_user_display_info(user_id: int, mc_id: str = None, nation: str = None) -> str:
    """
    사용자 표시 정보 생성 (콜사인 또는 국가명)
    
    Args:
        user_id: 사용자 ID
        mc_id: 마인크래프트 ID
        nation: 국가명
    
    Returns:
        표시할 문자열
    """
    if not mc_id:
        return "Unknown"
    
    # 콜사인 확인
    if callsign_manager:
        callsign = callsign_manager.get_callsign(user_id)
        if callsign:
            return f"{mc_id} ㅣ {callsign}"
    
    # 콜사인이 없으면 국가명 사용
    if nation:
        return f"{mc_id} ㅣ {nation}"
    
    return mc_id


# 싱글톤 인스턴스 생성
callsign_manager = CallsignManager()
print("CallsignManager instance created successfully")