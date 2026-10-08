// SPDX-License-Identifier: AGPL-3.0-or-later
//! Hudhud for desktop. Starts the hub (a bundled `hudhud.exe`), then shows the reader
//! the hub serves in a window that pairs itself. Closing the window keeps the hub
//! running in the tray, so phones can still sync; Quit stops both.

use std::net::{SocketAddr, TcpStream};
use std::sync::Mutex;
use std::thread::sleep;
use std::time::Duration;

use tauri::menu::{CheckMenuItem, Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, Url, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const DEFAULT_PORT: u16 = 8765;
const MINIMIZED_FLAG: &str = "--minimized";

/// The hub's port. HUDHUD_DESKTOP_PORT overrides it (tests run beside a real hub).
fn port() -> u16 {
    std::env::var("HUDHUD_DESKTOP_PORT").ok().and_then(|p| p.parse().ok()).unwrap_or(DEFAULT_PORT)
}

/// The hub process this app started (none if a hub was already running).
struct Hub(Mutex<Option<CommandChild>>);

fn hub_is_up() -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port()));
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

fn local_url(path: &str) -> Url {
    Url::parse(&format!("http://127.0.0.1:{}{path}", port())).expect("valid local URL")
}

fn show(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// Wait (off the main thread) until the hub answers, then point the window at it.
fn open_when_ready(app: AppHandle, url: Url) {
    std::thread::spawn(move || {
        for _ in 0..240 {
            if hub_is_up() {
                break;
            }
            sleep(Duration::from_millis(250));
        }
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.navigate(url);
        }
    });
}

fn stop_hub(app: &AppHandle) {
    let child = app.state::<Hub>().0.lock().ok().and_then(|mut slot| slot.take());
    if let Some(child) = child {
        // The packaged hub runs as a launcher plus a child process; stop the whole tree.
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            let _ = std::process::Command::new("taskkill")
                .args(["/PID", &child.pid().to_string(), "/T", "/F"])
                .creation_flags(CREATE_NO_WINDOW)
                .status();
        }
        let _ = child.kill();
    }
}

/// The first line of the form `HUDHUD_URL <url>` in a sidecar's output.
fn announced_url(output: &str) -> Option<Url> {
    output
        .lines()
        .find_map(|line| line.trim().strip_prefix("HUDHUD_URL "))
        .and_then(|url| Url::parse(url).ok())
}

fn start_hub(app: &AppHandle) -> tauri::Result<()> {
    let port = port().to_string();
    if hub_is_up() {
        // A hub is already serving (one started by hand): use it, and still let this
        // window pair itself with a fresh code from the same data folder.
        let handle = app.clone();
        let pair = app
            .shell()
            .sidecar("hudhud")
            .map_err(|e| tauri::Error::Anyhow(e.into()))?
            .args(["pair", "--announce", "--port", &port]);
        tauri::async_runtime::spawn(async move {
            let url = match pair.output().await {
                Ok(out) => announced_url(&String::from_utf8_lossy(&out.stdout)),
                Err(_) => None,
            };
            open_when_ready(handle, url.unwrap_or_else(|| local_url("/")));
        });
        return Ok(());
    }
    let (mut events, child) = app
        .shell()
        .sidecar("hudhud")
        .map_err(|e| tauri::Error::Anyhow(e.into()))?
        .args(["serve", "--announce", "--no-browser", "--port", &port])
        .spawn()
        .map_err(|e| tauri::Error::Anyhow(e.into()))?;
    if let Ok(mut slot) = app.state::<Hub>().0.lock() {
        slot.replace(child);
    }
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut opened = false;
        while let Some(event) = events.recv().await {
            if let CommandEvent::Stdout(line) = event {
                if let (false, Some(url)) = (opened, announced_url(&String::from_utf8_lossy(&line))) {
                    opened = true;
                    open_when_ready(handle.clone(), url);
                }
            }
        }
    });
    Ok(())
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open Hudhud", true, None::<&str>)?;
    let add = MenuItem::with_id(app, "add", "Add a device…", true, None::<&str>)?;
    let autostart_on = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart =
        CheckMenuItem::with_id(app, "autostart", "Start with Windows", true, autostart_on, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Hudhud", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &add, &autostart, &quit])?;
    let icon = app.default_window_icon().cloned().expect("bundled icon");
    TrayIconBuilder::with_id("hudhud")
        .icon(icon)
        .tooltip("Hudhud")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => show(app),
            "add" => {
                show(app);
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.navigate(local_url("/settings"));
                }
            }
            "autostart" => {
                let launcher = app.autolaunch();
                let _ = if launcher.is_enabled().unwrap_or(false) {
                    launcher.disable()
                } else {
                    launcher.enable()
                };
            }
            "quit" => {
                stop_hub(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

pub fn run() {
    let app = tauri::Builder::default()
        // A second launch just brings the running window forward.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show(app)))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec![MINIMIZED_FLAG]),
        ))
        .manage(Hub(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            build_tray(&handle)?;
            start_hub(&handle)?;
            if std::env::args().any(|arg| arg == MINIMIZED_FLAG) {
                if let Some(window) = handle.get_webview_window("main") {
                    let _ = window.hide();
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the window keeps Hudhud in the tray so phones can still sync.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("failed to build Hudhud");
    app.run(|app, event| {
        if let RunEvent::Exit = event {
            stop_hub(app);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::announced_url;

    #[test]
    fn finds_the_announced_url_among_log_lines() {
        let out = "Wrote settings template
HUDHUD_URL http://127.0.0.1:8765/?pair=ABCD1234
INFO started";
        assert_eq!(
            announced_url(out).map(|u| u.to_string()),
            Some("http://127.0.0.1:8765/?pair=ABCD1234".to_string())
        );
        assert_eq!(announced_url("nothing here"), None);
    }
}
