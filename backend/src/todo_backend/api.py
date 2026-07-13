# pyright: reportUnusedFunction=false

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from todo_backend.auth import require_token
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.errors import DatabaseVersionError
from todo_backend.models import (
    BootstrapCommand,
    BootstrapResponse,
    CompletionCommand,
    CompletionResponse,
    CreateTaskCommand,
    ReminderClaimCommand,
    ReminderClaimResponse,
    ReplaceTaskOrderCommand,
    SettingsPatchCommand,
    SettingsResponse,
    TaskListResponse,
    TaskResponse,
    UpdateTaskCommand,
)
from todo_backend.repositories.tasks import InvalidTaskOrderError, TaskNotFoundError
from todo_backend.services.bootstrap import BootstrapService
from todo_backend.services.reminders import ReminderService
from todo_backend.services.settings import SettingsService
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
    initialization_error: sqlite3.Error | DatabaseVersionError | None = None
    try:
        resolved_database.initialize()
    except (sqlite3.Error, DatabaseVersionError) as error:
        initialization_error = error
    task_service = TaskService(resolved_database)
    bootstrap_service = BootstrapService(resolved_database)
    reminder_service = ReminderService(resolved_database)
    settings_service = SettingsService(resolved_database)

    app = FastAPI()
    app.dependency_overrides[Settings.from_env] = lambda: resolved_settings
    app.add_exception_handler(TaskNotFoundError, _task_not_found_handler)
    app.add_exception_handler(InvalidTaskOrderError, _invalid_task_order_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(HTTPException, _http_error_handler)
    app.add_exception_handler(sqlite3.Error, _database_error_handler)
    app.add_exception_handler(DatabaseVersionError, _database_error_handler)
    app.add_exception_handler(Exception, _internal_error_handler)

    def _require_database() -> None:
        if initialization_error is not None:
            raise initialization_error

    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(require_token), Depends(_require_database)],
    )

    @router.get("/health")
    def _health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/bootstrap", response_model=BootstrapResponse, response_model_exclude_none=True)
    def _bootstrap(command: BootstrapCommand) -> BootstrapResponse:
        return bootstrap_service.bootstrap(command.preferred_theme)

    @router.post(
        "/tasks",
        response_model=TaskResponse,
        response_model_exclude_none=True,
        status_code=status.HTTP_201_CREATED,
    )
    def _create_task(command: CreateTaskCommand) -> TaskResponse:
        return TaskResponse(task=task_service.create(command))

    @router.patch(
        "/tasks/{task_id}",
        response_model=TaskResponse,
        response_model_exclude_none=True,
    )
    def _update_task(task_id: str, command: UpdateTaskCommand) -> TaskResponse:
        return TaskResponse(task=task_service.update(task_id, command))

    @router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
    def _delete_task(task_id: str) -> Response:
        task_service.delete(task_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.put(
        "/tasks/order",
        response_model=TaskListResponse,
        response_model_exclude_none=True,
    )
    def _replace_task_order(command: ReplaceTaskOrderCommand) -> TaskListResponse:
        return TaskListResponse(tasks=task_service.replace_order(command.task_ids))

    @router.put(
        "/tasks/{task_id}/completion",
        response_model=CompletionResponse,
        response_model_exclude_none=True,
    )
    def _set_task_completion(
        task_id: str,
        command: CompletionCommand,
    ) -> CompletionResponse:
        return task_service.set_completion(task_id, command)

    @router.post(
        "/reminders/claim",
        response_model=ReminderClaimResponse,
    )
    def _claim_reminder(command: ReminderClaimCommand) -> ReminderClaimResponse:
        return reminder_service.claim(command)

    @router.patch(
        "/settings",
        response_model=SettingsResponse,
    )
    def _patch_settings(command: SettingsPatchCommand) -> SettingsResponse:
        return SettingsResponse(settings=settings_service.patch(command))

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


def _validation_error_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "INVALID_REQUEST", "Invalid request")


def _http_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    http_error = cast(HTTPException, error)
    if http_error.status_code == status.HTTP_401_UNAUTHORIZED:
        return _error_response(
            http_error.status_code,
            "UNAUTHORIZED",
            "Unauthorized",
            headers=http_error.headers,
        )
    return _error_response(http_error.status_code, "REQUEST_FAILED", "Request failed")


def _database_error_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return _error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DATABASE_UNAVAILABLE",
        "Database unavailable",
    )


def _internal_error_handler(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    return _error_response(500, "INTERNAL_ERROR", "Internal error")


def _error_response(
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )
