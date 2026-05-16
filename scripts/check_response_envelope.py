"""掃描 app/routers/ 內所有 @router.<method> decorator。

檢查每個路由函式是否標註 response_model=ResponseEnvelope[...]。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROUTERS_DIR = Path(__file__).resolve().parent.parent / "backend" / "app" / "routers"


def _is_response_envelope(node: ast.expr) -> bool:
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        return node.value.id == "ResponseEnvelope"
    return False


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
                continue
            if deco.func.attr not in {"get", "post", "put", "delete", "patch"}:
                continue
            kw = {k.arg: k.value for k in deco.keywords}
            rm = kw.get("response_model")
            if rm is None:
                errors.append(f"{path}::{node.name} 缺少 response_model")
                continue
            if not _is_response_envelope(rm):
                errors.append(f"{path}::{node.name} response_model 不是 ResponseEnvelope[...]")
    return errors


def main() -> int:
    all_errors: list[str] = []
    for py in ROUTERS_DIR.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        all_errors.extend(check_file(py))
    if all_errors:
        print("\n".join(all_errors), file=sys.stderr)
        return 1
    print(f"OK: 所有 router 端點皆使用 ResponseEnvelope（已掃描 {ROUTERS_DIR}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
