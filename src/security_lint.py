#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
USES_RE = re.compile(r"^\s*uses:\s*([^@\s]+)@([^\s#]+)")
FORBIDDEN_JS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write(",
    "eval(",
    "new Function(",
    "javascript:",
)
FORBIDDEN_HTML = (
    "<script>",
    "javascript:",
    "onerror=",
    "onclick=",
    "onload=",
)


class PythonSecurityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr

        if name in {"eval", "exec", "compile"}:
            self.findings.append(f"dangerous dynamic execution: {name} at line {node.lineno}")

        if name in {"Popen", "run", "call", "check_call", "check_output"}:
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    self.findings.append(f"subprocess shell=True at line {node.lineno}")

        self.generic_visit(node)


def lint_python() -> list[str]:
    findings: list[str] = []
    for path in sorted((ROOT / "src").glob("*.py")):
        visitor = PythonSecurityVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        findings.extend(f"{path.relative_to(ROOT)}: {item}" for item in visitor.findings)
    return findings


def lint_javascript() -> list[str]:
    findings: list[str] = []
    for path in sorted((ROOT / "public").rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_JS:
            if token in text:
                findings.append(f"{path.relative_to(ROOT)}: forbidden JS sink/token {token!r}")
    return findings


def lint_html() -> list[str]:
    findings: list[str] = []
    for path in sorted((ROOT / "public").rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for token in FORBIDDEN_HTML:
            if token.lower() in lowered:
                findings.append(f"{path.relative_to(ROOT)}: forbidden HTML token {token!r}")
        if "Content-Security-Policy" not in text:
            findings.append(f"{path.relative_to(ROOT)}: missing Content Security Policy")
        if '<meta name="referrer" content="no-referrer">' not in text:
            findings.append(f"{path.relative_to(ROOT)}: missing no-referrer policy")
    return findings


def lint_actions() -> list[str]:
    findings: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            match = USES_RE.match(line)
            if not match:
                continue
            action, ref = match.groups()
            if action.startswith("./"):
                continue
            if not FULL_SHA.fullmatch(ref):
                findings.append(
                    f"{path.relative_to(ROOT)}:{line_number}: Action {action} is not pinned to a full SHA"
                )

        if re.search(r"permissions:\s*\n\s*contents:\s*write", text):
            # Write permission is allowed only at job level for the explicit publish job.
            prefix = text.split("jobs:", 1)[0]
            if re.search(r"permissions:\s*\n\s*contents:\s*write", prefix):
                findings.append(f"{path.relative_to(ROOT)}: workflow-level contents:write is forbidden")

        if "pull_request_target:" in text:
            findings.append(f"{path.relative_to(ROOT)}: pull_request_target is forbidden by policy")

    return findings


def main() -> None:
    findings = lint_python() + lint_javascript() + lint_html() + lint_actions()
    if findings:
        print("Security policy violations:", file=sys.stderr)
        for finding in findings:
            print(f" - {finding}", file=sys.stderr)
        raise SystemExit(1)
    print("[ok] static security policy checks passed")


if __name__ == "__main__":
    main()
