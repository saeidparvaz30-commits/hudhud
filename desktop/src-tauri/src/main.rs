// SPDX-License-Identifier: AGPL-3.0-or-later
// No console window behind the app in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    hudhud_desktop_lib::run()
}
