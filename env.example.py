"""
env.example.py — Template configuration for validate.py.

Copy this file to env.py in your tools/ directory and adjust
paths and settings to match your project structure.
"""

from pathlib import Path

# ── Project identity ──────────────────────────────────────────────────────────
# ROOT is the directory validate.py considers as the project root.
# By default it is the parent of the tools/ directory.
ROOT = Path(__file__).parent.parent.resolve()

# Human-readable name shown in reports and console output.
PROJECT_NAME = 'My Project'

# ── Python files ──────────────────────────────────────────────────────────────
# Directories scanned recursively for *.py files (relative to ROOT).
PYTHON_DIRS = ['src', 'scripts']

# Additional explicit files beyond directory scanning.
PYTHON_EXTRA: list[str] = ['manage.py']

# Folder names to skip while scanning.
PYTHON_EXCLUDE_DIRS = ['__pycache__', '.venv', 'venv', 'node_modules', '.git',
                       'dist', 'build', 'migrations']

# ── JavaScript files ──────────────────────────────────────────────────────────
JS_DIRS = ['static/js', 'src/js']
JS_EXTRA: list[str] = []
JS_EXCLUDE_DIRS = ['node_modules', 'dist', '.venv']

# ── CSS files ─────────────────────────────────────────────────────────────────
CSS_DIRS = ['static/css', 'src/css']
CSS_EXTRA: list[str] = []
CSS_EXCLUDE_DIRS = ['node_modules', 'dist']

# ── HTML files ────────────────────────────────────────────────────────────────
# Option A — explicit list (relative to ROOT):
HTML_FILES = [
    'index.html',
    'templates/base.html',
]

# Option B — scan directories (relative to ROOT):
HTML_DIRS: list[str] = []          # e.g. ['templates']
HTML_EXTRA: list[str] = []
HTML_EXCLUDE_DIRS = ['node_modules', 'dist', '.venv']

# ── Lint tool configs ─────────────────────────────────────────────────────────
# Paths relative to this file's directory (tools/) or absolute.
ESLINT_CONFIG       = 'eslint.config.mjs'     # ESLint v9 flat config
HTMLVALIDATE_CONFIG = '.htmlvalidate.json'     # html-validate rules
STYLELINT_CONFIG    = '.stylelintrc.json'      # stylelint rules

# ── Report output ─────────────────────────────────────────────────────────────
# Automatically save a report after every run.
# Set to None to print to console only.
# Relative paths are resolved from ROOT.
REPORT_FILE: str | None = None           # e.g. 'tools/report.html'
REPORT_FORMAT = 'html'                   # 'html' | 'json' | 'txt'
