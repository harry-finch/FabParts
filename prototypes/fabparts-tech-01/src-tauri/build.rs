fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "health",
            "list_libraries",
            "list_components",
            "get_component",
            "restart_engine",
            "get_asset_preview",
            "read_pdf_chunk",
            "release_preview",
        ]),
    ))
    .expect("Tauri build configuration");
}
