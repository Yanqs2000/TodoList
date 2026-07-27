from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from todo_backend.agent.checkpoints import CheckpointStore


class CounterState(TypedDict):
    value: int


def _graph(store: CheckpointStore):
    builder = StateGraph(CounterState)
    builder.add_node("increment", lambda state: {"value": state["value"] + 1})
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    return builder.compile(checkpointer=store.saver)


def test_checkpoint_survives_reopen_and_can_be_deleted(tmp_path: Path) -> None:
    path = tmp_path / "assistant_graph.sqlite3"
    config = {"configurable": {"thread_id": "turn:t1"}}

    first = CheckpointStore(path)
    assert _graph(first).invoke({"value": 1}, config=config)["value"] == 2
    assert first.has_thread("turn:t1") is True
    first.close()

    second = CheckpointStore(path)
    assert _graph(second).get_state(config).values["value"] == 2
    second.delete_thread("turn:t1")
    assert second.has_thread("turn:t1") is False
    second.close()
