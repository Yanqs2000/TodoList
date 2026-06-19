use tauri::{
  menu::{Menu, MenuItem},
  tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
  AppHandle, Emitter, Manager, WindowEvent,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

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

/// Replace the global shortcut at runtime. The shortcut string follows Tauri's
/// accelerator format (e.g. "Alt+Space", "CmdOrCtrl+Shift+N"). On parse failure
/// or registration error returns Err with a human-readable message.
#[tauri::command]
fn set_global_shortcut(app: AppHandle, shortcut: String) -> Result<(), String> {
  let manager = app.global_shortcut();
  let _ = manager.unregister_all();
  let parsed: Shortcut = shortcut.parse().map_err(|e| format!("invalid shortcut: {e}"))?;
  manager.register(parsed).map_err(|e| e.to_string())?;
  Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let default_shortcut: Shortcut = Shortcut::new(Some(Modifiers::ALT), Code::Space);

  tauri::Builder::default()
    .plugin(tauri_plugin_notification::init())
    .plugin(
      tauri_plugin_autostart::init(
        tauri_plugin_autostart::MacosLauncher::LaunchAgent,
        None,
      ),
    )
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
    .invoke_handler(tauri::generate_handler![quick_add, show_window, set_global_shortcut])
    .setup(move |app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // Register the default global shortcut at startup.
      let _ = app.global_shortcut().register(default_shortcut.clone());

      // Build tray menu.
      let show_item = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
      let new_task_item = MenuItem::with_id(app, "new-task", "新建任务", true, None::<&str>)?;
      let separator = tauri::menu::PredefinedMenuItem::separator(app)?;
      let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
      let menu = Menu::with_items(app, &[&show_item, &new_task_item, &separator, &quit_item])?;

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
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
