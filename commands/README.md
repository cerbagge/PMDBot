# 명령어 폴더 구조

이 폴더는 봇의 모든 명령어를 모듈화하여 관리합니다.

## 📁 폴더 구조

```
commands/
├── __init__.py          # 명령어 자동 로더
├── README.md            # 이 문서
└── admin/               # 관리자 전용 명령어
    ├── __init__.py
    │
    ├── callsigns/       # 🎭 콜사인 관련 (2개)
    │   ├── __init__.py
    │   ├── set_callsign.py      # /콜사인
    │   └── manage_callsign.py   # /콜사인관리
    │
    ├── queue/           # 📝 대기열 관련 (4개)
    │   ├── __init__.py
    │   ├── queue_add.py         # /대기열추가
    │   ├── queue_status.py      # /대기열상태
    │   ├── queue_clear.py       # /대기열초기화
    │   └── server_queue.py      # /서버대기열
    │
    ├── MF/              # 📨 &MF 명령어
    │   ├── __init__.py
    │   └── mf_handler.py        # &MF 메시지 핸들러
    │
    ├── setting/         # 🤝 설정 관련 (5개)
    │   ├── __init__.py
    │   ├── alliance_setup.py    # /동맹설정
    │   ├── alliance_check.py    # /동맹확인
    │   ├── nation_setup.py      # /국가설정
    │   ├── town_role.py         # /마을역할
    │   └── town_test.py         # /마을테스트
    │
    ├── scheduler/       # ⏰ 스케줄러 관련 (4개)
    │   ├── __init__.py
    │   ├── exception.py         # /예외설정
    │   ├── auto_run.py          # /자동실행
    │   ├── auto_start.py        # /자동실행시작
    │   └── schedule_check.py    # /스케줄확인
    │
    ├── system/          # ⚙️ 시스템 관련 (3개)
    │   ├── __init__.py
    │   ├── log_view.py          # /로그조회
    │   ├── log_manage.py        # /로그관리
    │   └── database.py          # /데이터베이스
    │
    └── basic/           # 📖 기본 명령어 (3개)
        ├── __init__.py
        ├── help.py              # /도움말
        ├── check.py             # /확인
        └── test.py              # /테스트
```

## 📋 명령어 분류

### 🎭 콜사인 (callsigns/)
- `/콜사인` - 개인 콜사인(별명) 설정 (15일 쿨타임)
- `/콜사인관리` - 사용자 콜사인 관리

### 📝 대기열 (queue/)
- `/대기열추가` - 유저/역할 멤버를 대기열에 추가
- `/대기열상태` - 현재 대기열 상태 확인
- `/대기열초기화` - 대기열 초기화
- `/서버대기열` - 서버 접속 대기열 인원 확인

### 📨 MF (MF/)
- `&MF` - 채널 이름 변경 및 대기열 추가 (메시지 핸들러)

### 🤝 설정 (setting/)
- `/동맹설정` - 동맹 관리 시스템
- `/동맹확인` - 모든 멤버의 동맹 역할 재확인
- `/국가설정` - 국가 설정
- `/마을역할` - 마을과 역할 연동
- `/마을테스트` - 마을 검증 기능 테스트

### ⏰ 스케줄러 (scheduler/)
- `/예외설정` - 자동실행 예외 대상 관리
- `/자동실행` - 자동 등록 역할 설정
- `/자동실행시작` - 자동 역할 부여 수동 시작
- `/스케줄확인` - 자동 실행 스케줄 정보 확인

### ⚙️ 시스템 (system/)
- `/로그조회` - 시스템 로그 조회
- `/로그관리` - 로그 시스템 관리
- `/데이터베이스` - 데이터베이스 조회 및 관리

### 📖 기본 (basic/)
- `/도움말` - 봇의 모든 명령어 확인
- `/확인` - 자신의 국적 확인하고 역할 받기
- `/테스트` - 봇의 기본 기능 테스트

---

## 💻 명령어 파일 형식

### 슬래시 명령어 예시

```python
# commands/admin/category/command_name.py

import discord
from discord import app_commands

def setup(bot):
    """봇에 명령어 등록"""
    @bot.tree.command(name="명령어이름", description="명령어 설명")
    async def command_name(interaction: discord.Interaction):
        # 명령어 로직
        await interaction.response.send_message("응답 메시지")
```

### 메시지 핸들러 예시

```python
# commands/admin/MF/mf_handler.py

import discord

async def message_handler(bot, message):
    """메시지 이벤트 핸들러"""
    # &MF 명령어 감지
    if '&MF' in message.content:
        # 처리 로직
        # ...
        return True  # True를 반환하면 다른 핸들러는 실행하지 않음

    return False  # 계속 다른 핸들러 실행
```

---

## 🔧 자동 로드 시스템

명령어는 봇 시작 시 자동으로 로드됩니다:

1. `commands/__init__.py`의 `CommandLoader`가 모든 `.py` 파일을 탐색
2. 각 파일의 `setup(bot)` 함수를 자동 호출
3. `message_handler` 함수가 있으면 메시지 핸들러로 등록
4. `__pycache__`와 `__init__.py`는 자동 제외

---

## ➕ 명령어 추가 방법

1. **적절한 카테고리 폴더 선택**
   - 콜사인 관련 → `admin/callsigns/`
   - 대기열 관련 → `admin/queue/`
   - &MF 관련 → `admin/MF/`
   - 설정 관련 → `admin/setting/`
   - 스케줄러 관련 → `admin/scheduler/`
   - 시스템 관련 → `admin/system/`
   - 기본 명령어 → `admin/basic/`

2. **`.py` 파일 생성**
   - 파일명: 영문, 숫자, 언더스코어(_)만 사용
   - 예: `queue_add.py`, `alliance_setup.py`

3. **`setup(bot)` 함수 구현**

4. **봇 재시작** - 자동으로 로드됨!

---

## ⚠️ 주의사항

- 모든 명령어는 `admin/` 폴더 아래에 위치
- 각 명령어 파일은 독립적으로 작동해야 함
- 공통 기능은 별도 유틸리티 모듈로 분리
- 파일명은 snake_case 사용 권장
- 한 파일에 하나의 명령어만 포함 권장

---

## 📊 통계

- **총 명령어 수**: 22개
- **카테고리 수**: 7개
- **자동 로드**: ✅ 활성화
