"""Application identity resources, separate from the electronic Asset Store."""

from pathlib import Path

from PySide6.QtGui import QIcon

PRODUCT_NAME = "FabParts"
PRODUCT_SUBTITLE = "Electronic component manager"

BRANDING_ROOT = Path(__file__).parent / "branding"


def application_icon() -> QIcon:
    """Resolve the scalable approved icon independently of the working directory."""
    return QIcon(str(BRANDING_ROOT / "source" / "app_icon.svg"))
