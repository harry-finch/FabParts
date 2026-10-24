"""PyInstaller entry point; the composition has no Qt imports."""

from kipartmanager.headless import main

raise SystemExit(main())
