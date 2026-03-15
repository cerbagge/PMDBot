from collections import deque
import threading

# 3개의 병렬 대기열을 지원하는 QueueManager

class QueueManager:
    NUM_QUEUES = 3  # 병렬 대기열 개수

    def __init__(self):
        # 3개의 독립적인 대기열
        self.queues = [[] for _ in range(self.NUM_QUEUES)]
        # 각 대기열의 처리 상태
        self.processing = [False for _ in range(self.NUM_QUEUES)]
        # 다음에 추가할 대기열 인덱스 (라운드 로빈)
        self._next_queue_index = 0
        # 스레드 안전성을 위한 락
        self._lock = threading.Lock()

    def _get_all_users(self) -> set:
        """모든 대기열의 사용자 ID 집합 반환"""
        all_users = set()
        for q in self.queues:
            all_users.update(q)
        return all_users

    def is_user_in_queue(self, user_id: int) -> bool:
        """사용자가 어떤 대기열에든 있는지 확인"""
        with self._lock:
            return user_id in self._get_all_users()

    def add_user(self, user_id: int):
        """사용자를 대기열에 추가 (라운드 로빈 분배, 중복 방지)"""
        with self._lock:
            if user_id in self._get_all_users():
                return False

            # 라운드 로빈으로 대기열 분배
            queue_idx = self._next_queue_index
            self.queues[queue_idx].append(user_id)
            self._next_queue_index = (self._next_queue_index + 1) % self.NUM_QUEUES
            return True

    def add_user_priority(self, user_id: int):
        """사용자를 가장 짧은 대기열 맨 앞에 우선 추가 (중복 방지)"""
        with self._lock:
            if user_id in self._get_all_users():
                return False

            # 가장 짧은 대기열 찾기
            min_idx = min(range(self.NUM_QUEUES), key=lambda i: len(self.queues[i]))
            self.queues[min_idx].insert(0, user_id)
            return True

    def add_user_back(self, user_id: int):
        """사용자를 가장 짧은 대기열 맨 뒤에 추가 (UUID 없는 사용자 후순위 처리용, 중복 방지)"""
        with self._lock:
            if user_id in self._get_all_users():
                return False

            min_idx = min(range(self.NUM_QUEUES), key=lambda i: len(self.queues[i]))
            self.queues[min_idx].append(user_id)
            return True

    def get_all_and_clear(self, queue_index: int = None) -> list:
        """대기열에서 모든 사용자를 꺼내고 비우기 (bulk 처리용)

        Args:
            queue_index: 특정 대기열 인덱스 (None이면 모든 대기열)

        Returns:
            사용자 ID 리스트
        """
        with self._lock:
            users = []
            if queue_index is not None and 0 <= queue_index < self.NUM_QUEUES:
                users = list(self.queues[queue_index])
                self.queues[queue_index].clear()
            else:
                for q in self.queues:
                    users.extend(q)
                    q.clear()
            return users

    def get_next(self, queue_index: int = 0):
        """특정 대기열에서 다음 사용자 가져오기"""
        with self._lock:
            if 0 <= queue_index < self.NUM_QUEUES and self.queues[queue_index]:
                return self.queues[queue_index].pop(0)
            return None

    def get_queue_size(self, queue_index: int = None) -> int:
        """대기열 크기 반환 (인덱스 없으면 전체 합계)"""
        with self._lock:
            if queue_index is not None and 0 <= queue_index < self.NUM_QUEUES:
                return len(self.queues[queue_index])
            return sum(len(q) for q in self.queues)

    def get_queue_sizes(self) -> list:
        """모든 대기열의 크기 리스트 반환"""
        with self._lock:
            return [len(q) for q in self.queues]

    def is_processing(self, queue_index: int = None) -> bool:
        """처리 중인지 여부 반환 (인덱스 없으면 하나라도 처리 중이면 True)"""
        with self._lock:
            if queue_index is not None and 0 <= queue_index < self.NUM_QUEUES:
                return self.processing[queue_index]
            return any(self.processing)

    def set_processing(self, queue_index: int, value: bool):
        """특정 대기열의 처리 상태 설정"""
        with self._lock:
            if 0 <= queue_index < self.NUM_QUEUES:
                self.processing[queue_index] = value

    def clear_queue(self, queue_index: int = None) -> int:
        """대기열 초기화 및 제거된 항목 수 반환 (인덱스 없으면 전체 초기화)"""
        with self._lock:
            if queue_index is not None and 0 <= queue_index < self.NUM_QUEUES:
                count = len(self.queues[queue_index])
                self.queues[queue_index].clear()
                return count

            total = sum(len(q) for q in self.queues)
            for q in self.queues:
                q.clear()
            return total

    def get_status(self) -> dict:
        """대기열 상태 정보 반환"""
        with self._lock:
            return {
                "total_size": sum(len(q) for q in self.queues),
                "queue_sizes": [len(q) for q in self.queues],
                "processing": list(self.processing),
                "any_processing": any(self.processing)
            }

queue_manager = QueueManager()
