# commands/__init__.py - 명령어 자동 로더

import os
import importlib
import discord
from discord import app_commands
from typing import Dict, List


def safe_print(msg):
    """유니코드 문자 출력 오류 방지용 print 함수"""
    try:
        print(msg)
    except UnicodeEncodeError:
        # 유니코드 문자를 ASCII로 대체
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class CommandLoader:
    """명령어를 자동으로 로드하고 등록하는 클래스"""

    def __init__(self, bot):
        self.bot = bot
        self.commands: Dict[str, any] = {}
        self.message_handlers: List[callable] = []

    def load_commands(self):
        """commands 폴더의 모든 명령어 로드"""
        commands_dir = os.path.dirname(__file__)

        # 모든 하위 폴더 탐색
        for root, dirs, files in os.walk(commands_dir):
            # __pycache__ 폴더 무시
            dirs[:] = [d for d in dirs if d != '__pycache__']

            for file in files:
                if file.endswith('.py') and file != '__init__.py':
                    # 파일 경로를 모듈 경로로 변환
                    rel_path = os.path.relpath(os.path.join(root, file), commands_dir)
                    module_path = rel_path.replace(os.sep, '.').replace('.py', '')
                    full_module_path = f'commands.{module_path}'

                    try:
                        # 모듈 로드
                        module = importlib.import_module(full_module_path)

                        # setup 함수가 있으면 호출
                        if hasattr(module, 'setup'):
                            module.setup(self.bot)
                            safe_print(f"  [OK] 명령어 로드: {full_module_path}")
                            self.commands[full_module_path] = module

                        # message_handler 함수가 있으면 등록
                        if hasattr(module, 'message_handler'):
                            safe_print(f"  [MSG] 메시지 핸들러 등록: {full_module_path}")
                            self.message_handlers.append(module.message_handler)

                    except Exception as e:
                        safe_print(f"  [FAIL] 명령어 로드 실패 ({full_module_path}): {e}")
                        import traceback
                        traceback.print_exc()

        safe_print(f"[OK] 총 {len(self.commands)}개 명령어 모듈 로드됨")
        safe_print(f"[OK] 총 {len(self.message_handlers)}개 메시지 핸들러 등록됨")

    async def handle_message(self, message):
        """등록된 모든 메시지 핸들러 실행"""
        for handler in self.message_handlers:
            try:
                result = await handler(self.bot, message)
                # 핸들러가 True를 반환하면 다른 핸들러는 실행하지 않음
                if result is True:
                    return True
            except Exception as e:
                print(f"❌ 메시지 핸들러 오류: {e}")
                import traceback
                traceback.print_exc()
        return False


def setup(bot):
    """봇에 명령어 로더 설정"""
    loader = CommandLoader(bot)
    loader.load_commands()
    bot.command_loader = loader
    return loader
