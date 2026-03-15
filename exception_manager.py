import json
import os
from typing import List, Set


def _safe_print(msg):
    """유니코드 문자 출력 오류 방지용 print 함수"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class ExceptionManager:
    def __init__(self, filename: str = "data/exceptions.json"):
        # data 폴더 생성
        os.makedirs("data", exist_ok=True)

        self.filename = filename
        self._exceptions: Set[int] = set()
        self.load_exceptions()

    def load_exceptions(self):
        """예외 목록을 파일에서 로드"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._exceptions = set(data.get('exceptions', []))
                _safe_print(f"[OK] 예외 목록 로드: {len(self._exceptions)}명")
            else:
                _safe_print(f"[INFO] 예외 파일이 없어서 새로 생성합니다: {self.filename}")
                self.save_exceptions()
        except Exception as e:
            _safe_print(f"[ERROR] 예외 목록 로드 실패: {e}")
            self._exceptions = set()

    def save_exceptions(self):
        """예외 목록을 파일에 저장"""
        try:
            data = {
                'exceptions': list(self._exceptions),
                'count': len(self._exceptions)
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            _safe_print(f"[OK] 예외 목록 저장: {len(self._exceptions)}명")
        except Exception as e:
            _safe_print(f"[ERROR] 예외 목록 저장 실패: {e}")

    def add_exception(self, user_id: int) -> bool:
        """예외 목록에 사용자 추가"""
        if user_id not in self._exceptions:
            self._exceptions.add(user_id)
            self.save_exceptions()
            _safe_print(f"[+] 예외 추가: {user_id}")
            return True
        return False

    def remove_exception(self, user_id: int) -> bool:
        """예외 목록에서 사용자 제거"""
        if user_id in self._exceptions:
            self._exceptions.remove(user_id)
            self.save_exceptions()
            _safe_print(f"[-] 예외 제거: {user_id}")
            return True
        return False
    
    def is_exception(self, user_id: int) -> bool:
        """사용자가 예외 목록에 있는지 확인"""
        return user_id in self._exceptions
    
    def get_exceptions(self) -> List[int]:
        """예외 목록 반환"""
        return list(self._exceptions)
    
    def get_count(self) -> int:
        """예외 목록 개수 반환"""
        return len(self._exceptions)

# 전역 예외 관리자 인스턴스
exception_manager = ExceptionManager()