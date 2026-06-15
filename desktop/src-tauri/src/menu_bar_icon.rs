//! macOS 顶部菜单栏状态图标（NSStatusItem），与 Dock 程序坞图标无关。

use objc2_app_kit::NSImage;
use objc2_foundation::{MainThreadMarker, NSSize, NSString};
use tauri::tray::TrayIcon;

const MENU_BAR_SYMBOL: &str = "star.fill";

pub fn apply_menu_bar_icon(tray: &TrayIcon) -> Result<(), String> {
    tray.with_inner_tray_icon(|inner| {
        let mtm =
            MainThreadMarker::new().ok_or_else(|| "menu bar icon must run on main thread".to_string())?;
        let status_item = inner
            .ns_status_item()
            .ok_or_else(|| "menu bar status item missing".to_string())?;
        let symbol = NSString::from_str(MENU_BAR_SYMBOL);
        let description = NSString::from_str("AgentPod");
        let image = NSImage::imageWithSystemSymbolName_accessibilityDescription(&symbol, Some(&description))
            .ok_or_else(|| format!("SF Symbol not found: {MENU_BAR_SYMBOL}"))?;
        image.setTemplate(true);
        image.setSize(NSSize::new(16.0, 16.0));
        let button = status_item
            .button(mtm)
            .ok_or_else(|| "menu bar status button missing".to_string())?;
        button.setImage(Some(&image));
        Ok(())
    })
    .map_err(|err| err.to_string())?
}
