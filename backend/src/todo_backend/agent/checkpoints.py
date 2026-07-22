import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver


class CheckpointStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        serializer = JsonPlusSerializer(
            pickle_fallback=False,
            allowed_msgpack_modules=None,
        )
        self.saver = SqliteSaver(self._connection, serde=serializer)
        self._closed = False

    @staticmethod
    def config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": thread_id}}

    def has_thread(self, thread_id: str) -> bool:
        return self.saver.get_tuple(self.config(thread_id)) is not None

    def delete_thread(self, thread_id: str) -> None:
        self.saver.delete_thread(thread_id)

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True
