fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "health",
            "list_libraries",
            "list_components",
            "get_component",
            "restart_engine",
        ]),
    ))
    .expect("Tauri build configuration");
}
