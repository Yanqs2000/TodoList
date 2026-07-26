use std::{
    fmt::Write as _,
    future::Future,
    net::{Ipv4Addr, TcpListener},
    path::PathBuf,
    process::Command as StdCommand,
    time::Duration,
};

use rand::RngCore;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State, Theme};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use tokio::{
    sync::{watch, Mutex},
    time::Instant,
};

const MAX_START_ATTEMPTS: usize = 3;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(10);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(100);
const PROCESS_CLEANUP_TIMEOUT: Duration = Duration::from_secs(2);
const PROCESS_KILL_TIMEOUT: Duration = Duration::from_secs(1);
const PROCESS_CLEANUP_POLL_INTERVAL: Duration = Duration::from_millis(50);
const SHORTCUT_ROLLBACK_FAILED: &str = "SHORTCUT_ROLLBACK_FAILED";
const SHORTCUT_CLEANUP_FAILED: &str = "SHORTCUT_CLEANUP_FAILED";

#[derive(Clone, Copy, Debug)]
struct StartupBudget {
    deadline: Instant,
}

impl StartupBudget {
    fn new(started: Instant, timeout: Duration) -> Self {
        Self {
            deadline: started + timeout,
        }
    }

    fn remaining(&self, now: Instant) -> Option<Duration> {
        self.deadline
            .checked_duration_since(now)
            .filter(|value| !value.is_zero())
    }

    fn bounded(&self, now: Instant, maximum: Duration) -> Option<Duration> {
        self.remaining(now).map(|remaining| remaining.min(maximum))
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackendConnection {
    base_url: String,
    token: String,
}

impl BackendConnection {
    fn loopback(port: u16, token: String) -> Self {
        Self {
            base_url: format!("http://127.0.0.1:{port}"),
            token,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
enum BackendPhase {
    #[default]
    Stopped,
    Restarting,
    Running,
}

#[derive(Debug, Default)]
struct BackendLifecycle {
    phase: BackendPhase,
}

impl BackendLifecycle {
    fn phase(&self) -> BackendPhase {
        self.phase
    }

    fn begin_restart(&mut self) {
        self.phase = BackendPhase::Restarting;
    }

    fn mark_running(&mut self) {
        self.phase = BackendPhase::Running;
    }

    fn mark_stopped(&mut self) {
        self.phase = BackendPhase::Stopped;
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum BackendError {
    PortBinding(String),
    Sidecar(String),
    SidecarExited,
    HealthCheck(String),
    NotRunning,
}

#[derive(Default)]
struct StartupCoordinator {
    wave: Mutex<()>,
    cached_failure: Mutex<Option<BackendError>>,
}

impl StartupCoordinator {
    async fn ensure<F, Fut>(&self, start: F) -> Result<BackendConnection, BackendError>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<BackendConnection, BackendError>>,
    {
        let _wave = self.wave.lock().await;
        if let Some(error) = self.cached_failure.lock().await.clone() {
            return Err(error);
        }
        self.run_and_cache(start).await
    }

    async fn retry<F, Fut>(&self, start: F) -> Result<BackendConnection, BackendError>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<BackendConnection, BackendError>>,
    {
        let _wave = self.wave.lock().await;
        *self.cached_failure.lock().await = None;
        self.run_and_cache(start).await
    }

    async fn run_and_cache<F, Fut>(&self, start: F) -> Result<BackendConnection, BackendError>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<BackendConnection, BackendError>>,
    {
        let result = start().await;
        *self.cached_failure.lock().await = result.as_ref().err().cloned();
        result
    }

    async fn cache_failure(&self, error: BackendError) {
        *self.cached_failure.lock().await = Some(error);
    }
}

impl BackendError {
    pub(crate) fn public_message(&self) -> &'static str {
        "BACKEND_UNAVAILABLE"
    }
}

impl std::fmt::Display for BackendError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::PortBinding(detail) => {
                write!(formatter, "failed to reserve loopback port: {detail}")
            }
            Self::Sidecar(detail) => write!(formatter, "sidecar process failed: {detail}"),
            Self::SidecarExited => formatter.write_str("sidecar exited before becoming ready"),
            Self::HealthCheck(detail) => write!(formatter, "sidecar health check failed: {detail}"),
            Self::NotRunning => formatter.write_str("sidecar is not running"),
        }
    }
}

#[derive(Debug, Default)]
struct SupervisorInner {
    lifecycle: BackendLifecycle,
    child: Option<CommandChild>,
    connection: Option<BackendConnection>,
    ordinary_failure: Option<BackendError>,
    generation: u64,
    shutting_down: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ExitDisposition {
    Stale,
    StartupFailed,
    EmitUnavailable,
}

impl SupervisorInner {
    fn record_process_exit(&mut self, generation: u64) -> ExitDisposition {
        if self.generation != generation {
            return ExitDisposition::Stale;
        }

        let disposition = match self.lifecycle.phase() {
            BackendPhase::Running => {
                self.ordinary_failure = Some(BackendError::SidecarExited);
                ExitDisposition::EmitUnavailable
            }
            BackendPhase::Stopped | BackendPhase::Restarting => ExitDisposition::StartupFailed,
        };
        self.generation = self.generation.wrapping_add(1);
        if let Some(child) = self.child.take() {
            let _ = child.kill();
        }
        self.connection = None;
        self.lifecycle.mark_stopped();
        disposition
    }
}

pub struct BackendSupervisor {
    database_path: PathBuf,
    client: reqwest::Client,
    coordinator: StartupCoordinator,
    inner: Mutex<SupervisorInner>,
}

impl BackendSupervisor {
    pub fn new(database_path: PathBuf) -> Self {
        Self {
            database_path,
            client: reqwest::Client::new(),
            coordinator: StartupCoordinator::default(),
            inner: Mutex::new(SupervisorInner::default()),
        }
    }

    pub(crate) async fn ensure_running(
        &self,
        app: &AppHandle,
    ) -> Result<BackendConnection, BackendError> {
        self.ensure_with(|| self.start(app)).await
    }

    async fn ensure_with<F, Fut>(&self, start: F) -> Result<BackendConnection, BackendError>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<BackendConnection, BackendError>>,
    {
        self.coordinator
            .ensure(|| async {
                let connection = {
                    let inner = self.inner.lock().await;
                    if let Some(error) = inner.ordinary_failure.clone() {
                        return Err(error);
                    }
                    (inner.lifecycle.phase() == BackendPhase::Running)
                        .then(|| inner.connection.clone())
                        .flatten()
                };
                if let Some(connection) = connection {
                    return Ok(connection);
                }
                start().await
            })
            .await
    }

    async fn restart(&self, app: &AppHandle) -> Result<BackendConnection, BackendError> {
        self.retry_with(|| self.start(app)).await
    }

    async fn retry_with<F, Fut>(&self, start: F) -> Result<BackendConnection, BackendError>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<BackendConnection, BackendError>>,
    {
        self.coordinator
            .retry(|| async {
                {
                    let mut inner = self.inner.lock().await;
                    if inner.shutting_down {
                        return Err(BackendError::NotRunning);
                    }
                    inner.ordinary_failure = None;
                    stop_child(&mut inner);
                }
                start().await
            })
            .await
    }

    async fn start(&self, app: &AppHandle) -> Result<BackendConnection, BackendError> {
        {
            let mut inner = self.inner.lock().await;
            if inner.shutting_down {
                return Err(BackendError::NotRunning);
            }
            inner.lifecycle.begin_restart();
        }
        let budget = StartupBudget::new(Instant::now(), STARTUP_TIMEOUT);
        let mut last_error = None;

        for _ in 0..MAX_START_ATTEMPTS {
            if budget.remaining(Instant::now()).is_none() {
                break;
            }
            if self.inner.lock().await.shutting_down {
                return Err(BackendError::NotRunning);
            }
            terminate_stale_backends(&self.database_path).await?;
            let port = match reserve_loopback_port() {
                Ok(port) => port,
                Err(error) => {
                    last_error = Some(error);
                    continue;
                }
            };
            let connection = BackendConnection::loopback(port, generate_token());
            let command = match app.shell().sidecar("todo-backend") {
                Ok(command) => command,
                Err(error) => {
                    last_error = Some(BackendError::Sidecar(error.to_string()));
                    continue;
                }
            }
            .env("TODO_DATABASE_PATH", &self.database_path)
            .env("TODO_BACKEND_PORT", port.to_string())
            .env("TODO_BACKEND_TOKEN", &connection.token)
            .env("TODO_PARENT_STDIN_WATCH", "1")
            .env(
                "TODO_BACKEND_ALLOW_VITE_ORIGIN",
                if cfg!(debug_assertions) { "1" } else { "0" },
            );
            let (receiver, child) = match command.spawn() {
                Ok(spawned) => spawned,
                Err(error) => {
                    last_error = Some(BackendError::Sidecar(error.to_string()));
                    continue;
                }
            };

            let generation = {
                let mut inner = self.inner.lock().await;
                if inner.shutting_down {
                    let _ = child.kill();
                    return Err(BackendError::NotRunning);
                }
                inner.generation = inner.generation.wrapping_add(1);
                inner.child = Some(child);
                inner.lifecycle.begin_restart();
                inner.generation
            };
            let process_exit = monitor_sidecar(app.clone(), receiver, generation);

            match self
                .wait_for_health(&connection, budget, process_exit)
                .await
            {
                Ok(()) => {
                    let mut inner = self.inner.lock().await;
                    if inner.generation == generation
                        && !inner.shutting_down
                        && inner.child.is_some()
                    {
                        inner.connection = Some(connection.clone());
                        inner.lifecycle.mark_running();
                        return Ok(connection);
                    }
                    if inner.shutting_down {
                        return Err(BackendError::NotRunning);
                    }
                    last_error = Some(BackendError::NotRunning);
                }
                Err(error) => {
                    last_error = Some(error);
                    let mut inner = self.inner.lock().await;
                    if inner.generation == generation {
                        stop_child(&mut inner);
                        if inner.shutting_down {
                            return Err(BackendError::NotRunning);
                        }
                        inner.lifecycle.begin_restart();
                    }
                }
            }
        }

        let should_emit = {
            let mut inner = self.inner.lock().await;
            inner.connection = None;
            inner.lifecycle.mark_stopped();
            !inner.shutting_down
        };
        if should_emit {
            let _ = app.emit("backend-unavailable", ());
        }
        Err(last_error.unwrap_or(BackendError::NotRunning))
    }

    async fn wait_for_health(
        &self,
        connection: &BackendConnection,
        budget: StartupBudget,
        mut process_exit: watch::Receiver<bool>,
    ) -> Result<(), BackendError> {
        let health_url = format!("{}/api/v1/health", connection.base_url);
        loop {
            if *process_exit.borrow() {
                return Err(BackendError::SidecarExited);
            }
            let request_timeout = budget
                .bounded(Instant::now(), Duration::from_secs(1))
                .ok_or_else(startup_timeout_error)?;
            let request = self
                .client
                .get(&health_url)
                .bearer_auth(&connection.token)
                .timeout(request_timeout)
                .send();
            let response = tokio::select! {
                response = request => response,
                _ = process_exit.changed() => return Err(BackendError::SidecarExited),
            };
            if budget.remaining(Instant::now()).is_none() {
                return Err(startup_timeout_error());
            }

            let detail = match response {
                Ok(response) if response.status().is_success() => {
                    let parse_timeout = budget
                        .remaining(Instant::now())
                        .ok_or_else(startup_timeout_error)?;
                    let parsed = tokio::select! {
                        parsed = tokio::time::timeout(parse_timeout, response.json::<HealthResponse>()) => parsed,
                        _ = process_exit.changed() => return Err(BackendError::SidecarExited),
                    };
                    if budget.remaining(Instant::now()).is_none() {
                        return Err(startup_timeout_error());
                    }
                    match parsed {
                        Ok(Ok(health)) if health.status == "ok" => return Ok(()),
                        Ok(Ok(_)) => "unexpected health payload".to_owned(),
                        Ok(Err(error)) => error.to_string(),
                        Err(_) => return Err(startup_timeout_error()),
                    }
                }
                Ok(response) => {
                    format!("HTTP {}", response.status().as_u16())
                }
                Err(error) => error.to_string(),
            };

            let poll_delay = budget
                .bounded(Instant::now(), HEALTH_POLL_INTERVAL)
                .ok_or_else(|| BackendError::HealthCheck(detail.clone()))?;
            tokio::select! {
                _ = tokio::time::sleep(poll_delay) => {}
                _ = process_exit.changed() => return Err(BackendError::SidecarExited),
            }
            if budget.remaining(Instant::now()).is_none() {
                return Err(BackendError::HealthCheck(detail));
            }
        }
    }

    async fn mark_unexpected_exit(&self, app: &AppHandle, generation: u64) {
        let disposition = self.invalidate_unexpected_exit(generation).await;

        if disposition == ExitDisposition::EmitUnavailable {
            let _ = app.emit("backend-unavailable", ());
            self.synchronize_running_exit_failure().await;
        }
    }

    async fn invalidate_unexpected_exit(&self, generation: u64) -> ExitDisposition {
        self.inner.lock().await.record_process_exit(generation)
    }

    async fn synchronize_running_exit_failure(&self) {
        let _wave = self.coordinator.wave.lock().await;
        let failure = self.inner.lock().await.ordinary_failure.clone();
        if let Some(failure) = failure {
            self.coordinator.cache_failure(failure).await;
        }
    }

    pub async fn shutdown(&self) {
        {
            let mut inner = self.inner.lock().await;
            inner.shutting_down = true;
            inner.ordinary_failure = Some(BackendError::NotRunning);
            stop_child(&mut inner);
        }
        self.coordinator
            .cache_failure(BackendError::NotRunning)
            .await;
    }

    async fn persist_shortcut(&self, shortcut: &str) -> Result<(), BackendError> {
        let connection = {
            let inner = self.inner.lock().await;
            if inner.lifecycle.phase() != BackendPhase::Running {
                return Err(BackendError::NotRunning);
            }
            inner.connection.clone().ok_or(BackendError::NotRunning)?
        };

        let response = self
            .client
            .patch(format!("{}/api/v1/settings", connection.base_url))
            .bearer_auth(&connection.token)
            .json(&serde_json::json!({ "shortcut": shortcut }))
            .timeout(Duration::from_secs(10))
            .send()
            .await
            .map_err(|error| BackendError::HealthCheck(error.to_string()))?;
        if response.status().is_success() {
            Ok(())
        } else {
            Err(BackendError::HealthCheck(format!(
                "settings returned HTTP {}",
                response.status().as_u16()
            )))
        }
    }

    async fn ensure_bootstrap(
        &self,
        connection: &BackendConnection,
        preferred_theme: &str,
    ) -> Result<String, BackendError> {
        let response = self
            .client
            .post(format!("{}/api/v1/bootstrap", connection.base_url))
            .bearer_auth(&connection.token)
            .json(&serde_json::json!({ "preferredTheme": preferred_theme }))
            .timeout(Duration::from_secs(10))
            .send()
            .await
            .map_err(|error| BackendError::HealthCheck(error.to_string()))?;
        if !response.status().is_success() {
            return Err(BackendError::HealthCheck(format!(
                "bootstrap returned HTTP {}",
                response.status().as_u16()
            )));
        }
        response
            .json::<BootstrapResponse>()
            .await
            .map(|bootstrap| bootstrap.settings.shortcut)
            .map_err(|error| BackendError::HealthCheck(error.to_string()))
    }
}

fn startup_timeout_error() -> BackendError {
    BackendError::HealthCheck("startup timed out".to_owned())
}

#[derive(Deserialize)]
struct HealthResponse {
    status: String,
}

#[derive(Deserialize)]
struct BootstrapResponse {
    settings: BootstrapSettings,
}

#[derive(Deserialize)]
struct BootstrapSettings {
    shortcut: String,
}

fn stop_child(inner: &mut SupervisorInner) {
    inner.generation = inner.generation.wrapping_add(1);
    if let Some(child) = inner.child.take() {
        let _ = child.kill();
    }
    inner.connection = None;
    inner.lifecycle.mark_stopped();
}

fn matching_backend_pids(
    process_inventory: &str,
    database_path: &std::path::Path,
    current_pid: u32,
) -> Vec<u32> {
    let database_marker = format!("TODO_DATABASE_PATH={}", database_path.display());
    process_inventory
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim_start();
            let pid_end = trimmed.find(char::is_whitespace)?;
            let pid = trimmed[..pid_end].parse::<u32>().ok()?;
            if pid == current_pid {
                return None;
            }
            let marker_start = line.find(&database_marker)?;
            let marker_end = marker_start + database_marker.len();
            let marker_remainder = &line[marker_end..];
            if !marker_remainder.is_empty() && !marker_remainder.starts_with(char::is_whitespace) {
                return None;
            }
            let command = &line[..marker_start];
            (command.contains("/todo-backend") || command.contains("todo_backend.sidecar"))
                .then_some(pid)
        })
        .collect()
}

#[cfg(target_os = "macos")]
fn stale_backend_pids(database_path: &std::path::Path) -> Result<Vec<u32>, BackendError> {
    let output = StdCommand::new("/bin/ps")
        .args(["ewwx", "-o", "pid=,ppid=,command="])
        .output()
        .map_err(|error| BackendError::Sidecar(format!("failed to inspect processes: {error}")))?;
    if !output.status.success() {
        return Err(BackendError::Sidecar(format!(
            "failed to inspect processes: /bin/ps exited with {}",
            output.status
        )));
    }
    let inventory = String::from_utf8_lossy(&output.stdout);
    matching_backend_pids(&inventory, database_path, std::process::id())
        .into_iter()
        .filter_map(|pid| match process_is_todo_backend(pid) {
            Ok(true) => Some(Ok(pid)),
            Ok(false) => None,
            Err(error) => Some(Err(error)),
        })
        .collect()
}

#[cfg(not(target_os = "macos"))]
fn stale_backend_pids(_database_path: &std::path::Path) -> Result<Vec<u32>, BackendError> {
    Ok(Vec::new())
}

#[cfg(target_os = "macos")]
fn process_field(pid: u32, field: &str) -> Result<Option<String>, BackendError> {
    let output = StdCommand::new("/bin/ps")
        .args(["-ww", "-p", &pid.to_string(), "-o", field])
        .output()
        .map_err(|error| {
            BackendError::Sidecar(format!("failed to verify stale backend {pid}: {error}"))
        })?;
    if !output.status.success() {
        return Ok(None);
    }
    Ok(Some(
        String::from_utf8_lossy(&output.stdout).trim().to_owned(),
    ))
}

#[cfg(target_os = "macos")]
fn process_is_todo_backend(pid: u32) -> Result<bool, BackendError> {
    let Some(executable) = process_field(pid, "comm=")? else {
        return Ok(false);
    };
    let command = process_field(pid, "command=")?.unwrap_or_default();
    Ok(is_todo_backend_identity(&executable, &command))
}

fn is_todo_backend_identity(executable: &str, command: &str) -> bool {
    let executable_name = std::path::Path::new(executable)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default();
    let packaged_sidecar = executable_name == "todo-backend"
        || executable_name
            .strip_prefix("todo-backend-")
            .is_some_and(|target| target.ends_with("-apple-darwin"));
    packaged_sidecar
        || (executable_name.contains("python")
            && (command.contains("-m todo_backend.sidecar")
                || command.contains("todo_backend/sidecar.py")))
}

#[cfg(target_os = "macos")]
fn signal_matching_backend(
    database_path: &std::path::Path,
    pid: u32,
    signal: i32,
) -> Result<(), BackendError> {
    if !stale_backend_pids(database_path)?.contains(&pid) {
        return Ok(());
    }
    let result = unsafe { libc::kill(pid as i32, signal) };
    if result == 0 {
        return Ok(());
    }
    let error = std::io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ESRCH) {
        Ok(())
    } else {
        Err(BackendError::Sidecar(format!(
            "failed to signal stale backend {pid}: {error}"
        )))
    }
}

#[cfg(target_os = "macos")]
async fn wait_for_stale_backends(
    database_path: &std::path::Path,
    timeout: Duration,
) -> Result<Vec<u32>, BackendError> {
    let deadline = Instant::now() + timeout;
    loop {
        let remaining = stale_backend_pids(database_path)?;
        if remaining.is_empty() || Instant::now() >= deadline {
            return Ok(remaining);
        }
        tokio::time::sleep(PROCESS_CLEANUP_POLL_INTERVAL).await;
    }
}

async fn terminate_stale_backends(database_path: &std::path::Path) -> Result<(), BackendError> {
    #[cfg(target_os = "macos")]
    {
        let stale = stale_backend_pids(database_path)?;
        for pid in stale {
            signal_matching_backend(database_path, pid, libc::SIGTERM)?;
        }
        let remaining = wait_for_stale_backends(database_path, PROCESS_CLEANUP_TIMEOUT).await?;
        for pid in remaining {
            signal_matching_backend(database_path, pid, libc::SIGKILL)?;
        }
        let remaining = wait_for_stale_backends(database_path, PROCESS_KILL_TIMEOUT).await?;
        if !remaining.is_empty() {
            return Err(BackendError::Sidecar(format!(
                "stale backends did not exit: {remaining:?}"
            )));
        }
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum MonitorAction {
    Continue,
    UnexpectedExit,
}

fn monitor_action(event: Option<&CommandEvent>) -> MonitorAction {
    match event {
        Some(CommandEvent::Stdout(_) | CommandEvent::Stderr(_)) => MonitorAction::Continue,
        Some(CommandEvent::Error(_) | CommandEvent::Terminated(_)) | None => {
            MonitorAction::UnexpectedExit
        }
        Some(_) => MonitorAction::Continue,
    }
}

fn monitor_sidecar(
    app: AppHandle,
    mut receiver: tauri::async_runtime::Receiver<CommandEvent>,
    generation: u64,
) -> watch::Receiver<bool> {
    let (process_exit_tx, process_exit_rx) = watch::channel(false);
    tauri::async_runtime::spawn(async move {
        loop {
            let event = receiver.recv().await;
            if monitor_action(event.as_ref()) == MonitorAction::UnexpectedExit {
                let supervisor = app.state::<BackendSupervisor>();
                supervisor.mark_unexpected_exit(&app, generation).await;
                let _ = process_exit_tx.send(true);
                break;
            }
        }
    });
    process_exit_rx
}

fn reserve_loopback_port() -> Result<u16, BackendError> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))
        .map_err(|error| BackendError::PortBinding(error.to_string()))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| BackendError::PortBinding(error.to_string()))
}

fn generate_token() -> String {
    let mut bytes = [0_u8; 32];
    rand::rng().fill_bytes(&mut bytes);
    let mut token = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        write!(&mut token, "{byte:02x}").expect("writing to a String cannot fail");
    }
    token
}

pub struct ShortcutRegistration {
    current: Mutex<Option<String>>,
}

impl ShortcutRegistration {
    pub fn new() -> Self {
        Self {
            current: Mutex::new(None),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ShortcutStep<'a> {
    EnsureRunning,
    EnsureBootstrap,
    Register(&'a str),
    Unregister(&'a str),
    Persist(&'a str),
}

struct ShortcutTransaction<'a> {
    previous: &'a str,
    next: &'a str,
}

impl<'a> ShortcutTransaction<'a> {
    fn new(previous: &'a str, next: &'a str) -> Self {
        Self { previous, next }
    }

    fn workflow_steps(&self) -> [ShortcutStep<'a>; 5] {
        [
            ShortcutStep::EnsureRunning,
            ShortcutStep::EnsureBootstrap,
            ShortcutStep::Register(self.next),
            ShortcutStep::Unregister(self.previous),
            ShortcutStep::Persist(self.next),
        ]
    }

    fn rollback_steps(&self) -> [ShortcutStep<'a>; 2] {
        [
            ShortcutStep::Unregister(self.next),
            ShortcutStep::Register(self.previous),
        ]
    }
}

fn rollback_shortcut(app: &AppHandle, transaction: &ShortcutTransaction<'_>) -> Result<(), String> {
    let manager = app.global_shortcut();
    let steps = transaction.rollback_steps();
    let remove_result = match steps[0] {
        ShortcutStep::Unregister(shortcut) => manager.unregister(shortcut),
        _ => unreachable!(),
    };
    let restore_result = match steps[1] {
        ShortcutStep::Register(shortcut) => manager.register(shortcut),
        _ => unreachable!(),
    };
    if remove_result.is_err() || restore_result.is_err() {
        return Err(SHORTCUT_ROLLBACK_FAILED.to_owned());
    }
    Ok(())
}

fn preferred_theme(app: &AppHandle) -> &'static str {
    let theme = app
        .get_webview_window("main")
        .and_then(|window| window.theme().ok());
    preferred_theme_for(theme)
}

fn preferred_theme_for(theme: Option<Theme>) -> &'static str {
    if theme == Some(Theme::Dark) {
        "workspace-dark"
    } else {
        "workspace-light"
    }
}

async fn ensure_shortcut_registered(
    app: &AppHandle,
    registration: &ShortcutRegistration,
    stored_shortcut: String,
) -> Result<(), String> {
    let mut current = registration.current.lock().await;
    if current.is_some() {
        return Ok(());
    }
    let _: Shortcut = stored_shortcut
        .parse()
        .map_err(|error| format!("invalid stored shortcut: {error}"))?;
    app.global_shortcut()
        .register(stored_shortcut.as_str())
        .map_err(|error| error.to_string())?;
    *current = Some(stored_shortcut);
    Ok(())
}

pub async fn initialize_shortcut(app: &AppHandle) -> Result<(), String> {
    let supervisor = app.state::<BackendSupervisor>();
    let connection = supervisor
        .ensure_running(app)
        .await
        .map_err(|error| error.public_message().to_owned())?;
    let stored_shortcut = supervisor
        .ensure_bootstrap(&connection, preferred_theme(app))
        .await
        .map_err(|error| error.public_message().to_owned())?;
    ensure_shortcut_registered(app, &app.state::<ShortcutRegistration>(), stored_shortcut).await
}

#[tauri::command]
pub async fn get_backend_connection(
    app: AppHandle,
    supervisor: State<'_, BackendSupervisor>,
) -> Result<BackendConnection, String> {
    supervisor
        .ensure_running(&app)
        .await
        .map_err(|error| error.public_message().to_owned())
}

#[tauri::command]
pub async fn retry_backend(
    app: AppHandle,
    supervisor: State<'_, BackendSupervisor>,
) -> Result<BackendConnection, String> {
    supervisor
        .restart(&app)
        .await
        .map_err(|error| error.public_message().to_owned())
}

#[tauri::command]
pub async fn set_global_shortcut(
    app: AppHandle,
    supervisor: State<'_, BackendSupervisor>,
    registration: State<'_, ShortcutRegistration>,
    shortcut: String,
) -> Result<(), String> {
    let _: Shortcut = shortcut
        .parse()
        .map_err(|error| format!("invalid shortcut: {error}"))?;
    let connection = supervisor
        .ensure_running(&app)
        .await
        .map_err(|error| error.public_message().to_owned())?;
    let stored_shortcut = supervisor
        .ensure_bootstrap(&connection, preferred_theme(&app))
        .await
        .map_err(|error| error.public_message().to_owned())?;
    ensure_shortcut_registered(&app, &registration, stored_shortcut).await?;

    let mut previous = registration.current.lock().await;
    let previous_shortcut = previous
        .as_deref()
        .ok_or_else(|| "SHORTCUT_NOT_INITIALIZED".to_owned())?;
    if previous_shortcut == shortcut {
        return supervisor
            .persist_shortcut(&shortcut)
            .await
            .map_err(|error| error.public_message().to_owned());
    }

    let transaction = ShortcutTransaction::new(previous_shortcut, &shortcut);
    let workflow_steps = transaction.workflow_steps();
    app.global_shortcut()
        .register(match workflow_steps[2] {
            ShortcutStep::Register(value) => value,
            _ => unreachable!(),
        })
        .map_err(|error| error.to_string())?;
    let unregister_previous = match workflow_steps[3] {
        ShortcutStep::Unregister(value) => value,
        _ => unreachable!(),
    };
    if let Err(error) = app.global_shortcut().unregister(unregister_previous) {
        if app.global_shortcut().unregister(shortcut.as_str()).is_err() {
            return Err(SHORTCUT_CLEANUP_FAILED.to_owned());
        }
        return Err(error.to_string());
    }

    let persist_next = match workflow_steps[4] {
        ShortcutStep::Persist(value) => value,
        _ => unreachable!(),
    };
    if let Err(error) = supervisor.persist_shortcut(persist_next).await {
        rollback_shortcut(&app, &transaction)?;
        return Err(error.public_message().to_owned());
    }

    *previous = Some(shortcut);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };

    #[test]
    fn stale_process_inventory_only_selects_todo_backends_for_the_same_database() {
        let database_path =
            PathBuf::from("/Users/test/Library/Application Support/com.todo/todo.sqlite3");
        let process_inventory = "\
101 1 /Applications/Todo List.app/Contents/MacOS/todo-backend TODO_DATABASE_PATH=/Users/test/Library/Application Support/com.todo/todo.sqlite3 TODO_BACKEND_PORT=40001
102 101 /Applications/Todo List.app/Contents/MacOS/todo-backend TODO_DATABASE_PATH=/Users/test/Library/Application Support/com.todo/todo.sqlite3 TODO_BACKEND_PORT=40001
103 1 /tmp/todo-backend TODO_DATABASE_PATH=/tmp/debug/todo.sqlite3 TODO_BACKEND_PORT=40002
104 1 /bin/zsh -c echo todo-backend TODO_DATABASE_PATH=/Users/test/Library/Application Support/com.todo/todo.sqlite3
105 1 python -m todo_backend.sidecar TODO_DATABASE_PATH=/Users/test/Library/Application Support/com.todo/todo.sqlite3 TODO_BACKEND_PORT=40003
900 1 /Applications/Todo List.app/Contents/MacOS/todo-backend TODO_DATABASE_PATH=/Users/test/Library/Application Support/com.todo/todo.sqlite3";

        assert_eq!(
            matching_backend_pids(process_inventory, &database_path, 900),
            vec![101, 102, 105]
        );
    }

    #[test]
    fn executable_identity_rejects_shells_and_similarly_named_tools() {
        assert!(is_todo_backend_identity(
            "/Applications/Todo List.app/Contents/MacOS/todo-backend",
            "/Applications/Todo List.app/Contents/MacOS/todo-backend"
        ));
        assert!(is_todo_backend_identity(
            "/opt/homebrew/bin/python3.12",
            "python -m todo_backend.sidecar"
        ));
        assert!(!is_todo_backend_identity(
            "/bin/zsh",
            "/bin/zsh -c /tmp/todo-backend"
        ));
        assert!(!is_todo_backend_identity(
            "/tmp/todo-backend-debugger",
            "/tmp/todo-backend-debugger"
        ));
    }

    #[test]
    fn token_has_256_bits_of_hex_entropy() {
        let token = generate_token();

        assert_eq!(token.len(), 64);
        assert!(token.chars().all(|value| value.is_ascii_hexdigit()));
    }

    #[test]
    fn lifecycle_moves_between_stopped_restarting_and_running() {
        let mut lifecycle = BackendLifecycle::default();

        assert_eq!(lifecycle.phase(), BackendPhase::Stopped);
        lifecycle.begin_restart();
        assert_eq!(lifecycle.phase(), BackendPhase::Restarting);
        lifecycle.mark_running();
        assert_eq!(lifecycle.phase(), BackendPhase::Running);
        lifecycle.begin_restart();
        assert_eq!(lifecycle.phase(), BackendPhase::Restarting);
        lifecycle.mark_stopped();
        assert_eq!(lifecycle.phase(), BackendPhase::Stopped);
    }

    #[test]
    fn connection_serializes_only_loopback_url_and_token() {
        let connection = BackendConnection::loopback(43_123, "secret-token".to_owned());

        assert_eq!(
            serde_json::to_value(connection).unwrap(),
            json!({
              "baseUrl": "http://127.0.0.1:43123",
              "token": "secret-token"
            })
        );
    }

    #[test]
    fn public_errors_do_not_expose_internal_details() {
        let error = BackendError::HealthCheck("Bearer secret-token at /private/db".to_owned());

        assert_eq!(error.public_message(), "BACKEND_UNAVAILABLE");
    }

    #[test]
    fn one_startup_budget_is_shared_across_all_attempts() {
        let started = Instant::now();
        let budget = StartupBudget::new(started, Duration::from_secs(10));

        assert_eq!(
            budget.remaining(started + Duration::from_secs(3)),
            Some(Duration::from_secs(7))
        );
        assert_eq!(
            budget.remaining(started + Duration::from_secs(9)),
            Some(Duration::from_secs(1))
        );
        assert_eq!(budget.remaining(started + Duration::from_secs(10)), None);
    }

    #[test]
    fn request_and_poll_delays_are_bounded_by_remaining_budget() {
        let started = Instant::now();
        let budget = StartupBudget::new(started, Duration::from_secs(10));
        let nearly_expired = started + Duration::from_millis(9_950);

        assert_eq!(
            budget.bounded(nearly_expired, Duration::from_secs(1)),
            Some(Duration::from_millis(50))
        );
        assert_eq!(
            budget.bounded(nearly_expired, HEALTH_POLL_INTERVAL),
            Some(Duration::from_millis(50))
        );
    }

    #[test]
    fn active_running_exit_invalidates_connection_once() {
        let mut inner = SupervisorInner::default();
        inner.generation = 7;
        inner.lifecycle.mark_running();
        inner.connection = Some(BackendConnection::loopback(43_123, "token".to_owned()));

        assert_eq!(
            inner.record_process_exit(7),
            ExitDisposition::EmitUnavailable
        );
        assert_eq!(inner.lifecycle.phase(), BackendPhase::Stopped);
        assert!(inner.connection.is_none());
        assert_eq!(inner.record_process_exit(7), ExitDisposition::Stale);
    }

    #[test]
    fn active_startup_exit_invalidates_without_emitting() {
        let mut inner = SupervisorInner::default();
        inner.generation = 3;
        inner.lifecycle.begin_restart();

        assert_eq!(inner.record_process_exit(3), ExitDisposition::StartupFailed);
        assert_eq!(inner.lifecycle.phase(), BackendPhase::Stopped);
        assert_eq!(inner.record_process_exit(2), ExitDisposition::Stale);
    }

    #[test]
    fn stale_generation_does_not_invalidate_active_connection() {
        let mut inner = SupervisorInner::default();
        inner.generation = 8;
        inner.lifecycle.mark_running();
        inner.connection = Some(BackendConnection::loopback(43_123, "token".to_owned()));

        assert_eq!(inner.record_process_exit(7), ExitDisposition::Stale);
        assert_eq!(inner.lifecycle.phase(), BackendPhase::Running);
        assert!(inner.connection.is_some());
        assert_eq!(inner.generation, 8);
    }

    #[test]
    fn monitor_treats_error_termination_and_channel_close_as_exit() {
        assert_eq!(
            monitor_action(Some(&CommandEvent::Stdout(vec![]))),
            MonitorAction::Continue
        );
        assert_eq!(
            monitor_action(Some(&CommandEvent::Error("wait failed".to_owned()))),
            MonitorAction::UnexpectedExit
        );
        assert_eq!(
            monitor_action(Some(&CommandEvent::Terminated(
                tauri_plugin_shell::process::TerminatedPayload {
                    code: Some(1),
                    signal: None,
                }
            ))),
            MonitorAction::UnexpectedExit
        );
        assert_eq!(monitor_action(None), MonitorAction::UnexpectedExit);
    }

    #[test]
    fn bootstrap_preferred_theme_follows_dark_system_theme() {
        assert_eq!(preferred_theme_for(Some(Theme::Dark)), "workspace-dark");
        assert_eq!(preferred_theme_for(Some(Theme::Light)), "workspace-light");
        assert_eq!(preferred_theme_for(None), "workspace-light");
    }

    #[tokio::test(flavor = "current_thread")]
    async fn concurrent_ensure_callers_share_failure_until_explicit_retry() {
        let coordinator = Arc::new(StartupCoordinator::default());
        let starts = Arc::new(AtomicUsize::new(0));
        let first_failure = BackendError::HealthCheck("first wave failed".to_owned());
        let mut callers = Vec::new();

        for _ in 0..8 {
            let coordinator = coordinator.clone();
            let starts = starts.clone();
            let first_failure = first_failure.clone();
            callers.push(tokio::spawn(async move {
                coordinator
                    .ensure(|| async move {
                        starts.fetch_add(1, Ordering::SeqCst);
                        tokio::task::yield_now().await;
                        Err(first_failure)
                    })
                    .await
            }));
        }

        for caller in callers {
            assert_eq!(caller.await.unwrap().unwrap_err(), first_failure);
        }
        assert_eq!(starts.load(Ordering::SeqCst), 1);

        let retry_failure = BackendError::HealthCheck("retry wave failed".to_owned());
        let retry_started = Arc::new(tokio::sync::Notify::new());
        let release_retry = Arc::new(tokio::sync::Notify::new());
        let retry_task = tokio::spawn({
            let coordinator = coordinator.clone();
            let retry_started = retry_started.clone();
            let release_retry = release_retry.clone();
            let retry_failure = retry_failure.clone();
            let starts = starts.clone();
            async move {
                coordinator
                    .retry(|| async move {
                        starts.fetch_add(1, Ordering::SeqCst);
                        retry_started.notify_one();
                        release_retry.notified().await;
                        Err(retry_failure)
                    })
                    .await
            }
        });
        retry_started.notified().await;

        let mut retry_joiners = Vec::new();
        for _ in 0..4 {
            let coordinator = coordinator.clone();
            retry_joiners.push(tokio::spawn(async move {
                coordinator
                    .ensure(|| async { panic!("ensure caller must join the active retry wave") })
                    .await
            }));
        }
        tokio::task::yield_now().await;
        release_retry.notify_one();

        assert_eq!(retry_task.await.unwrap().unwrap_err(), retry_failure);
        for joiner in retry_joiners {
            assert_eq!(joiner.await.unwrap().unwrap_err(), retry_failure);
        }
        assert_eq!(starts.load(Ordering::SeqCst), 2);
        assert_eq!(
            coordinator
                .ensure(|| async { panic!("cached retry failure must suppress a new wave") })
                .await
                .unwrap_err(),
            retry_failure
        );
        assert_eq!(starts.load(Ordering::SeqCst), 2);
    }

    #[tokio::test(flavor = "current_thread")]
    async fn monitor_invalidation_blocks_health_and_ordinary_restart_until_retry() {
        let supervisor = Arc::new(BackendSupervisor::new(PathBuf::from("test.sqlite3")));
        let startup_generation = 7;
        let coordinator_wave = supervisor.coordinator.wave.lock().await;
        let mut startup_inner = supervisor.inner.lock().await;
        startup_inner.generation = startup_generation;
        startup_inner.lifecycle.begin_restart();

        let monitor = tokio::spawn({
            let supervisor = supervisor.clone();
            async move {
                supervisor
                    .invalidate_unexpected_exit(startup_generation)
                    .await
            }
        });
        tokio::task::yield_now().await;
        let health = tokio::spawn({
            let supervisor = supervisor.clone();
            async move {
                let mut inner = supervisor.inner.lock().await;
                if inner.generation == startup_generation && !inner.shutting_down {
                    inner.connection = Some(BackendConnection::loopback(
                        43_123,
                        "stale-health-token".to_owned(),
                    ));
                    inner.lifecycle.mark_running();
                    true
                } else {
                    false
                }
            }
        });
        tokio::task::yield_now().await;
        drop(startup_inner);

        assert_eq!(
            tokio::time::timeout(Duration::from_secs(1), monitor)
                .await
                .expect("startup monitor must not wait for the coordinator wave")
                .unwrap(),
            ExitDisposition::StartupFailed
        );
        assert!(!health.await.unwrap());
        drop(coordinator_wave);

        let running_generation = 20;
        {
            let mut inner = supervisor.inner.lock().await;
            inner.generation = running_generation;
            inner.lifecycle.mark_running();
            inner.connection = Some(BackendConnection::loopback(
                43_124,
                "running-token".to_owned(),
            ));
        }

        let coordinator_wave = supervisor.coordinator.wave.lock().await;
        assert_eq!(
            supervisor
                .invalidate_unexpected_exit(running_generation)
                .await,
            ExitDisposition::EmitUnavailable
        );

        let starts = Arc::new(AtomicUsize::new(0));
        let ordinary_ensure = tokio::spawn({
            let supervisor = supervisor.clone();
            let starts = starts.clone();
            async move {
                supervisor
                    .ensure_with(|| async move {
                        starts.fetch_add(1, Ordering::SeqCst);
                        Ok(BackendConnection::loopback(
                            43_125,
                            "unexpected-restart".to_owned(),
                        ))
                    })
                    .await
            }
        });
        tokio::task::yield_now().await;
        let cache_sync = tokio::spawn({
            let supervisor = supervisor.clone();
            async move { supervisor.synchronize_running_exit_failure().await }
        });
        tokio::task::yield_now().await;
        drop(coordinator_wave);

        assert_eq!(
            ordinary_ensure.await.unwrap().unwrap_err(),
            BackendError::SidecarExited
        );
        cache_sync.await.unwrap();
        assert_eq!(starts.load(Ordering::SeqCst), 0);
        assert_eq!(
            supervisor
                .ensure_with(|| async {
                    panic!("ordinary ensure must not restart an unexpectedly exited backend")
                })
                .await
                .unwrap_err(),
            BackendError::SidecarExited
        );

        let retried_connection = BackendConnection::loopback(43_126, "retry-token".to_owned());
        assert_eq!(
            supervisor
                .retry_with({
                    let starts = starts.clone();
                    let retried_connection = retried_connection.clone();
                    || async move {
                        starts.fetch_add(1, Ordering::SeqCst);
                        Ok(retried_connection)
                    }
                })
                .await
                .unwrap(),
            retried_connection
        );
        assert_eq!(starts.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn shortcut_workflow_initializes_backend_before_registration_and_restores_on_rollback() {
        let transaction = ShortcutTransaction::new("Cmd+Alt+KeyT", "Cmd+Shift+KeyN");

        assert_eq!(
            transaction.workflow_steps(),
            [
                ShortcutStep::EnsureRunning,
                ShortcutStep::EnsureBootstrap,
                ShortcutStep::Register("Cmd+Shift+KeyN"),
                ShortcutStep::Unregister("Cmd+Alt+KeyT"),
                ShortcutStep::Persist("Cmd+Shift+KeyN")
            ]
        );
        assert_eq!(
            transaction.rollback_steps(),
            [
                ShortcutStep::Unregister("Cmd+Shift+KeyN"),
                ShortcutStep::Register("Cmd+Alt+KeyT")
            ]
        );
        assert_eq!(SHORTCUT_ROLLBACK_FAILED, "SHORTCUT_ROLLBACK_FAILED");
        assert_eq!(SHORTCUT_CLEANUP_FAILED, "SHORTCUT_CLEANUP_FAILED");
    }
}
