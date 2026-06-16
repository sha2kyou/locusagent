//! macOS 顶部菜单栏状态项（设置页「菜单栏与后台」里的菜单栏图标）。

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle,
};

use crate::desktop_prefs::{hide_main_window, show_main_window};

#[cfg(target_os = "macos")]
use crate::menu_bar_icon;

const MENU_SHOW: &str = "tray_show";
const MENU_HIDE: &str = "tray_hide";
const MENU_QUIT: &str = "tray_quit";

pub fn setup_tray(app: &AppHandle) -> Result<(), String> {
    let show = MenuItem::with_id(app, MENU_SHOW, "打开 AgentPod", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let hide = MenuItem::with_id(app, MENU_HIDE, "隐藏窗口", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let quit = MenuItem::with_id(app, MENU_QUIT, "退出 AgentPod", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let menu = Menu::with_items(app, &[&show, &hide, &quit]).map_err(|e| e.to_string())?;

    let mut builder = TrayIconBuilder::new()
        .menu(&menu)
        .tooltip("AgentPod")
        .show_menu_on_left_click(false);

    // 非 macOS 仍用应用图标；macOS 菜单栏图标单独用 SF Symbol（见 menu_bar_icon.rs）。
    #[cfg(not(target_os = "macos"))]
    {
        let icon = app
            .default_window_icon()
            .cloned()
            .ok_or_else(|| "application icon missing".to_string())?;
        builder = builder.icon(icon);
    }

    let app_menu = app.clone();
    let _tray = builder
        .on_menu_event(move |_tray, event| match event.id().as_ref() {
            MENU_SHOW => show_main_window(&app_menu),
            MENU_HIDE => hide_main_window(&app_menu),
            MENU_QUIT => app_menu.exit(0),
            _ => {}
        })
        .on_tray_icon_event(move |tray, event| {
            if let TrayIconEvent::Click {
                button,
                button_state,
                ..
            } = event
            {
                if button == MouseButton::Left && button_state == MouseButtonState::Up {
                    show_main_window(tray.app_handle());
                }
            }
        })
        .build(app)
        .map_err(|e| e.to_string())?;

    #[cfg(target_os = "macos")]
    menu_bar_icon::apply_menu_bar_icon(&_tray)?;

    Ok(())
}
