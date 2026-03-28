#!/usr/bin/env python3
"""
validate.py — Language-agnostic static validator for web projects.

Reads project layout and tool configuration from env.py in the same directory.
Supports Python, JavaScript, CSS, and HTML out of the box.

Usage (run from any directory):
    python tools/validate.py               # all checks
    python tools/validate.py --exec        # + Python dry-run execution
    python tools/validate.py --python      # Python only
    python tools/validate.py --js          # JS only
    python tools/validate.py --css         # CSS only
    python tools/validate.py --html        # HTML only
    python tools/validate.py --no-lint     # skip ESLint / html-validate / stylelint
    python tools/validate.py --report      # save HTML report (path from env.py)
    python tools/validate.py --json        # machine-readable JSON output
    python tools/validate.py src/app.py    # single file
"""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Load env.py (project-specific configuration) ──────────────────────────────
TOOLS_DIR = Path(__file__).parent.resolve()

_cfg = None
_env_path = TOOLS_DIR / 'env.py'
if _env_path.exists():
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('_validate_env', str(_env_path))
    _cfg = _ilu.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(_cfg)
    except Exception as _e:
        print(f"[validate] Warning: could not load env.py: {_e}", file=sys.stderr)
        _cfg = None


def _cfg_get(attr: str, default=None):
    if _cfg is not None and hasattr(_cfg, attr):
        return getattr(_cfg, attr)
    return default


# ── Resolve project root and file lists from config ───────────────────────────
ROOT: Path = _cfg_get('ROOT', TOOLS_DIR.parent)
PROJECT_NAME: str = _cfg_get('PROJECT_NAME', ROOT.name)

_COMMON_EXCLUDE = ['__pycache__', '.venv', 'venv', 'node_modules', '.git', 'dist', 'build']


def _collect(dirs_key: str, extra_key: str, excl_key: str, pattern: str) -> list[Path]:
    """Glob pattern inside each configured directory, honouring exclude list."""
    dirs    = [ROOT / d for d in _cfg_get(dirs_key,  [])]
    extra   = [ROOT / f for f in _cfg_get(extra_key, [])]
    exclude = set(_cfg_get(excl_key, _COMMON_EXCLUDE))
    files: list[Path] = []
    seen: set[Path] = set()
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.rglob(pattern)):
            if any(part in exclude for part in f.parts) or f in seen:
                continue
            files.append(f); seen.add(f)
    for f in extra:
        if f.exists() and f not in seen:
            files.append(f); seen.add(f)
    return files


def _explicit_html() -> list[Path]:
    listed = [ROOT / f for f in _cfg_get('HTML_FILES', [])]
    from_dirs = _collect('HTML_DIRS', 'HTML_EXTRA', 'HTML_EXCLUDE_DIRS', '*.html')
    seen: set[Path] = set()
    result: list[Path] = []
    for f in listed + from_dirs:
        if f not in seen:
            result.append(f); seen.add(f)
    return result


PYTHON_FILES = _collect('PYTHON_DIRS', 'PYTHON_EXTRA', 'PYTHON_EXCLUDE_DIRS', '*.py')
JS_FILES     = _collect('JS_DIRS',     'JS_EXTRA',     'JS_EXCLUDE_DIRS',     '*.js')
CSS_FILES    = _collect('CSS_DIRS',    'CSS_EXTRA',    'CSS_EXCLUDE_DIRS',    '*.css')
HTML_FILES   = _explicit_html()


def _tool_config(key: str, default: str) -> Path:
    val = _cfg_get(key, default)
    p = Path(val)
    return p if p.is_absolute() else TOOLS_DIR / val


ESLINT_CONFIG       = _tool_config('ESLINT_CONFIG',       'eslint.config.mjs')
HTMLVALIDATE_CONFIG = _tool_config('HTMLVALIDATE_CONFIG',  '.htmlvalidate.json')
STYLELINT_CONFIG    = _tool_config('STYLELINT_CONFIG',     '.stylelintrc.json')

REPORT_FILE:   str | None = _cfg_get('REPORT_FILE',   None)
REPORT_FORMAT: str        = _cfg_get('REPORT_FORMAT', 'html')

# ── Severity constants ─────────────────────────────────────────────────────────
ERROR = 'ERROR'
WARN  = 'WARN'
INFO  = 'INFO'

# ── ANSI colours ──────────────────────────────────────────────────────────────
_USE_COLOUR = sys.stdout.isatty() and sys.platform != 'win32'
C = {k: (v if _USE_COLOUR else '') for k, v in {
    'red': '\033[31m', 'yellow': '\033[33m', 'green': '\033[32m',
    'cyan': '\033[36m', 'bold': '\033[1m', 'dim': '\033[2m', 'reset': '\033[0m',
}.items()}


# ── Issue data class ───────────────────────────────────────────────────────────

class Issue:
    __slots__ = ('severity', 'path', 'line', 'col', 'message', 'check')

    def __init__(self, severity: str, path, line, col, message: str, check: str):
        self.severity = severity
        self.path     = str(path)
        self.line     = line
        self.col      = col
        self.message  = message
        self.check    = check

    def as_dict(self) -> dict:
        return dict(severity=self.severity, path=self.path, line=self.line,
                    col=self.col, message=self.message, check=self.check)


# ── Python: syntax (py_compile) ───────────────────────────────────────────────

def check_python_syntax(path: Path) -> list[Issue]:
    issues: list[Issue] = []
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as e:
            issues.append(Issue(ERROR, path, None, None, str(e), 'syntax'))
    for w in caught:
        if issubclass(w.category, SyntaxWarning):
            issues.append(Issue(WARN, path, getattr(w, 'lineno', None),
                                None, f"SyntaxWarning: {w.message}", 'syntax'))
    return issues


# ── Python: imports / names (pyflakes) ────────────────────────────────────────

def _has_pyflakes() -> bool:
    try:
        import pyflakes  # noqa: F401
        return True
    except ImportError:
        return False


def check_python_imports(path: Path) -> list[Issue]:
    issues: list[Issue] = []
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pyflakes', str(path)],
            capture_output=True, text=True
        )
        for line in (result.stdout + result.stderr).splitlines():
            m = re.match(r'^(.+?):(\d+)(?::(\d+))?: (.+)$', line.strip())
            if not m:
                continue
            _, lineno, col, msg = m.groups()
            if any(k in msg for k in ('undefined name', 'redefinition', 'SyntaxError')):
                sev = ERROR
            elif any(k in msg for k in ('imported but unused', 'local variable', 'is unused',
                                        'f-string is missing', 'redefinition of unused')):
                sev = WARN
            else:
                sev = INFO
            issues.append(Issue(sev, path, int(lineno),
                                int(col) if col else None, msg, 'imports'))
    except Exception as e:
        issues.append(Issue(WARN, path, None, None, f"pyflakes failed: {e}", 'imports'))
    return issues


# ── Python: dry-run execution (importlib + --help) ────────────────────────────

def check_python_exec(path: Path) -> list[Issue]:
    """
    Safe two-phase dry-run:
      1. Module load via importlib — catches missing packages, NameError, etc.
      2. subprocess --help         — exercises argparse + unconditional main code.
    Neither phase starts servers, makes network calls, or modifies data.
    """
    issues: list[Issue] = []
    env = {**os.environ, '_CATALOG_VENV': '1'}

    old_argv = sys.argv[:]
    old_env  = os.environ.get('_CATALOG_VENV')
    try:
        import importlib.util as ilu
        sys.argv = [str(path), '--help']
        os.environ['_CATALOG_VENV'] = '1'
        spec = ilu.spec_from_file_location('_vt', str(path))
        mod  = ilu.module_from_spec(spec)
        sys.path.insert(0, str(path.parent))
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
        finally:
            if sys.path and sys.path[0] == str(path.parent):
                sys.path.pop(0)
    except Exception as e:
        issues.append(Issue(ERROR, path, None, None,
                            f"Module load: {type(e).__name__}: {e}", 'exec'))
        return issues
    finally:
        sys.argv = old_argv
        if old_env is None:
            os.environ.pop('_CATALOG_VENV', None)
        else:
            os.environ['_CATALOG_VENV'] = old_env

    try:
        result = subprocess.run(
            [sys.executable, str(path), '--help'],
            capture_output=True, text=True, timeout=15, env=env
        )
        if result.returncode not in (0, 1):
            out = (result.stderr or result.stdout).strip()
            fatal = [l for l in out.splitlines()
                     if any(k in l for k in ('Error', 'Traceback', 'Exception'))
                     and 'DeprecationWarning' not in l]
            if fatal:
                issues.append(Issue(ERROR, path, None, None,
                                    f"--help (rc={result.returncode}): {fatal[0]}", 'exec'))
    except subprocess.TimeoutExpired:
        issues.append(Issue(WARN, path, None, None, '--help timed out (>15 s)', 'exec'))
    except Exception as e:
        issues.append(Issue(WARN, path, None, None, f"--help error: {e}", 'exec'))
    return issues


# ── JavaScript: syntax (node --check) ─────────────────────────────────────────

def _has_node() -> bool:
    return shutil.which('node') is not None


def check_js_syntax(path: Path) -> list[Issue]:
    if not _has_node():
        return [Issue(WARN, path, None, None, 'node not found — skipped', 'js')]
    result = subprocess.run(['node', '--check', str(path)], capture_output=True, text=True)
    issues: list[Issue] = []
    if result.returncode != 0:
        for line in (result.stderr or result.stdout).splitlines():
            m = re.search(r':(\d+)$', line)
            issues.append(Issue(ERROR, path, int(m.group(1)) if m else None,
                                None, line.strip(), 'js'))
    return issues


# ── JavaScript: ESLint ────────────────────────────────────────────────────────

def _has_npx() -> bool:
    return shutil.which('npx') is not None


def check_js_eslint(path: Path) -> list[Issue]:
    if not ESLINT_CONFIG.exists() or not _has_npx():
        return []
    result = subprocess.run(
        ['npx', 'eslint', '--config', str(ESLINT_CONFIG), '--format', 'json', str(path)],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if not result.stdout.strip():
        if result.returncode > 1:
            return [Issue(WARN, path, None, None,
                          f"ESLint config error: {result.stderr[:200].strip()}", 'eslint')]
        return []
    try:
        issues: list[Issue] = []
        for fr in json.loads(result.stdout):
            for msg in fr.get('messages', []):
                sev  = ERROR if msg.get('severity') == 2 else WARN
                rule = msg.get('ruleId') or 'eslint'
                issues.append(Issue(sev, path, msg.get('line'), msg.get('column'),
                                    f"[{rule}] {msg['message']}", 'eslint'))
        return issues
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return [Issue(WARN, path, None, None, f"ESLint parse error: {e}", 'eslint')]


# ── HTML: broken local references ─────────────────────────────────────────────

_REF_RE = re.compile(r'''(?:src|href)\s*=\s*['"]([^'"#?]+)['"]''')
_SKIP_SCHEMES = ('http://', 'https://', 'data:', '//', 'mailto:', 'tel:', 'about:', '#')


def check_html_refs(path: Path) -> list[Issue]:
    issues: list[Issue] = []
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return [Issue(ERROR, path, None, None, f"Cannot read: {e}", 'html')]

    base = path.parent
    for i, line in enumerate(content.splitlines(), 1):
        for ref in _REF_RE.findall(line):
            if any(ref.startswith(s) for s in _SKIP_SCHEMES):
                continue
            resolved = (ROOT / ref.lstrip('/')) if ref.startswith('/') \
                       else (base / ref).resolve()
            if not resolved.exists():
                rel = resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved
                issues.append(Issue(ERROR, path, i, None,
                                    f"Broken ref: {ref!r} → {rel}", 'html'))
    return issues


# ── HTML: html-validate ───────────────────────────────────────────────────────

def check_html_validate(path: Path) -> list[Issue]:
    if not HTMLVALIDATE_CONFIG.exists() or not _has_npx():
        return []
    result = subprocess.run(
        ['npx', 'html-validate', '--config', str(HTMLVALIDATE_CONFIG),
         '--formatter', 'json', str(path)],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    stdout = result.stdout.strip()
    if not stdout:
        return []
    try:
        issues: list[Issue] = []
        for fr in json.loads(stdout):
            for msg in fr.get('messages', []):
                sev  = ERROR if msg.get('severity') == 2 else WARN
                rule = msg.get('ruleId') or 'html-validate'
                issues.append(Issue(sev, path, msg.get('line'), msg.get('column'),
                                    f"[{rule}] {msg['message']}", 'html-validate'))
        return issues
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return [Issue(WARN, path, None, None, f"html-validate parse error: {e}", 'html-validate')]


# ── CSS: stylelint ────────────────────────────────────────────────────────────

def check_css_stylelint(path: Path) -> list[Issue]:
    if not STYLELINT_CONFIG.exists() or not _has_npx():
        return []
    result = subprocess.run(
        ['npx', 'stylelint', '--config', str(STYLELINT_CONFIG),
         '--formatter', 'json', str(path)],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    stdout = result.stdout.strip()
    if not stdout:
        return []
    try:
        issues: list[Issue] = []
        for fr in json.loads(stdout):
            for w in fr.get('warnings', []):
                sev  = ERROR if w.get('severity') == 'error' else WARN
                rule = w.get('rule') or 'stylelint'
                text = re.sub(r'\s*\(' + re.escape(rule) + r'\)\s*$', '', w.get('text', ''))
                issues.append(Issue(sev, path, w.get('line'), w.get('column'),
                                    f"[{rule}] {text}", 'css'))
        return issues
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return [Issue(WARN, path, None, None, f"stylelint parse error: {e}", 'css')]


# ── Runner ────────────────────────────────────────────────────────────────────

def run_checks(
    paths_py:   list[Path],
    paths_js:   list[Path],
    paths_css:  list[Path],
    paths_html: list[Path],
    *,
    do_syntax=True, do_imports=True, do_exec=False,
    do_js=True, do_eslint=True,
    do_css=True,
    do_html=True, do_html_validate=True,
) -> tuple[list[Issue], list[Path]]:
    all_issues: list[Issue] = []
    checked:    list[Path]  = []
    has_pf  = _has_pyflakes()
    has_npx = _has_npx()

    if do_imports and not has_pf:
        print(f"{C['yellow']}  pyflakes not installed — import checks skipped  "
              f"(pip install pyflakes){C['reset']}")
    if (do_eslint or do_html_validate or do_css) and not has_npx:
        print(f"{C['yellow']}  npx not found — ESLint/html-validate/stylelint skipped{C['reset']}")

    for p in paths_py:
        checked.append(p)
        if do_syntax:              all_issues.extend(check_python_syntax(p))
        if do_imports and has_pf:  all_issues.extend(check_python_imports(p))
        if do_exec:                all_issues.extend(check_python_exec(p))

    for p in paths_js:
        checked.append(p)
        if do_js:                    all_issues.extend(check_js_syntax(p))
        if do_eslint and has_npx:    all_issues.extend(check_js_eslint(p))

    for p in paths_css:
        checked.append(p)
        if do_css and has_npx:       all_issues.extend(check_css_stylelint(p))

    for p in paths_html:
        checked.append(p)
        if do_html:                          all_issues.extend(check_html_refs(p))
        if do_html_validate and has_npx:     all_issues.extend(check_html_validate(p))

    return all_issues, checked


# ── Console report ────────────────────────────────────────────────────────────

def _rel(path_str: str) -> str:
    try:
        return str(Path(path_str).relative_to(ROOT))
    except ValueError:
        return path_str


def print_report(issues: list[Issue], checked: list[Path], verbose=False):
    by_file: dict[str, list[Issue]] = {}
    for iss in issues:
        by_file.setdefault(iss.path, []).append(iss)

    errors = [i for i in issues if i.severity == ERROR]
    warns  = [i for i in issues if i.severity == WARN]
    infos  = [i for i in issues if i.severity == INFO]

    print()
    for p in checked:
        rel         = _rel(str(p))
        file_issues = by_file.get(str(p), [])
        ferrs       = [i for i in file_issues if i.severity == ERROR]
        fwarns      = [i for i in file_issues if i.severity == WARN]

        if not ferrs and not fwarns:
            if verbose or not file_issues:
                print(f"  {C['green']}OK   {C['reset']}{C['dim']}{rel}{C['reset']}")
            continue

        badge = f"{C['red']}ERROR{C['reset']}" if ferrs else f"{C['yellow']}WARN {C['reset']}"
        print(f"  {badge} {C['bold']}{rel}{C['reset']}")
        for iss in file_issues:
            if not verbose and iss.severity == INFO:
                continue
            sc = {'ERROR': C['red'], 'WARN': C['yellow'], 'INFO': C['cyan']}.get(iss.severity, '')
            loc = f"L{iss.line}" if iss.line else '?'
            print(f"    {sc}{iss.severity:<5}{C['reset']} {loc:<7}  {iss.message}")
        print()

    print(f"  {'─'*60}")
    if not errors and not warns:
        print(f"  {C['green']}{C['bold']}All checks passed.{C['reset']}\n")
    else:
        parts = []
        if errors: parts.append(f"{C['red']}{len(errors)} error(s){C['reset']}")
        if warns:  parts.append(f"{C['yellow']}{len(warns)} warning(s){C['reset']}")
        if infos and verbose: parts.append(f"{C['cyan']}{len(infos)} info{C['reset']}")
        print(f"  {', '.join(parts)}\n")


# ── HTML report ───────────────────────────────────────────────────────────────

def generate_html_report(issues: list[Issue], checked: list[Path]) -> str:
    """Return a standalone HTML validation report as a string."""
    by_file: dict[str, list[Issue]] = {}
    for iss in issues:
        by_file.setdefault(iss.path, []).append(iss)

    errors = sum(1 for i in issues if i.severity == ERROR)
    warns  = sum(1 for i in issues if i.severity == WARN)
    ok     = sum(1 for p in checked if not any(i.severity in (ERROR, WARN)
                                               for i in by_file.get(str(p), [])))

    status_cls = 'status-error' if errors else ('status-warn' if warns else 'status-ok')
    status_txt = f'{errors} error(s), {warns} warning(s)' if errors or warns else 'All checks passed'

    rows = []
    for p in checked:
        rel  = _rel(str(p))
        fi   = by_file.get(str(p), [])
        fe   = [i for i in fi if i.severity == ERROR]
        fw   = [i for i in fi if i.severity == WARN]
        cls  = 'row-error' if fe else ('row-warn' if fw else 'row-ok')
        badge = ('<span class="badge badge-error">ERROR</span>' if fe
                 else '<span class="badge badge-warn">WARN</span>' if fw
                 else '<span class="badge badge-ok">OK</span>')
        detail_rows = ''.join(
            f'<tr class="issue issue-{i.severity.lower()}">'
            f'<td>{i.severity}</td>'
            f'<td>{i.line or "—"}</td>'
            f'<td>{i.check}</td>'
            f'<td>{_html_esc(i.message)}</td></tr>'
            for i in fi if i.severity in (ERROR, WARN)
        )
        detail = (
            f'<tr class="detail-row"><td colspan="3">'
            f'<table class="detail-table"><thead><tr>'
            f'<th>Sev</th><th>Line</th><th>Check</th><th>Message</th>'
            f'</tr></thead><tbody>{detail_rows}</tbody></table></td></tr>'
            if detail_rows else ''
        )
        toggle = (
            f' onclick="this.closest(\'tr\').nextSibling.classList.toggle(\'hidden\')" '
            f'style="cursor:pointer" title="Toggle details"'
            if detail_rows else ''
        )
        rows.append(
            f'<tr class="{cls}"{toggle}>'
            f'<td>{badge}</td><td class="filepath">{rel}</td>'
            f'<td>{len(fe) or ""}</td><td>{len(fw) or ""}</td>'
            f'</tr>{detail}'
        )

    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    file_rows = '\n'.join(rows)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Validation Report — {_html_esc(PROJECT_NAME)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#0f1117;color:#e2e8f0;font-size:14px;line-height:1.5}}
header{{background:#1a1d2e;border-bottom:2px solid #2d3148;padding:24px 32px}}
header h1{{font-size:22px;font-weight:700;color:#a5b4fc;margin-bottom:4px}}
.meta{{color:#64748b;font-size:12px}}
.summary{{display:flex;gap:16px;margin-top:16px;flex-wrap:wrap}}
.stat{{padding:8px 16px;border-radius:8px;font-weight:600;font-size:13px}}
.stat-ok{{background:#052e16;color:#4ade80;border:1px solid #166534}}
.stat-warn{{background:#2d1b00;color:#fbbf24;border:1px solid #92400e}}
.stat-error{{background:#2d0a0a;color:#f87171;border:1px solid #7f1d1d}}
.{status_cls}{{}}
main{{padding:24px 32px}}
.section-title{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;
  color:#475569;margin:20px 0 8px;font-weight:600}}
table{{width:100%;border-collapse:collapse;background:#1a1d2e;
  border-radius:8px;overflow:hidden}}
th{{background:#252843;color:#94a3b8;font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;padding:8px 12px;text-align:left}}
td{{padding:8px 12px;border-bottom:1px solid #252843;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.row-ok td{{color:#94a3b8}}
.row-warn td{{color:#fde68a}}
.row-error td{{color:#fca5a5}}
.filepath{{font-family:monospace;font-size:12px}}
.badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700}}
.badge-ok{{background:#166534;color:#4ade80}}
.badge-warn{{background:#92400e;color:#fbbf24}}
.badge-error{{background:#7f1d1d;color:#f87171}}
.detail-row td{{padding:0 12px 8px 32px;background:#0f1117}}
.detail-table{{width:100%;font-size:12px;margin:4px 0}}
.detail-table th{{background:#1a1d2e;padding:4px 8px}}
.detail-table td{{padding:4px 8px;border-bottom:1px solid #1e2133}}
.issue-error td{{color:#f87171}}
.issue-warn td{{color:#fbbf24}}
.hidden{{display:none}}
.row-warn:hover td, .row-error:hover td{{background:#252843}}
</style>
</head>
<body>
<header>
  <h1>&#x1F50D; Validation Report</h1>
  <div class="meta">{_html_esc(PROJECT_NAME)} &nbsp;·&nbsp; {ts}</div>
  <div class="summary">
    <span class="stat stat-ok">&#x2713; {ok} OK</span>
    <span class="stat stat-warn">&#x26A0; {warns} warnings</span>
    <span class="stat stat-error">&#x2715; {errors} errors</span>
  </div>
</header>
<main>
  <div class="section-title">Files checked — {len(checked)} total &nbsp;|&nbsp; {status_txt}
  &nbsp;(click a row to expand issues)</div>
  <table>
    <thead><tr><th>Status</th><th>File</th><th>Errors</th><th>Warns</th></tr></thead>
    <tbody>{file_rows}</tbody>
  </table>
</main>
</body>
</html>'''


def _html_esc(s: str) -> str:
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Language-agnostic static validator (Python, JS, CSS, HTML)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('files',       nargs='*',       help='Specific files (default: all)')
    parser.add_argument('--python',    action='store_true', help='Python files only')
    parser.add_argument('--js',        action='store_true', help='JS files only')
    parser.add_argument('--css',       action='store_true', help='CSS files only')
    parser.add_argument('--html',      action='store_true', help='HTML files only')
    parser.add_argument('--no-imports',action='store_true', help='Skip pyflakes checks')
    parser.add_argument('--no-lint',   action='store_true', help='Skip ESLint/html-validate/stylelint')
    parser.add_argument('--exec',      action='store_true', help='Python dry-run execution')
    parser.add_argument('--report',    action='store_true', help='Save HTML/TXT report (path from env.py)')
    parser.add_argument('--report-out',metavar='FILE',   help='Save report to this path (overrides env.py)')
    parser.add_argument('--verbose',   '-v', action='store_true', help='Show INFO items too')
    parser.add_argument('--json',      action='store_true', help='JSON output (machine-readable)')
    args = parser.parse_args()

    if args.python or args.js or args.css or args.html:
        do_py = args.python; do_js_ = args.js
        do_css_ = args.css;  do_html = args.html
    else:
        do_py = do_js_ = do_css_ = do_html = True

    do_syntax        = do_py
    do_imports       = do_py and not args.no_imports
    do_exec          = do_py and args.exec
    do_js            = do_js_
    do_eslint        = do_js_ and not args.no_lint
    do_css           = do_css_ and not args.no_lint
    do_html_refs     = do_html
    do_html_validate = do_html and not args.no_lint

    if args.files:
        paths = [Path(f).resolve() for f in args.files]
        py_files   = [p for p in paths if p.suffix == '.py']
        js_files   = [p for p in paths if p.suffix == '.js']
        css_files  = [p for p in paths if p.suffix == '.css']
        html_files = [p for p in paths if p.suffix == '.html']
    else:
        py_files   = PYTHON_FILES if do_py   else []
        js_files   = JS_FILES     if do_js_  else []
        css_files  = CSS_FILES    if do_css_ else []
        html_files = HTML_FILES   if do_html else []

    if not args.json:
        print(f"\n{C['bold']}Static Validator — {PROJECT_NAME}{C['reset']}")
        print(f"{C['dim']}Root: {ROOT}{C['reset']}")
        counts = ([f"{len(py_files)} Python"] if py_files else []) + \
                 ([f"{len(js_files)} JS"]     if js_files else []) + \
                 ([f"{len(css_files)} CSS"]   if css_files else []) + \
                 ([f"{len(html_files)} HTML"] if html_files else [])
        lint_note = f" {C['dim']}(lint tools disabled){C['reset']}" if args.no_lint else ''
        print(f"Checking: {', '.join(counts)} files{lint_note}\n")

    issues, checked = run_checks(
        py_files, js_files, css_files, html_files,
        do_syntax=do_syntax, do_imports=do_imports, do_exec=do_exec,
        do_js=do_js, do_eslint=do_eslint,
        do_css=do_css,
        do_html=do_html_refs, do_html_validate=do_html_validate,
    )

    if args.json:
        print(json.dumps([i.as_dict() for i in issues], indent=2))
    else:
        print_report(issues, checked, verbose=args.verbose)

    # ── Save report file ──────────────────────────────────────────────────────
    report_path_str = args.report_out or (REPORT_FILE if (args.report or REPORT_FILE) else None)
    if report_path_str:
        rp = Path(report_path_str)
        if not rp.is_absolute():
            rp = ROOT / rp
        fmt = REPORT_FORMAT
        if rp.suffix == '.json':
            fmt = 'json'
        elif rp.suffix == '.txt':
            fmt = 'txt'
        rp.parent.mkdir(parents=True, exist_ok=True)
        if fmt == 'json':
            rp.write_text(json.dumps([i.as_dict() for i in issues], indent=2), encoding='utf-8')
        elif fmt == 'txt':
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                print_report(issues, checked, verbose=True)
            rp.write_text(buf.getvalue(), encoding='utf-8')
        else:
            rp.write_text(generate_html_report(issues, checked), encoding='utf-8')
        if not args.json:
            print(f"  {C['cyan']}Report saved: {rp}{C['reset']}\n")

    sys.exit(1 if any(i.severity == ERROR for i in issues) else 0)


if __name__ == '__main__':
    main()
