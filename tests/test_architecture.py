"""Guard the initial layer boundaries without a dependency-analysis framework."""

import ast
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src" / "kipartmanager"
ALLOWED_LAYERS = {
    "domain": set(),
    "ports": {"domain"},
    "application": {"domain", "ports"},
    "infrastructure": {"domain", "ports"},
    "ui": {"domain", "application"},
}


@pytest.mark.parametrize("layer", ALLOWED_LAYERS)
def test_layer_import_boundaries(layer: str) -> None:
    for path in (SOURCE / layer).rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = path.relative_to(SOURCE.parent).parts[:-1]
                    base = package[: len(package) - node.level + 1]
                    module = ".".join((*base, *((node.module or "").split("."))))
                else:
                    module = node.module or ""
                modules = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            for module in modules:
                parts = module.strip(".").split(".")
                if parts[0] == "kipartmanager" and len(parts) > 1:
                    target = parts[1]
                    assert target in {layer, *ALLOWED_LAYERS[layer], "__version__"}, (
                        path,
                        module,
                    )
                elif parts[0] != "kipartmanager" and layer in {"domain", "ports", "application"}:
                    assert parts[0] in sys.stdlib_module_names, (path, module)
