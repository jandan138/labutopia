import ast
from pathlib import Path

import pytest


CONTROLLERS = Path(__file__).resolve().parents[1] / "controllers"


@pytest.mark.parametrize(
    "filename",
    [
        "base_controller.py",
        "open_controller.py",
        "pick_controller.py",
        "close_controller.py",
        "openclose_controller.py",
    ],
)
def test_inference_factory_is_imported_only_inside_infer_mode(filename):
    tree = ast.parse((CONTROLLERS / filename).read_text(encoding="utf-8"))
    top_level_imports = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any(
        module.endswith("inference_engines.inference_engine_factory")
        for module in top_level_imports
    )

    infer_method = next(
        member
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        for member in node.body
        if isinstance(member, ast.FunctionDef)
        and member.name == "_init_infer_mode"
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module.endswith("inference_engines.inference_engine_factory")
        for node in infer_method.body
    )


def test_base_controller_close_releases_the_inference_engine():
    tree = ast.parse(
        (CONTROLLERS / "base_controller.py").read_text(encoding="utf-8")
    )
    close_method = next(
        member
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BaseController"
        for member in node.body
        if isinstance(member, ast.FunctionDef) and member.name == "close"
    )

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "close"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "inference_engine"
        for node in ast.walk(close_method)
    )
