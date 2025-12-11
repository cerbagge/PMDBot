# callsign_backup.py - 백업 관리 모듈

import json
import os
import shutil
from datetime import datetime, time
from typing import Dict, Tuple, Optional, List
import asyncio
from discord.ext import tasks
import discord

class CallsignBackupManager:
    def __init__(self, callsign_file: str = "data/callsigns.json", backup_dir: str = "data/callsign_backups"):
        """
        콜사인 백업 관리자 초기화

        Args:
            callsign_file: 원본 콜사인 파일
            backup_dir: 백업 파일 저장 디렉토리
        """
        self.callsign_file = callsign_file
        self.backup_dir = backup_dir
        self.ensure_backup_directory()
    
    def ensure_backup_directory(self):
        """백업 디렉토리 생성"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
            print(f"✅ 백업 디렉토리 생성: {self.backup_dir}")
    
    def create_backup(self, backup_type: str = "auto") -> Tuple[bool, str]:
        """
        백업 파일 생성
        
        Args:
            backup_type: 백업 유형 (auto/manual)
        
        Returns:
            (성공 여부, 백업 파일 경로 또는 에러 메시지)
        """
        try:
            if not os.path.exists(self.callsign_file):
                return False, "원본 콜사인 파일이 존재하지 않습니다."
            
            # 백업 파일명 생성 (YYYY-MM-DD_HH-MM-SS_type.json)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"callsigns_backup_{timestamp}_{backup_type}.json"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # 파일 복사
            shutil.copy2(self.callsign_file, backup_path)
            
            # 백업 메타데이터 추가
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 메타데이터 추가
            backup_data = {
                "metadata": {
                    "backup_time": datetime.now().isoformat(),
                    "backup_type": backup_type,
                    "total_callsigns": len(data) if isinstance(data, dict) else 0,
                    "original_file": self.callsign_file
                },
                "data": data
            }
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            # 오래된 백업 정리 (30일 이상)
            self.cleanup_old_backups(days=30)
            
            print(f"💾 백업 생성 완료: {backup_filename}")
            return True, backup_path
            
        except Exception as e:
            print(f"❌ 백업 생성 실패: {str(e)}")
            return False, f"백업 생성 실패: {str(e)}"
    
    def restore_backup(self, backup_file: str) -> Tuple[bool, str]:
        """
        백업 파일로부터 복구
        
        Args:
            backup_file: 복구할 백업 파일 경로
        
        Returns:
            (성공 여부, 메시지)
        """
        try:
            if not os.path.exists(backup_file):
                return False, "백업 파일이 존재하지 않습니다."
            
            # 현재 파일 백업 (복구 전 안전 백업)
            if os.path.exists(self.callsign_file):
                pre_restore_backup = f"{self.callsign_file}.pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.callsign_file, pre_restore_backup)
                print(f"🔒 복구 전 백업 생성: {pre_restore_backup}")
            
            # 백업 파일 읽기
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # 메타데이터가 있는 새 형식인지 확인
            if "metadata" in backup_data and "data" in backup_data:
                callsign_data = backup_data["data"]
                metadata = backup_data["metadata"]
            else:
                # 구 형식 백업 파일
                callsign_data = backup_data
                metadata = {"backup_time": "Unknown", "total_callsigns": len(callsign_data)}
            
            # 원본 파일에 복구
            with open(self.callsign_file, 'w', encoding='utf-8') as f:
                json.dump(callsign_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 백업 복구 완료: {backup_file}")
            return True, f"백업 복구 완료\n- 백업 시간: {metadata.get('backup_time', 'Unknown')}\n- 복구된 콜사인: {metadata.get('total_callsigns', len(callsign_data))}개"
            
        except Exception as e:
            print(f"❌ 복구 실패: {str(e)}")
            return False, f"복구 실패: {str(e)}"
    
    def list_backups(self, limit: int = 10) -> List[Dict]:
        """
        백업 파일 목록 조회
        
        Args:
            limit: 표시할 최대 백업 수
        
        Returns:
            백업 파일 정보 리스트
        """
        backups = []
        
        try:
            if not os.path.exists(self.backup_dir):
                return []
            
            for filename in os.listdir(self.backup_dir):
                if filename.startswith("callsigns_backup_") and filename.endswith(".json"):
                    filepath = os.path.join(self.backup_dir, filename)
                    
                    # 파일 정보 가져오기
                    file_stat = os.stat(filepath)
                    file_size = file_stat.st_size / 1024  # KB 단위
                    
                    # 메타데이터 읽기 시도
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if "metadata" in data:
                                metadata = data["metadata"]
                            else:
                                metadata = {"total_callsigns": len(data)}
                    except:
                        metadata = {}
                    
                    backups.append({
                        "filename": filename,
                        "filepath": filepath,
                        "size_kb": round(file_size, 2),
                        "created": datetime.fromtimestamp(file_stat.st_mtime),
                        "type": "manual" if "manual" in filename else "auto" if "auto" in filename else "upload",
                        "callsign_count": metadata.get("total_callsigns", "Unknown")
                    })
            
            # 최신 순으로 정렬
            backups.sort(key=lambda x: x["created"], reverse=True)
            
            return backups[:limit]
            
        except Exception as e:
            print(f"백업 목록 조회 실패: {e}")
            return []
    
    def cleanup_old_backups(self, days: int = 30):
        """
        오래된 백업 파일 정리
        
        Args:
            days: 보관 기간 (일)
        """
        try:
            if not os.path.exists(self.backup_dir):
                return
            
            cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
            
            for filename in os.listdir(self.backup_dir):
                if filename.startswith("callsigns_backup_"):
                    filepath = os.path.join(self.backup_dir, filename)
                    
                    # 자동 백업만 정리 (수동 백업은 유지)
                    if "auto" in filename:
                        file_stat = os.stat(filepath)
                        if file_stat.st_mtime < cutoff_date:
                            os.remove(filepath)
                            print(f"🗑️ 오래된 백업 삭제: {filename}")
                            
        except Exception as e:
            print(f"백업 정리 실패: {e}")
    
    def restore_from_upload(self, file_content: bytes) -> Tuple[bool, str]:
        """
        업로드된 파일로부터 복구
        
        Args:
            file_content: 업로드된 파일 내용
        
        Returns:
            (성공 여부, 메시지)
        """
        try:
            # JSON 파싱 시도
            backup_data = json.loads(file_content.decode('utf-8'))
            
            # 현재 파일 백업
            if os.path.exists(self.callsign_file):
                pre_restore_backup = f"{self.callsign_file}.pre_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.callsign_file, pre_restore_backup)
                print(f"🔒 업로드 복구 전 백업 생성: {pre_restore_backup}")
            
            # 데이터 추출
            if "metadata" in backup_data and "data" in backup_data:
                callsign_data = backup_data["data"]
                metadata = backup_data["metadata"]
            else:
                callsign_data = backup_data
                metadata = {"total_callsigns": len(callsign_data)}
            
            # 원본 파일에 저장
            with open(self.callsign_file, 'w', encoding='utf-8') as f:
                json.dump(callsign_data, f, ensure_ascii=False, indent=2)
            
            # 업로드된 파일을 백업으로도 저장
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            upload_backup_path = os.path.join(self.backup_dir, f"callsigns_backup_{timestamp}_upload.json")
            
            # 메타데이터와 함께 저장
            upload_backup_data = {
                "metadata": {
                    "backup_time": datetime.now().isoformat(),
                    "backup_type": "upload",
                    "total_callsigns": len(callsign_data),
                    "original_file": "uploaded_file"
                },
                "data": callsign_data
            }
            
            with open(upload_backup_path, 'w', encoding='utf-8') as f:
                json.dump(upload_backup_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 업로드 파일로 복구 완료: {upload_backup_path}")
            return True, f"✅ 업로드 파일로 복구 완료\n- 복구된 콜사인: {metadata.get('total_callsigns', len(callsign_data))}개"
            
        except json.JSONDecodeError:
            return False, "❌ 유효하지 않은 JSON 파일입니다."
        except Exception as e:
            print(f"❌ 업로드 복구 실패: {str(e)}")
            return False, f"❌ 복구 실패: {str(e)}"
    
    def get_backup_info(self, backup_filename: str) -> Optional[Dict]:
        """
        특정 백업 파일의 상세 정보 조회
        
        Args:
            backup_filename: 백업 파일명
        
        Returns:
            백업 정보 딕셔너리 또는 None
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            if not os.path.exists(backup_path):
                return None
            
            file_stat = os.stat(backup_path)
            
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "metadata" in data:
                metadata = data["metadata"]
                callsign_data = data["data"]
            else:
                metadata = {}
                callsign_data = data
            
            return {
                "filename": backup_filename,
                "filepath": backup_path,
                "size_kb": round(file_stat.st_size / 1024, 2),
                "created": datetime.fromtimestamp(file_stat.st_mtime),
                "backup_time": metadata.get("backup_time", "Unknown"),
                "backup_type": metadata.get("backup_type", "Unknown"),
                "total_callsigns": metadata.get("total_callsigns", len(callsign_data)),
                "callsign_list": list(callsign_data.keys()) if isinstance(callsign_data, dict) else []
            }
            
        except Exception as e:
            print(f"백업 정보 조회 실패: {e}")
            return None


# 스케줄러 태스크 클래스
class CallsignBackupScheduler:
    def __init__(self, bot, backup_manager: CallsignBackupManager):
        self.bot = bot
        self.backup_manager = backup_manager
        self.weekly_backup.start()
        print("📅 콜사인 백업 스케줄러 초기화 완료")
    
    @tasks.loop(time=time(hour=8, minute=0))  # 매일 오전 8시에 체크
    async def weekly_backup(self):
        """매주 월요일 오전 8시에 자동 백업"""
        # 월요일인지 확인 (0 = Monday)
        if datetime.now().weekday() == 0:
            print("🔄 주간 콜사인 백업 시작...")
            success, result = self.backup_manager.create_backup("auto")
            
            if success:
                print(f"✅ 주간 백업 성공: {result}")
            else:
                print(f"❌ 주간 백업 실패: {result}")
            
            # 로그 채널에 알림 (선택사항)
            try:
                from config import config
                if hasattr(config, 'LOG_CHANNEL_ID') and config.LOG_CHANNEL_ID:
                    channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
                    if channel:
                        embed = discord.Embed(
                            title="💾 콜사인 자동 백업" if success else "❌ 백업 실패",
                            description=f"{'백업 파일: ' + os.path.basename(result) if success else result}",
                            color=0x00ff00 if success else 0xff0000,
                            timestamp=datetime.now()
                        )
                        
                        if success:
                            # 백업 정보 추가
                            backup_info = self.backup_manager.get_backup_info(os.path.basename(result))
                            if backup_info:
                                embed.add_field(
                                    name="📊 백업 정보",
                                    value=f"• 크기: {backup_info['size_kb']} KB\n"
                                          f"• 콜사인: {backup_info['total_callsigns']}개",
                                    inline=False
                                )
                        
                        await channel.send(embed=embed)
            except Exception as e:
                print(f"로그 채널 알림 실패: {e}")
    
    @weekly_backup.before_loop
    async def before_weekly_backup(self):
        """태스크 시작 전 봇이 준비될 때까지 대기"""
        await self.bot.wait_until_ready()
        print("✅ 콜사인 백업 스케줄러 준비 완료")
    
    def stop(self):
        """스케줄러 중지"""
        self.weekly_backup.cancel()
        print("⏹️ 콜사인 백업 스케줄러 중지됨")