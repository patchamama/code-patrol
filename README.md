# code-patrol

> **Language-agnostic static validator for web projects.**
> Python · JavaScript · CSS · HTML — one command, one report.

---

## Why code-patrol?

Most projects start without a formal test suite. Structural errors accumulate silently: an import that stopped working after a rename, a CSS property that was deprecated, a broken `<script src="…">` that only fails at runtime. `code-patrol` catches all of these **without executing business logic** — no side effects, no database connections, no running servers.

### Where it helps most

| Scenario | What it does for you |
|----------|----------------------|
| **No tests yet** | Acts as a first safety net — catches hidden bugs automatically before any logic-level testing |
| **Taking over a legacy project** | Validates the entire codebase before you touch a single line, so you start from a known baseline |
| **Onboarding a third-party project** | Understand the code health at a glance before committing to use or extend it |
| **Before writing tests** | Cleans up obvious errors first, so test-writing starts from solid ground |
| **Continuous integration** | Runs in seconds, integrates with any CI pipeline |

### What it detects (without running the application)

**Python**
- `SyntaxError` and `SyntaxWarning` (invalid escape sequences, deprecated syntax)
- `ImportError` — modules that don't exist or were renamed
- Undefined names, unused imports, shadowed variables, bare f-strings
- Module-level runtime errors (via optional dry-run execution)

**JavaScript**
- Syntax errors (via `node --check`)
- Undefined global variables, unused local variables
- Calling functions that don't exist in the page context
- Rule violations configured per-project (ESLint)

**CSS**
- Deprecated property values (e.g. `word-break: break-word`)
- Invalid hex colors, unknown properties, duplicate selectors
- `rgba()` / modern notation consistency

**HTML**
- Broken local `src` / `href` references (files that don't exist on disk)
- Missing required attributes, invalid attribute values
- Structural violations (heading hierarchy, element nesting)

---

## Quick Start

### 1. Install prerequisites

**Python 3**

```bash
# macOS (Homebrew)
brew install python3

# Linux (Debian / Ubuntu)
sudo apt update && sudo apt install -y python3 python3-venv python3-pip

# Windows (winget)
winget install Python.Python.3
# or download the installer from https://www.python.org/downloads/
```

**Node.js**

```bash
# macOS (Homebrew)
brew install node

# Linux (Debian / Ubuntu)
sudo apt update && sudo apt install -y nodejs npm

# Windows (winget)
winget install OpenJS.NodeJS
# or download the installer from https://nodejs.org
```

### 2. Set up the project

```bash
# Clone or copy validate.py + env.example.py into your project's tools/ folder

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows (cmd)
# venv\Scripts\Activate.ps1       # Windows (PowerShell)

# Install Python dependencies
pip install -r requirements.txt

# Install Node lint tools (optional but recommended)
npm install --save-dev @eslint/js globals html-validate stylelint stylelint-config-standard

# Configure for your project
cp env.example.py env.py          # edit paths to match your project
cp eslint.config.example.mjs eslint.config.mjs   # customise ESLint globals

# Run
python3 tools/validate.py
```

---

## Configuration (`env.py`)

All project-specific settings live in `env.py` (same folder as `validate.py`). This file is **not** committed to the validator's repository — it belongs to each project that uses the tool.

```python
# env.py
from pathlib import Path

ROOT         = Path(__file__).parent.parent.resolve()   # project root
PROJECT_NAME = 'My Project'

PYTHON_DIRS  = ['src', 'scripts']          # dirs to scan for *.py
JS_DIRS      = ['static/js']               # dirs to scan for *.js
CSS_DIRS     = ['static/css']              # dirs to scan for *.css
HTML_FILES   = ['index.html', 'app.html']  # explicit HTML files

# Lint tool configs (relative to tools/)
ESLINT_CONFIG       = 'eslint.config.mjs'
HTMLVALIDATE_CONFIG = '.htmlvalidate.json'
STYLELINT_CONFIG    = '.stylelintrc.json'

# Optional: auto-save report after every run
REPORT_FILE   = 'tools/report.html'        # None = console only
REPORT_FORMAT = 'html'                     # 'html' | 'json' | 'txt'
```

See `env.example.py` for all available options with comments.

---

## Usage

```bash
# All checks (default)
python3 tools/validate.py

# Specific language
python3 tools/validate.py --python
python3 tools/validate.py --js
python3 tools/validate.py --css
python3 tools/validate.py --html

# Single file
python3 tools/validate.py src/app.py

# Python dry-run execution (catches runtime import errors)
python3 tools/validate.py --exec

# Skip npm-based linters (ESLint / html-validate / stylelint)
python3 tools/validate.py --no-lint

# Save HTML report
python3 tools/validate.py --report
python3 tools/validate.py --report-out build/report.html

# Machine-readable JSON (pipe to other tools or AI)
python3 tools/validate.py --json

# Verbose (show INFO-level items too)
python3 tools/validate.py -v
```

**Exit codes:** `0` = no errors, `1` = one or more errors found.

---

## Using AI to Fix Errors

One of the most productive workflows is to feed the validation report directly to an AI assistant that can read your code and fix the issues automatically.

### Claude Code (CLI)

```bash
# Generate a JSON report, then ask Claude to fix everything
python3 tools/validate.py --json > /tmp/report.json
claude "Read /tmp/report.json. For each error listed, find the affected file in the project and apply the exact fix. Don't fix warnings unless they indicate real problems."

# Or pipe directly for a quick interactive session
python3 tools/validate.py 2>&1 | claude --print \
  "These are validation errors from my project. For each error, show the file path, the problem, and the exact line change needed to fix it."
```

### Inside a Claude Code session

Use slash-command style prompts for targeted fixes:

```
Run python3 tools/validate.py --json and fix all errors found.
For each fix, explain what was wrong in one sentence.
```

```
Run python3 tools/validate.py --python --exec and investigate any
module load errors. Trace the import chain to find the root cause.
```

### With other AI CLIs (OpenAI, Gemini, etc.)

```bash
# Any AI CLI that reads stdin
python3 tools/validate.py --json | ai-cli "Fix the errors in this validation report"

# GPT-4 via shell
REPORT=$(python3 tools/validate.py --json)
openai api chat.completions.create \
  -m gpt-4o \
  -g user "Fix these validation errors: $REPORT"
```

### Tips for effective AI-assisted fixes

- Use `--json` output — structured format gives the AI precise line numbers and rule IDs
- Fix `ERROR` level issues first, then decide which `WARN`ings matter
- For ESLint `no-undef` errors, ask the AI to trace *where* the function is defined — it may need a globals declaration rather than a code change
- For Python `ImportError`, ask the AI to also check if the module was renamed recently via `git log`

---

## Common Errors Detected

### Python

```
# SyntaxWarning: invalid escape sequence
path = "C:\new_folder"         # \n is escape sequence, not literal backslash
# Fix:
path = r"C:\new_folder"        # raw string

# ImportError after rename
from old_module import Worker   # module was renamed to new_module.py
# Fix:
from new_module import Worker

# Undefined name
def process(data):
    return resutl                # typo: 'resutl' is not defined
# Fix:
    return result

# Unused import (pyflakes WARN)
from urllib.parse import quote   # imported but never called
```

### JavaScript

```js
// no-undef: calling a function defined in another script file
doSearch(query);   // doSearch is defined in es_test.js but not listed as a global
// Fix: add to ESLint globals config for this file

// no-unused-vars
function openModal(id) {
    const unused = computeData();  // 'unused' never referenced again
}

// Broken script reference in HTML
<script src="assets/catalog.js"></script>  <!-- file moved to js/catalog.js -->
```

### CSS

```css
/* Deprecated value */
.container { word-break: break-word; }   /* non-standard, deprecated */
/* Fix: */
.container { overflow-wrap: break-word; }

/* Duplicate selector (property conflict risk) */
.card { background: #fff; }
/* ... 200 lines later ... */
.card { background: #f0f0f0; }   /* duplicates + overrides silently */

/* Invalid hex */
color: #gghhii;   /* invalid hex characters */
```

### HTML

```html
<!-- Broken local reference -->
<script src="js/app.js"></script>   <!-- file is at assets/app.js, not js/app.js -->

<!-- Empty iframe src causes the parent page to reload inside itself -->
<iframe src=""></iframe>
<!-- Fix: -->
<iframe src="about:blank" title="Content viewer"></iframe>

<!-- Missing required attribute -->
<img src="logo.png">          <!-- missing alt — accessibility violation -->
<iframe src="video.html">     <!-- missing title — screen reader issue -->
```

---

## Project Structure

```
tools/
├── validate.py              # the validator (language-agnostic, reads env.py)
├── env.py                   # your project config (not in this repo)
├── env.example.py           # template — copy to env.py
├── eslint.config.mjs        # ESLint rules (customise per project)
├── eslint.config.example.mjs
├── .htmlvalidate.json       # html-validate rules
├── .htmlvalidate.example.json
├── .stylelintrc.json        # stylelint rules
├── .stylelintrc.example.json
├── requirements.txt         # pip install -r requirements.txt
└── README.md
```

---

## Integrating with CI/CD

```yaml
# .github/workflows/validate.yml
name: Static Validation
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: pip install -r tools/requirements.txt
      - run: npm ci
      - run: python3 tools/validate.py --json > report.json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: validation-report
          path: report.json
```

---

## TODO / Roadmap

### Near-term

- [ ] **TypeScript support** — `tsc --noEmit` for type checking without compilation
- [ ] **JSON validation** — schema validation via `jsonschema`, detect duplicate keys, invalid syntax
- [ ] **YAML validation** — syntax check + optional schema validation
- [ ] **Markdown lint** — `markdownlint` integration for documentation quality
- [ ] **Dead code detection** — track which functions/classes are never called across the codebase
- [ ] **Circular import detection** — Python circular dependencies
- [ ] **Dependency vulnerability scan** — `pip-audit` for Python, `npm audit` for Node

### Intermediate

- [ ] **SQL simulation** — Parse SQL files and validate syntax for MySQL, PostgreSQL, SQLite:
  - `sqlfluff` for dialect-aware linting
  - Detect undefined table/column references within a schema file
  - Simulate `CREATE TABLE` → `SELECT` flows to catch column-name mismatches
- [ ] **XML/HTML template validation** — DTD/XSD schema checking
- [ ] **Environment variable audit** — detect `.env` keys referenced in code but missing from `.env.example`
- [ ] **Secret detection** — scan for accidentally committed credentials, API keys, tokens (like `detect-secrets`)
- [ ] **Git hook integration** — auto-run on `pre-commit`
- [ ] **VSCode extension** — inline underline of issues in the editor

### Advanced

- [ ] **Playwright browser testing** — open the frontend in a real browser and:
  - Click through all interactive elements (buttons, tabs, modals, forms)
  - Monitor the browser console for `console.error` and unhandled exceptions
  - Capture network errors (404s, CORS failures)
  - Screenshot diffs between runs to detect unintended visual regressions
  - Example:
    ```python
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda msg: collect_console(msg))
        page.goto("http://localhost:5000")
        for btn in page.query_selector_all("button"):
            btn.click(); page.wait_for_timeout(200)
    ```

- [ ] **OWASP / Security checks**
  - XSS: detect `innerHTML =` with unescaped user input in JS
  - SQL injection: detect string-concatenated queries in Python/JS
  - CSRF: check that forms have protection tokens
  - Hardcoded secrets in source code
  - Insecure `eval()` / `exec()` usage
  - Open redirects: `href` or `redirect()` built from user input
  - Missing `Content-Security-Policy` / security headers in HTML/server code
  - Dependency CVE scanning via `pip-audit` / `npm audit`

- [ ] **Performance hints**
  - Detect synchronous `fs` calls in async Node.js code
  - Flag large inline images (base64 in CSS/HTML)
  - Missing `loading="lazy"` on `<img>` tags
  - Unused CSS selectors (compare CSS classes against HTML)

- [ ] **Auto-fix mode** — apply safe, mechanical fixes automatically:
  - `--fix` to run ESLint/stylelint auto-fix
  - Replace deprecated patterns (e.g. `word-break: break-word` → `overflow-wrap`)
  - Add missing `type="button"` to `<button>` elements
  - Add `about:blank` to empty `<iframe src="">`

- [ ] **Watch mode** — `--watch` to re-run checks on file save (using `watchdog`)

- [ ] **HTML report enhancements**
  - Severity filter (show only errors / warnings)
  - Group by check type (syntax / lint / broken-refs)
  - Trend graph across multiple runs (requires storing history)
  - Diff view: compare two reports to see what regressed

- [ ] **Plugin system** — allow custom check functions via `env.py`:
  ```python
  # env.py
  def custom_check(path):
      # your domain-specific rule
      ...
  EXTRA_CHECKS = {'*.py': [custom_check]}
  ```

---

## Dependencies

| Tool | Purpose | Install |
|------|---------|---------|
| `python3` | Runtime | macOS: `brew install python3` · Linux: `sudo apt install python3 python3-venv` · Windows: `winget install Python.Python.3` |
| `pyflakes` | Python import/name analysis | `pip install pyflakes` (included in `requirements.txt`) |
| `node` | JS syntax check (`node --check`) | macOS: `brew install node` · Linux: `sudo apt install nodejs npm` · Windows: `winget install OpenJS.NodeJS` |
| `eslint` | JS linting | `npm i -D eslint @eslint/js globals` |
| `html-validate` | HTML structure validation | `npm i -D html-validate` |
| `stylelint` | CSS linting | `npm i -D stylelint stylelint-config-standard` |

All npm tools are optional. `validate.py` skips any tool whose config file doesn't exist or whose binary isn't found.

---

## License

MIT
