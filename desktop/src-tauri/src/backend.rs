use std::{
    fmt::Write as _,
    net::{Ipv4Addr, TcpListener},
    path::PathBuf,
    time::Duration,
};

use rand::RngCore;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use tokio::{sync::Mutex, time::Instant};

const MAX_START_ATTEMPTS: usize = 3;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(10);
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(100);
pub const DEFAULT_SHORTCUT: &str = "Cmd+Alt+KeyT";

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

#[derive(Debug)]
pub(crate) enum BackendError {
    PortBinding(String),
    Sidecar(String),
    HealthCheck(String),
    NotRunning,
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
    generation: u64,
    shutting_down: bool,
}

pub struct BackendSupervisor {
    database_path: PathBuf,
    client: reqwest::Client,
    operation: Mutex<()>,
    inner: Mutex<SupervisorInner>,
}

impl BackendSupervisor {
    pub fn new(database_path: PathBuf) -> Self {
        Self {
            database_path,
            client: reqwest::Client::new(),
            operation: Mutex::new(()),
            inner: Mutex::new(SupervisorInner::default()),
        }
    }

    pub(crate) async fn ensure_running(
        &self,
        app: &AppHandle,
    ) -> Result<BackendConnection, BackendError> {
        if let Some(connection) = self.running_connection().await {
            return Ok(connection);
        }

        let _operation = self.operation.lock().await;
        if let Some(connection) = self.running_connection().await {
            return Ok(connection);
        }
        self.start(app).await
    }

    async fn restart(&self, app: &AppHandle) -> Result<BackendConnection, BackendError> {
        let _operation = self.operation.lock().await;
        {
            let mut inner = self.inner.lock().await;
            if inner.shutting_down {
                return Err(BackendError::NotRunning);
            }
            stop_child(&mut inner);
        }
        self.start(app).await
    }

    async fn running_connection(&self) -> Option<BackendConnection> {
        let inner = self.inner.lock().await;
        (inner.lifecycle.phase() == BackendPhase::Running)
            .then(|| inner.connection.clone())
            .flatten()
    }

    async fn start(&self, app: &AppHandle) -> Result<BackendConnection, BackendError> {
        {
            let mut inner = self.inner.lock().await;
            if inner.shutting_down {
                return Err(BackendError::NotRunning);
            }
            inner.lifecycle.begin_restart();
        }
        let mut last_error = None;

        for _ in 0..MAX_START_ATTEMPTS {
            if self.inner.lock().await.shutting_down {
                return Err(BackendError::NotRunning);
            }
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
            .env("TODO_BACKEND_TOKEN", &connection.token);
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
                inner.generation
            };
            monitor_sidecar(app.clone(), receiver, generation);

            match self.wait_for_health(&connection).await {
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

    async fn wait_for_health(&self, connection: &BackendConnection) -> Result<(), BackendError> {
        let deadline = Instant::now() + STARTUP_TIMEOUT;
        let health_url = format!("{}/api/v1/health", connection.base_url);
        loop {
            let detail = match self
                .client
                .get(&health_url)
                .bearer_auth(&connection.token)
                .timeout(Duration::from_secs(1))
                .send()
                .await
            {
                Ok(response) if response.status().is_success() => {
                    match response.json::<HealthResponse>().await {
                        Ok(health) if health.status == "ok" => return Ok(()),
                        Ok(_) => "unexpected health payload".to_owned(),
                        Err(error) => error.to_string(),
                    }
                }
                Ok(response) => {
                    format!("HTTP {}", response.status().as_u16())
                }
                Err(error) => error.to_string(),
            };

            if Instant::now() >= deadline {
                return Err(BackendError::HealthCheck(detail));
            }
            tokio::time::sleep(HEALTH_POLL_INTERVAL).await;
        }
    }

    async fn mark_unexpected_exit(&self, app: &AppHandle, generation: u64) {
        let should_emit = {
            let mut inner = self.inner.lock().await;
            if inner.generation != generation {
                false
            } else {
                let was_running = inner.lifecycle.phase() == BackendPhase::Running;
                inner.generation = inner.generation.wrapping_add(1);
                inner.child = None;
                inner.connection = None;
                inner.lifecycle.mark_stopped();
                was_running
            }
        };

        if should_emit {
            let _ = app.emit("backend-unavailable", ());
        }
    }

    pub async fn shutdown(&self) {
        let mut inner = self.inner.lock().await;
        inner.shutting_down = true;
        stop_child(&mut inner);
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
}

#[derive(Deserialize)]
struct HealthResponse {
    status: String,
}

fn stop_child(inner: &mut SupervisorInner) {
    inner.generation = inner.generation.wrapping_add(1);
    if let Some(child) = inner.child.take() {
        let _ = child.kill();
    }
    inner.connection = None;
    inner.lifecycle.mark_stopped();
}

fn monitor_sidecar(
    app: AppHandle,
    mut receiver: tauri::async_runtime::Receiver<CommandEvent>,
    generation: u64,
) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            if matches!(event, CommandEvent::Terminated(_)) {
                let supervisor = app.state::<BackendSupervisor>();
                supervisor.mark_unexpected_exit(&app, generation).await;
                break;
            }
        }
    });
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
    current: Mutex<String>,
}

impl ShortcutRegistration {
    pub fn new(shortcut: impl Into<String>) -> Self {
        Self {
            current: Mutex::new(shortcut.into()),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ShortcutStep<'a> {
    Register(&'a str),
    Unregister(&'a str),
}

struct ShortcutTransaction<'a> {
    previous: &'a str,
    next: &'a str,
}

impl<'a> ShortcutTransaction<'a> {
    fn new(previous: &'a str, next: &'a str) -> Self {
        Self { previous, next }
    }

    fn apply_steps(&self) -> [ShortcutStep<'a>; 2] {
        [
            ShortcutStep::Register(self.next),
            ShortcutStep::Unregister(self.previous),
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
        ShortcutStep::Register(_) => unreachable!(),
    };
    let restore_result = match steps[1] {
        ShortcutStep::Register(shortcut) => manager.register(shortcut),
        ShortcutStep::Unregister(_) => unreachable!(),
    };
    if remove_result.is_err() || restore_result.is_err() {
        return Err("SHORTCUT_ROLLBACK_FAILED".to_owned());
    }
    Ok(())
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
    let mut previous = registration.current.lock().await;
    if *previous == shortcut {
        return supervisor
            .persist_shortcut(&shortcut)
            .await
            .map_err(|error| error.public_message().to_owned());
    }

    let transaction = ShortcutTransaction::new(&previous, &shortcut);
    let apply_steps = transaction.apply_steps();
    app.global_shortcut()
        .register(match apply_steps[0] {
            ShortcutStep::Register(value) => value,
            ShortcutStep::Unregister(_) => unreachable!(),
        })
        .map_err(|error| error.to_string())?;
    if let Err(error) = app.global_shortcut().unregister(previous.as_str()) {
        let _ = app.global_shortcut().unregister(shortcut.as_str());
        return Err(error.to_string());
    }

    if let Err(error) = supervisor.persist_shortcut(&shortcut).await {
        rollback_shortcut(&app, &transaction)?;
        return Err(error.public_message().to_owned());
    }

    *previous = shortcut;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

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
    fn shortcut_transaction_registers_next_first_and_restores_previous_on_rollback() {
        let transaction = ShortcutTransaction::new("Cmd+Alt+KeyT", "Cmd+Shift+KeyN");

        assert_eq!(
            transaction.apply_steps(),
            [
                ShortcutStep::Register("Cmd+Shift+KeyN"),
                ShortcutStep::Unregister("Cmd+Alt+KeyT")
            ]
        );
        assert_eq!(
            transaction.rollback_steps(),
            [
                ShortcutStep::Unregister("Cmd+Shift+KeyN"),
                ShortcutStep::Register("Cmd+Alt+KeyT")
            ]
        );
    }
}
