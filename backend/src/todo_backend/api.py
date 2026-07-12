# pyright: reportUnusedFunction=false

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from todo_backend.auth import require_token
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import (
    BootstrapCommand,
    CreateTaskCommand,
    ReplaceTaskOrderCommand,
    TaskListResponse,
    TaskResponse,
    UpdateTaskCommand,
)
from todo_backend.repositories.tasks import InvalidTaskOrderError, TaskNotFoundError
from todo_backend.services.tasks import TaskService


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_database = database or Database(
        resolved_settings.database_path,
        Path(__file__).parents[2] / "migrations",
    )
    resolved_database.initialize()
    service = TaskService(resolved_database)

    app = FastAPI()
    app.dependency_overrides[Settings.from_env] = lambda: resolved_settings
    app.add_exception_handler(TaskNotFoundError, _task_not_found_handler)
    app.add_exception_handler(InvalidTaskOrderError, _invalid_task_order_handler)

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])

    @router.post("/bootstrap", response_model=TaskListResponse, response_model_exclude_none=True)
    def _bootstrap(_: BootstrapCommand) -> TaskListResponse:
        return TaskListResponse(tasks=service.list_all())

    @router.post(
        "/tasks",
        response_model=TaskResponse,
        response_model_exclude_none=True,
        status_code=status.HTTP_201_CREATED,
    )
    def _create_task(command: CreateTaskCommand) -> TaskResponse:
        return TaskResponse(task=service.create(command))

    @router.patch(
        "/tasks/{task_id}",
        response_model=TaskResponse,
        response_model_exclude_none=True,
    )
    def _update_task(task_id: str, command: UpdateTaskCommand) -> TaskResponse:
        return TaskResponse(task=service.update(task_id, command))

    @router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
    def _delete_task(task_id: str) -> Response:
        service.delete(task_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.put(
        "/tasks/order",
        response_model=TaskListResponse,
        response_model_exclude_none=True,
    )
    def _replace_task_order(command: ReplaceTaskOrderCommand) -> TaskListResponse:
        return TaskListResponse(tasks=service.replace_order(command.task_ids))

    app.include_router(router)
    return app


def _task_not_found_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found"}},
    )


def _invalid_task_order_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": "INVALID_TASK_ORDER",
                "message": "Invalid task order",
            }
        },
    )
