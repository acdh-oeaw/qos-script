#!/usr/bin/env python3
import ast
import importlib
import inspect
import os
import pkgutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import checks

CHECK_DIR = REPO_ROOT / "checks"
HTTP_CLIENT_PATH = REPO_ROOT / "utils" / "http_client.py"
EXPECTED_ASYNC = "check_imprint_page"
FORBIDDEN_PATTERNS = ["requests.get(", "aiohttp.ClientSession("]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def assert_checks_signature() -> None:
    for finder, name, ispkg in pkgutil.iter_modules([str(CHECK_DIR)]):
        module_name = f"checks.{name}"
        module = importlib.import_module(module_name)

        for fn_name, fn in inspect.getmembers(module, inspect.isfunction):
            if not fn_name.startswith("check_"):
                continue

            params = list(inspect.signature(fn).parameters.values())
            param_names = [p.name for p in params if p.name != "self"]

            if "html" not in param_names:
                fail(f"{module_name}.{fn_name} must accept an 'html' parameter")

            if fn_name == EXPECTED_ASYNC:
                if not inspect.iscoroutinefunction(fn):
                    fail(f"{module_name}.{fn_name} must be async")
            else:
                if inspect.iscoroutinefunction(fn):
                    fail(f"{module_name}.{fn_name} must be synchronous")

            if fn_name == EXPECTED_ASYNC:
                if "http_client" not in param_names:
                    fail(f"{module_name}.{fn_name} must accept an 'http_client' parameter")

    print("OK: check function signatures are correct")


def assert_no_forbidden_http_calls() -> None:
    for path in CHECK_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                fail(f"Forbidden pattern '{pattern}' found in {path.relative_to(REPO_ROOT)}")
    print("OK: no forbidden HTTP call patterns in checks")


def assert_http_client_signature() -> None:
    source = HTTP_CLIENT_PATH.read_text(encoding="utf-8")
    parsed = ast.parse(source, filename=str(HTTP_CLIENT_PATH))

    for node in parsed.body:
        if isinstance(node, ast.ClassDef) and node.name == "ResilientHttpClient":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "get":
                    arg_names = [arg.arg for arg in item.args.args]
                    if len(arg_names) < 2 or arg_names[0] != "self" or arg_names[1] != "url":
                        fail("ResilientHttpClient.get() must accept 'self, url' as the first parameters")
                    print("OK: ResilientHttpClient.get() signature is correct")
                    return
    fail("ResilientHttpClient.get() method not found in utils/http_client.py")


def main() -> None:
    print("Running self-check...")
    assert_checks_signature()
    assert_no_forbidden_http_calls()
    assert_http_client_signature()
    print("All self-checks passed")


if __name__ == "__main__":
    main()
