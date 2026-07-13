mod backend;

use backend::{
    get_backend_connection, initialize_shortcut, retry_backend, set_global_shortcut,
    BackendSupervisor, ShortcutRegistration,
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, WindowEvent,
};
use tauri_plugin_global_shortcut::ShortcutState;

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn toggle_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        match window.is_visible() {
            Ok(true) => {
                let _ = window.hide();
            }
            _ => {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }
    }
}

#[tauri::command]
fn quick_add(app: AppHandle) {
    show_main_window(&app);
    let _ = app.emit("open-create-modal", ());
}

#[tauri::command]
fn show_window(app: AppHandle) {
    show_main_window(&app);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    // Any registered global shortcut press → show window + open quick add.
                    // We register only one shortcut at a time (default Alt+Space; user can override).
                    if event.state() == ShortcutState::Pressed {
                        show_main_window(app);
                        let _ = app.emit("open-create-modal", ());
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            quick_add,
            show_window,
            get_backend_connection,
            retry_backend,
            set_global_shortcut
        ])
        .setup(move |app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let app_data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&app_data_dir)?;
            app.manage(BackendSupervisor::new(app_data_dir.join("todo.sqlite3")));
            app.manage(ShortcutRegistration::new());
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if initialize_shortcut(&app_handle).await.is_err() {
                    log::error!("backend initialization failed");
                }
            });

            // Build tray menu.
            let show_item = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
            let new_task_item = MenuItem::with_id(app, "new-task", "新建任务", true, None::<&str>)?;
            let separator = tauri::menu::PredefinedMenuItem::separator(app)?;
            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu =
                Menu::with_items(app, &[&show_item, &new_task_item, &separator, &quit_item])?;

            let _tray = TrayIconBuilder::with_id("main-tray")
                .icon(app.default_window_icon().unwrap().clone())
                .icon_as_template(true)
                .tooltip("Todo List")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_main_window(app),
                    "new-task" => {
                        show_main_window(app);
                        let _ = app.emit("open-create-modal", ());
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Intercept main-window close → hide instead of exit.
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
                tauri::async_runtime::block_on(app.state::<BackendSupervisor>().shutdown());
            }
        });
}
