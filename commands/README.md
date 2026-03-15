# 명령어 폴더 구조

이 폴더는 봇의 모든 명령어를 모듈화하여 관리합니다.

## 📁 폴더 구조

```
commands/
├── __init__.py          # 명령어 자동 로더
├── README.md            # 이 문서
│
├── user/                # 일반 유저 명령어
│   └── basic/           # 📖 기본 명령어 (5개)
│       ├── help.py              # /도움말
│       ├── check.py             # /확인
│       ├── nation.py            # /nation
│       ├── town.py              # /town
│       └── resident.py          # /resident
│   └── travel/          # ✈️ 여행 명령어 (1개)
│       └── travel_request.py    # /여행신청
│
└── admin/               # 관리자 전용 명령어
    ├── test.py                  # /테스트
    │
    ├── alt_account/     # 👥 부계정 관리 (1개)
    │   └── alt_account.py       # /부계관리
    │
    ├── announcement/    # 📢 공지 관련 (2개)
    │   ├── announcement.py      # /공지
    │   └── announcement_manage.py # /공지관리
    │
    ├── callsigns/       # 🎭 콜사인 관련 (2개)
    │   ├── set_callsign.py      # /콜사인
    │   └── manage_callsign.py   # /콜사인관리
    │
    ├── MF/              # 📨 &MF 명령어
    │   └── mf_handler.py        # &MF 메시지 핸들러
    │
    ├── queue/           # 📝 대기열 관련 (4개)
    │   ├── queue_add.py         # /대기열추가
    │   ├── queue_status.py      # /대기열상태
    │   ├── queue_clear.py       # /대기열초기화
    │   └── server_queue.py      # /서버대기열
    │
    ├── return_system/   # 🔄 복귀/잠수 시스템 (4개)
    │   ├── return_setup.py      # /복귀설정
    │   ├── return_manage.py     # /복귀관리
    │   ├── return_confirm.py    # /복귀확인
    │   └── ticket_handler.py    # 복귀 티켓 버튼/메시지 핸들러
    │
    ├── scheduler/       # ⏰ 스케줄러 관련 (6개)
    │   ├── exception.py         # /예외설정
    │   ├── auto_role.py         # /자동실행
    │   ├── auto_start.py        # /자동실행시작
    │   ├── schedule_check.py    # /스케줄확인
    │   ├── newbie_setup.py      # /뉴비설정
    │   └── newbie_check.py      # /뉴비확인
    │
    ├── setting/         # 🤝 설정 관련 (5개)
    │   ├── alliance_setup.py    # /동맹설정
    │   ├── alliance_check.py    # /동맹확인
    │   ├── nation_setup.py      # /국가설정
    │   ├── town_role.py         # /마을역할
    │   └── town_test.py         # /마을테스트
    │
    ├── system/          # ⚙️ 시스템 관련 (3개)
    │   ├── log_view.py          # /로그조회
    │   ├── log_manage.py        # /로그관리
    │   └── database.py          # /데이터베이스
    │
    ├── travel/          # ✈️ 여행 관리 (1개)
    │   └── travel_manage.py     # /여행관리
    │
    └── warning/         # ⚠️ 경고 관련 (2개)
        ├── warning_give.py      # /경고
        └── warning_manage.py    # /경고관리
```

## 📋 명령어 분류

### 👥 일반 유저 (user/)

#### 📖 기본 (basic/)
- `/도움말` - 봇의 모든 명령어 확인
- `/확인` - 자신의 국적 확인하고 역할 받기
- `/nation` - 국가 정보 조회
- `/town` - 마을 정보 조회
- `/resident` - 주민 정보 조회

#### ✈️ 여행 (travel/)
- `/여행신청` - 여행 신청

### 🛡️ 관리자 전용 (admin/)

#### 🧪 테스트
- `/테스트` - 봇의 기본 기능 테스트

#### 👥 부계정 (alt_account/)
- `/부계관리` - 부계정 추가/제거/목록/역할 동기화

#### 📢 공지 (announcement/)
- `/공지` - 즉시/예약 공지 발송
- `/공지관리` - 예약 공지 목록/취소

#### 🎭 콜사인 (callsigns/)
- `/콜사인` - 개인 콜사인(별명) 설정 (15일 쿨타임)
- `/콜사인관리` - 사용자 콜사인 관리 (금지/해제/초기화/백업)

#### 📝 대기열 (queue/)
- `/대기열추가` - 유저/역할 멤버를 대기열에 추가
- `/대기열상태` - 현재 대기열 상태 확인
- `/대기열초기화` - 대기열 초기화
- `/서버대기열` - 서버 접속 대기열 인원 확인

#### 🔄 복귀 시스템 (return_system/)
- `/복귀설정` - 잠수역할/복귀역할/복귀완료역할/핑채널/핑역할/티켓채널 설정
- `/복귀관리` - 역할 부여/제거, 예외 추가/삭제/목록
- `/복귀확인` - 유저 복귀 처리 (잠수+복귀역할 제거, 복귀완료역할 지급)

#### ⏰ 스케줄러 (scheduler/)
- `/예외설정` - 자동실행 예외 대상 관리
- `/자동실행` - 자동 등록 역할 설정
- `/자동실행시작` - 자동 역할 부여 수동 시작
- `/스케줄확인` - 자동 실행 스케줄 정보 확인
- `/뉴비설정` - 뉴비 알림 채널/역할/기간 설정
- `/뉴비확인` - 현재 뉴비 목록 확인

#### 🤝 설정 (setting/)
- `/동맹설정` - 동맹 관리 시스템
- `/동맹확인` - 모든 멤버의 동맹 역할 재확인
- `/국가설정` - 국가 설정
- `/마을역할` - 마을과 역할 연동
- `/마을테스트` - 마을 검증 기능 테스트

#### ⚙️ 시스템 (system/)
- `/로그조회` - 시스템 로그 조회
- `/로그관리` - 로그 시스템 관리
- `/데이터베이스` - 데이터베이스 조회 및 관리

#### ✈️ 여행 관리 (travel/)
- `/여행관리` - 여행 승인/거절/설정

#### ⚠️ 경고 (warning/)
- `/경고` - 경고 부여
- `/경고관리` - 경고 차감/조회/설정 관리

#### 📨 MF (MF/)
- `&MF` - 채널 이름 변경 및 대기열 추가 (메시지 핸들러)

---

## 💻 명령어 파일 형식

### 슬래시 명령어 예시

```python
# commands/admin/category/command_name.py

import discord
from discord import app_commands

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

def setup(bot):
    @bot.tree.command(name="명령어이름", description="명령어 설명")
    @app_commands.check(is_admin)
    async def command_name(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # 명령어 로직
        await interaction.followup.send(embed=embed)

    @command_name.error
    async def command_error(interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("관리자 전용 명령어입니다.", ephemeral=True)
```

### 메시지 핸들러 예시

```python
# commands/admin/MF/mf_handler.py

async def message_handler(bot, message):
    if '&MF' in message.content:
        # 처리 로직
        return True  # True: 다른 핸들러 실행하지 않음
    return False
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

1. **적절한 카테고리 폴더 선택** (또는 새 폴더 생성)
2. **`.py` 파일 생성** (snake_case 권장)
3. **`setup(bot)` 함수 구현**
4. **봇 재시작** - 자동으로 로드됨!

---

## ⚠️ 주의사항

- 일반 유저 명령어는 `user/` 폴더에, 관리자 전용은 `admin/` 폴더에 위치
- 각 명령어 파일은 독립적으로 작동해야 함
- 공통 기능은 별도 유틸리티 모듈로 분리
- 한 파일에 하나의 명령어만 포함 권장
- DB 쿼리 시 반드시 `adapter.adapt_sql()` / `adapter.adapt_ddl()` 사용

---

## 📊 통계

- **총 명령어 수**: 36개
  - **일반 유저**: 6개
  - **관리자 전용**: 30개
- **카테고리 수**: 13개
- **자동 로드**: ✅ 활성화
