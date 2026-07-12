from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


StrictText = Annotated[str, Field(strict=True, min_length=1, max_length=10_000)]
StrictNotes = Annotated[str, Field(strict=True, max_length=10_000)]
Priority = Literal["low", "medium", "high"]
Category = Literal["work", "study", "life", "other"]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class TimeField(WireModel):
    start: StrictText
    end: StrictText | None = None


class Task(WireModel):
    id: str
    text: StrictText
    completed: bool
    priority: Priority
    created_at: int = Field(alias="createdAt")
    time: TimeField | None = None
    category: Category
    notes: StrictNotes | None = None


class CreateTaskCommand(WireModel):
    text: StrictText
    priority: Priority
    time: TimeField | None = None
    category: Category = "other"
    notes: StrictNotes | None = None


class UpdateTaskCommand(WireModel):
    text: StrictText | None = None
    priority: Priority | None = None
    time: TimeField | None = None
    category: Category | None = None
    notes: StrictNotes | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "UpdateTaskCommand":
        for field_name in ("text", "priority", "category"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class ReplaceTaskOrderCommand(WireModel):
    task_ids: list[str] = Field(alias="taskIds")


class BootstrapCommand(WireModel):
    pass


class TaskResponse(WireModel):
    task: Task


class TaskListResponse(WireModel):
    tasks: list[Task]
