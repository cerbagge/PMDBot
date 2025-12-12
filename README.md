# Mafia Discord Bot

Planet Earth Minecraft 서버용 디스코드 봇입니다. 국가/마을 관리, 콜사인 시스템, 자동 역할 부여 등의 기능을 제공합니다.

## ⓒ 2025. MF_MNT(cerbaggemoon@gmail.com)

---

## 주요 기능

### 🎮 게임 연동
- Discord-Minecraft 계정 연동 확인
- 국가/마을 정보 자동 조회
- 실시간 게임 데이터 동기화

### 🏷️ 역할 관리
- 국가별 자동 역할 부여
- 마을별 역할 매핑 (UUID 기반)
- 동맹 국가 역할 관리
- 예외 사용자 관리

### 🎯 콜사인 시스템
- 개인 별명(콜사인) 설정 (15일 쿨타임)
- 콜사인 금지 및 관리자 제어
- 자동 백업 시스템 (주간 자동 백업)
- 수동 백업/복구 기능

### 📊 데이터 관리
- SQLite 기반 데이터베이스
- 사용자 검색 및 조회
- 국가/마을 역할 매핑 데이터베이스
- 자동 실행 결과 CSV 리포트

### 📝 로그 시스템
- SQLite 기반 로그 저장
- 카테고리별 로그 분류
- 날짜/사용자별 로그 조회
- 로그 내보내기 (JSON/CSV)

### ⏰ 자동화
- 스케줄러 기반 자동 실행
- 대기열 시스템
- 배치 처리
- CSV 리포트 자동 생성

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
- 채널 ID 및 역할 ID들

### 4. 봇 실행
```bash
python main.py
```

## 폴더 구조

```
discord_bot_api_pe/
├── main.py                     # 봇 메인 파일
├── commands.py                 # 디스코드 명령어
├── config.py                   # 환경 변수 관리
├── scheduler.py                # 자동 실행 스케줄러
├── pe_api_utils.py            # PE API 유틸리티
│
├── *_manager.py               # 각종 매니저 모듈
│   ├── alliance_manager.py    # 동맹 관리
│   ├── callsign_manager.py    # 콜사인 관리
│   ├── callsign_backup.py     # 콜사인 백업
│   ├── database_manager.py    # 데이터베이스 관리
│   ├── exception_manager.py   # 예외 사용자 관리
│   ├── log_manager.py         # 로그 관리
│   ├── nation_role_manager.py # 국가 역할 관리
│   ├── role_manager.py        # 역할 관리
│   ├── town_role_manager.py   # 마을 역할 관리
│   └── queue_manager.py       # 대기열 관리
│
├── utils.py                   # 유틸리티 함수
├── requirements.txt           # 의존성 목록
├── .env.example              # 환경 변수 예시
│
└── data/                     # 데이터 폴더 (자동 생성)
    ├── callsign_backups/     # 콜사인 백업 파일
    ├── csv_exports/          # CSV 리포트
    ├── logs/                 # 로그 파일
    │   └── bot_logs.db      # SQLite 로그 DB
    ├── callsigns.json        # 콜사인 데이터
    ├── alliance_data.json    # 동맹 정보
    ├── nation_roles.json     # 국가 역할
    ├── town_role_mapping.json # 마을 역할 매핑
    ├── discord_minecraft.db  # 메인 데이터베이스
    └── ...                   # 기타 데이터 파일
```

## 주요 명령어

### 사용자 명령어
- `/확인` - 자신의 국적 확인 및 역할 받기
- `/콜사인 [텍스트]` - 콜사인 설정 (15일 쿨타임)

### 관리자 명령어
- `/국가설정 [국가]` - 봇의 기본 국가(BASE_NATION) 설정
- `/마을역할` - 마을-역할 연동 관리
- `/동맹관리` - 동맹 국가 관리
- `/국가역할관리` - 국가별 역할 설정
- `/콜사인관리` - 콜사인 금지/해제/초기화
- `/콜사인백업` - 콜사인 백업/복구
- `/예외관리` - 예외 사용자 관리
- `/자동실행` - 자동 역할 부여 실행
- `/데이터베이스` - 사용자 데이터 조회
- `/로그조회` - 시스템 로그 조회

## 데이터베이스

### SQLite 데이터베이스
1. **discord_minecraft.db** - 메인 데이터베이스
   - 사용자 정보
   - 국가/마을 데이터
   - 닉네임 변경 이력

2. **bot_logs.db** - 로그 데이터베이스
   - 시스템 로그
   - 사용자 활동 로그
   - 관리자 액션 로그

### JSON 파일
- UUID 기반 저장으로 이름 변경에도 안정적
- 사람이 읽기 쉬운 형식으로 백업 및 관리 용이

## 로그 시스템

SQLite 기반 로그 시스템으로 다음 기능 제공:
- 로그 레벨: INFO, WARNING, ERROR, ADMIN, AUTO, SYSTEM
- 로그 카테고리: 콜사인, 대기열, 동맹, 역할, 예외처리, 스케줄러, 시스템, 관리자
- 날짜별, 사용자별, 카테고리별 로그 조회
- JSON/CSV 형식으로 로그 내보내기
- 자동 로그 정리 (30일 이상 오래된 로그)

자세한 내용은 [LOG_MANAGER_README.md](LOG_MANAGER_README.md) 참조

## 백업 시스템

### 콜사인 백업
- 주간 자동 백업 (매주 월요일 오전 8시)
- 수동 백업 기능
- 백업 파일은 Discord 채널에 자동 업로드
- 30일 이상 오래된 자동 백업 자동 삭제

### CSV 리포트
- 자동 실행 완료 시 CSV 파일 생성
- `data/csv_exports/` 폴더에 저장
- Discord 채널에 자동 업로드
- Excel에서 바로 열어서 분석 가능

## 자동 실행

매주 지정된 요일/시간에 자동으로 실행:
1. 지정된 역할을 가진 모든 사용자 처리
2. Discord-Minecraft 계정 연동 확인
3. 국가/마을 정보 조회
4. 적절한 역할 자동 부여
5. 처리 결과 CSV 리포트 생성
6. 성공/실패 채널에 결과 전송

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 기여

버그 리포트 및 기능 제안은 GitHub Issues를 통해 제출해주세요.

## 지원

문제가 발생하면 GitHub Issues에 등록하거나 디스코드 서버 관리자에게 문의하세요.
