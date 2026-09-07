"""Reproduce source-size and inclusive AST branch proxies (not formal CC).

The proxy starts at one and counts if/for/while/if-expressions, except handlers,
comprehension generators, and each extra Boolean operand, including nested
functions. Physical line spans include comments and blank lines. These simple
metrics locate investigation targets; they do not establish maintainability.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path


def inventory(root: Path, revision: str | None = None) -> dict:
    if revision:
        names = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", revision, "src/paranoia_local"],
            cwd=root, text=True,
        ).splitlines()
        sources = {
            name: subprocess.check_output(
                ["git", "show", f"{revision}:{name}"], cwd=root,
            ).decode("utf-8")
            for name in names if name.endswith(".py")
        }
    else:
        sources = {
            str(path.relative_to(root)): path.read_text(encoding="utf-8")
            for path in sorted((root / "src/paranoia_local").rglob("*.py"))
        }
    modules, functions = [], []
    for name, source in sources.items():
        modules.append({"path": name, "lines": len(source.splitlines()),
                        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()})
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            branches = sum(
                isinstance(child, (
                    ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp,
                    ast.ExceptHandler, ast.comprehension,
                ))
                for child in ast.walk(node)
            )
            branches += sum(
                len(child.values) - 1 for child in ast.walk(node)
                if isinstance(child, ast.BoolOp)
            )
            functions.append({
                "path": name, "name": node.name, "line": node.lineno,
                "lines": node.end_lineno - node.lineno + 1,
                "inclusive_branch_proxy": branches + 1,
            })
    return {
        "metric": "inclusive-python-ast-branch-proxy-v1",
        "revision": revision or "working-tree",
        "modules": sorted(modules, key=lambda row: (-row["lines"], row["path"])),
        "functions": sorted(functions, key=lambda row: (
            -row["inclusive_branch_proxy"], row["path"], row["line"],
        )),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inventory(Path(__file__).resolve().parents[1], args.revision)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
