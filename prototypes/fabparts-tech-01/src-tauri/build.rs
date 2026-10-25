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
            "get_model_status",
            "read_mesh_chunk",
            "release_model_preview",
            "ingestion_command",
            "choose_ingestion_files",
        ]),
    ))
    .expect("Tauri build configuration");
}
