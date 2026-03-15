# mf_config.py - MF 명령어 설정 관리

import json
import os

CONFIG_FILE = "data/mf_config.json"


def _load_config() -> dict:
    """설정 파일 로드"""
    os.makedirs("data", exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] MF 설정 파일 로드 실패: {e}")
    return {"allowed_bot_ids": [557628352828014614, 1325579039888511056]}


def _save_config(config: dict) -> bool:
    """설정 파일 저장"""
    try:
        os.makedirs("data", exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ERROR] MF 설정 파일 저장 실패: {e}")
        return False


def get_allowed_bot_ids() -> list:
    """허용된 봇 ID 목록 조회"""
    config = _load_config()
    return config.get("allowed_bot_ids", [])


def add_bot_id(bot_id: int) -> bool:
    """봇 ID 추가"""
    config = _load_config()
    if bot_id not in config.get("allowed_bot_ids", []):
        config.setdefault("allowed_bot_ids", []).append(bot_id)
        if _save_config(config):
            print(f"[OK] MF 허용 봇 추가: {bot_id}")
            return True
    return False


def remove_bot_id(bot_id: int) -> bool:
    """봇 ID 제거"""
    config = _load_config()
    if bot_id in config.get("allowed_bot_ids", []):
        config["allowed_bot_ids"].remove(bot_id)
        if _save_config(config):
            print(f"[OK] MF 허용 봇 제거: {bot_id}")
            return True
    return False


def is_allowed_bot(bot_id: int) -> bool:
    """허용된 봇인지 확인"""
    return bot_id in get_allowed_bot_ids()
