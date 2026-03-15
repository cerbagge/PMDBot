# Mafia Discord Bot

Planet Earth Minecraft 서버용 디스코드 봇입니다. 국가/마을 관리, 콜사인 시스템, 부계정 관리, 복귀 시스템, 경고 시스템 등의 기능을 제공합니다.

## ⓒ 2025-2026. MF_MNT(cerbaggemoon@gmail.com)

---

## 주요 기능

### 🎮 게임 연동
- Discord-Minecraft 계정 연동 확인
- 국가/마을/주민 정보 조회 (`/nation`, `/town`, `/resident`)
- 실시간 게임 데이터 동기화
- **Bulk API 3분마다 자동 업데이트** (모든 주민 정보 캐싱)
- 국가/마을 통계 히스토리 기록

### 🏷️ 역할 관리
- 국가별 자동 역할 부여
- 마을별 역할 매핑 (UUID 기반)
- 동맹 국가 역할 관리
- 예외 사용자 관리

### 🎯 콜사인 시스템
- 개인 별명(콜사인) 설정 (15일 쿨타임)
- 콜사인 포맷 변수 지원 (`{MC}`, `{DC}` 등)
- 콜사인 금지 및 관리자 제어
- 자동 백업 시스템 (주간 자동 백업)

### 👥 부계정 관리
- 부계정 ↔ 본계정 연동
- 역할 자동 동기화
- 처벌 연동 (밴/킥/타임아웃/경고)

### 🔄 복귀/잠수 시스템
- 잠수 유저 자동 감지 (매일 03:00)
- 복귀 채팅 일일 핑 (매일 09:00)
- 티켓 기반 복귀 프로세스
- 복귀 확인 시 역할 자동 전환

### ⚠️ 경고 시스템
- 경고 부여/차감/조회
- 누적 경고 자동 처벌 규칙
- 부계정 경고 연동

### ✈️ 여행 시스템
- 여행 신청/승인/거절
- 여행 기간 관리
- 닉네임 자동 변경

### 📢 공지 시스템
- 즉시/예약 공지 발송
- 예약 공지 관리 (목록/취소)

### 📊 데이터 관리
- **PostgreSQL / SQLite 듀얼 지원** (`DB_TYPE` 환경 변수)
- DB 어댑터 패턴으로 SQL 호환성 자동 처리
- 사용자 검색 및 조회
- 자동 실행 결과 CSV 리포트
- Bulk 데이터 캐싱 (빠른 조회)

### 📝 로그 시스템
- 카테고리별 로그 분류
- 날짜/사용자별 로그 조회
- 로그 내보내기 (JSON/CSV)
- 자동 로그 정리 (30일)

### ⏰ 자동화
- 스케줄러 기반 자동 역할 부여
- 뉴비 자동 감지 및 알림
- 대기열 시스템
- 배치 처리 및 CSV 리포트 자동 생성
- Bulk 데이터 3분 주기 업데이트

## 설치 방법

### 1. 필요 요구사항
- Python 3.8 이상
- Discord Bot Token
- Planet Earth API 접근 권한

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정
`.env.example` 파일을 `.env`로 복사하고 필요한 값을 입력하세요:

```bash
cp .env.example .env
```

필수 환경 변수:
- `DISCORD_TOKEN`: Discord 봇 토큰
- `GUILD_ID`: Discord 서버 ID
- `MC_API_BASE`: Planet Earth API 주소
- `BASE_NATION`: 기본 국가 이름
- `DB_TYPE`: 데이터베이스 타입 (`sqlite` 또는 `postgresql`)
- 채널 ID 및 역할 ID들

### 4. 봇 실행
```bash
python main.py
```

## 폴더 구조

```
discord_bot_api_pe/
├── main.py                      # 봇 메인 파일
├── config.py                    # 환경 변수 관리
├── database_manager.py          # 데이터베이스 관리 (싱글톤)
├── scheduler.py                 # 자동 실행 스케줄러
├── bulk_updater.py              # Bulk API 데이터 관리자
├── pe_api_utils.py              # PE API 유틸리티
├── api_handler.py               # API 통신 핸들러
├── utils.py                     # 유틸리티 함수
│
├── db_config/                   # 데이터베이스 설정
│   ├── database.py              # 연결 파라미터 관리
│   ├── db_adapter.py            # PostgreSQL/SQLite 어댑터
│   └── sql_compat.py            # SQL 호환성 헬퍼
│
├── *_manager.py                 # 각종 매니저 모듈
│   ├── alliance_manager.py      # 동맹 관리
│   ├── callsign_manager.py      # 콜사인 관리
│   ├── callsign_backup.py       # 콜사인 백업
│   ├── exception_manager.py     # 예외 사용자 관리
│   ├── log_manager.py           # 로그 관리
│   ├── nation_role_manager.py   # 국가 역할 관리
│   ├── role_manager.py          # 역할 관리
│   ├── town_role_manager.py     # 마을 역할 관리
│   ├── queue_manager.py         # 대기열 관리
│   ├── newbie_config_manager.py # 뉴비 설정 관리
│   ├── return_config_manager.py # 복귀 시스템 설정
│   └── travel_manager.py        # 여행 설정 관리
│
├── *_scheduler.py               # 스케줄러 모듈
│   ├── announcement_scheduler.py # 예약 공지 스케줄러
│   ├── return_scheduler.py      # 잠수 체크 / 복귀 핑 스케줄러
│   └── travel_scheduler.py      # 여행 스케줄러
│
├── commands/                    # 모듈화된 명령어 시스템
│   ├── __init__.py              # 명령어 자동 로더
│   │
│   ├── user/                    # 일반 유저 명령어
│   │   ├── basic/               # 기본 (확인, 도움말, nation, town, resident)
│   │   └── travel/              # 여행신청
│   │
│   └── admin/                   # 관리자 전용 명령어
│       ├── alt_account/         # 부계정 관리
│       ├── announcement/        # 공지 시스템
│       ├── callsigns/           # 콜사인 관련
│       ├── MF/                  # &MF 핸들러
│       ├── queue/               # 대기열 관련
│       ├── return_system/       # 복귀/잠수 시스템
│       ├── scheduler/           # 스케줄러/뉴비 관련
│       ├── setting/             # 설정 관련
│       ├── system/              # 시스템 관련
│       ├── travel/              # 여행 관리
│       └── warning/             # 경고 시스템
│
└── data/                        # 데이터 폴더 (자동 생성)
    ├── bulk/                    # Bulk API 캐시
    ├── callsign_backups/        # 콜사인 백업 파일
    ├── csv_exports/             # CSV 리포트
    ├── return_config.json       # 복귀 시스템 설정
    ├── travel_config.json       # 여행 시스템 설정
    ├── announcement_schedule.json # 예약 공지
    ├── callsigns.json           # 콜사인 데이터
    ├── alliance_data.json       # 동맹 정보
    ├── nation_roles.json        # 국가 역할
    ├── town_role_mapping.json   # 마을 역할 매핑
    └── bot.db / bot_logs.db     # SQLite DB (SQLite 모드 시)
```

## 명령어 시스템

### 일반 유저 명령어 (6개)

| 명령어 | 설명 |
|--------|------|
| `/확인` | 자신의 국적 확인 및 역할 받기 |
| `/도움말` | 봇의 모든 명령어 확인 |
| `/nation` | 국가 정보 조회 |
| `/town` | 마을 정보 조회 |
| `/resident` | 주민 정보 조회 |
| `/여행신청` | 여행 신청 |

### 관리자 명령어 (30개)

#### 🎭 콜사인 (2개)
- `/콜사인 [텍스트]` - 콜사인 설정 (15일 쿨타임)
- `/콜사인관리` - 콜사인 금지/해제/초기화/백업

#### 📝 대기열 (4개)
- `/대기열추가` - 유저/역할을 대기열에 추가
- `/대기열상태` - 현재 대기열 상태 확인
- `/대기열초기화` - 대기열 초기화
- `/서버대기열` - 서버 접속 대기열 인원 확인

#### 🤝 설정 (5개)
- `/국가설정` - 봇의 기본 국가 설정
- `/동맹설정` - 동맹 국가 관리
- `/동맹확인` - 모든 멤버의 동맹 역할 재확인
- `/마을역할` - 마을-역할 연동 관리
- `/마을테스트` - 마을 검증 기능 테스트

#### ⏰ 스케줄러 (6개)
- `/스케줄확인` - 자동 실행 스케줄 정보 확인
- `/예외설정` - 자동실행 예외 대상 관리
- `/자동실행` - 자동 등록 역할 설정
- `/자동실행시작` - 자동 역할 부여 수동 시작
- `/뉴비설정` - 뉴비 알림 설정
- `/뉴비확인` - 현재 뉴비 목록 확인

#### ⚙️ 시스템 (3개)
- `/데이터베이스` - 사용자 데이터 조회
- `/로그조회` - 시스템 로그 조회
- `/로그관리` - 로그 시스템 관리 (통계/정리/내보내기/백업)

#### 👥 부계정 (1개)
- `/부계관리` - 부계정 추가/제거/목록/역할 동기화

#### ⚠️ 경고 (2개)
- `/경고` - 경고 부여
- `/경고관리` - 경고 차감/조회/설정

#### 🔄 복귀 시스템 (3개)
- `/복귀설정` - 잠수/복귀 역할·채널·핑 설정
- `/복귀관리` - 역할 부여/제거, 예외 관리
- `/복귀확인` - 유저 복귀 처리

#### ✈️ 여행 (1개)
- `/여행관리` - 여행 승인/거절/설정

#### 📢 공지 (2개)
- `/공지` - 즉시/예약 공지 발송
- `/공지관리` - 예약 공지 목록/취소

#### 🧪 기타
- `/테스트` - 봇의 기본 기능 테스트

#### 📨 메시지 핸들러
- `&MF` - 채널 이름 변경 및 대기열 추가

> 자세한 명령어 구조는 [commands/README.md](commands/README.md) 참조

## 데이터베이스

### 듀얼 DB 지원
- **PostgreSQL** (권장): `DB_TYPE=postgresql`
- **SQLite** (기본값): `DB_TYPE=sqlite`
- `db_config/db_adapter.py`의 어댑터 패턴으로 SQL 차이 자동 처리

### 주요 테이블
| 테이블 | 설명 |
|--------|------|
| `users` | 사용자 정보 (discord_id, minecraft_uuid, 국가, 마을 등) |
| `minecraft_name_history` | 마인크래프트 닉네임 변경 이력 |
| `nation_history` | 국가/마을 소속 변경 이력 |
| `callsigns` / `callsign_history` | 콜사인 및 변경 이력 |
| `all_players` / `all_nations` / `all_towns` | Bulk API 캐시 |
| `nation_stats_history` | 국가 통계 히스토리 |
| `town_stats_history` | 마을 통계 히스토리 |
| `alt_accounts` | 부계정 연동 |
| `travels` | 여행 기록 |
| `warnings` / `warning_config` | 경고 및 설정 |

### 로그 데이터베이스
- 로그 레벨: INFO, WARNING, ERROR, ADMIN, AUTO, SYSTEM
- 카테고리별 분류 및 날짜/사용자별 조회
- JSON/CSV 내보내기, 자동 정리 (30일)

## 백그라운드 태스크

| 태스크 | 주기 | 설명 |
|--------|------|------|
| 대기열 처리 | 1분 | 대기열 확인 및 처리 |
| Bulk 데이터 업데이트 | 3분 | 전체 주민 정보 갱신 |
| 자동 역할 체크 | 1시간 | 스케줄 시간 확인 |
| 잠수 체크 | 매일 03:00 | 잠수 유저 자동 감지 |
| 복귀 채팅 핑 | 매일 09:00 | 복귀 대상 일일 핑 |
| 콜사인 백업 | 매주 월요일 08:00 | 자동 백업 |

## 개발 정보

### 아키텍처
- **모듈화된 명령어 시스템**: `commands/` 하위 파일 자동 로드
- **DB 어댑터 패턴**: PostgreSQL/SQLite 투명하게 전환
- **싱글톤 매니저**: `db_manager`, `return_config_manager` 등
- **스케줄러**: Discord.py tasks + APScheduler 기반

### 새 명령어 추가 방법
1. `commands/user/` 또는 `commands/admin/` 하위에 폴더/파일 생성
2. `setup(bot)` 함수 구현
3. 봇 재시작 - 자동 로드!

자세한 내용은 [commands/README.md](commands/README.md) 참조

## 최근 업데이트

### v3.0.0 (2026-03)
- ✅ PostgreSQL / SQLite 듀얼 DB 지원
- ✅ 부계정 관리 시스템 (역할/처벌 동기화)
- ✅ 복귀/잠수 시스템 (자동 감지, 티켓, 일일 핑)
- ✅ 경고 시스템 (누적 자동 처벌)
- ✅ 여행 시스템 (신청/승인/거절)
- ✅ 공지 시스템 (즉시/예약 발송)
- ✅ 뉴비 자동 감지 및 알림
- ✅ 국가/마을/주민 조회 명령어
- ✅ 국가/마을 통계 히스토리 기록

### v2.0.0 (2025-01)
- ✅ 명령어 시스템 모듈화 (22개 명령어 분리)
- ✅ 자동 로딩 시스템 구현
- ✅ Bulk API 3분 주기 자동 업데이트
- ✅ 사용자/관리자 명령어 분리
- ✅ all_players 테이블 추가

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 기여

버그 리포트 및 기능 제안은 GitHub Issues를 통해 제출해주세요.

## 지원

문제가 발생하면 GitHub Issues에 등록하거나 디스코드 서버 관리자에게 문의하세요.
