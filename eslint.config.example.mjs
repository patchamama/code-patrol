// eslint.config.example.mjs — ESLint flat config template for browser scripts.
//
// Copy to eslint.config.mjs in your tools/ directory and adjust:
//   1. The file patterns in each `files` block
//   2. The sharedGlobals / pageGlobals to match your project's window-level functions
//   3. Per-file global overrides (e.g. one entry-point script defines functions
//      that other scripts call — list those as 'readonly' globals for the callers)

import js      from '@eslint/js';
import globals from 'globals';

// ── Globals defined in shared scripts loaded on every page ────────────────────
// Add any function/variable that is defined in one JS file but called from others.
const sharedGlobals = {
  // Examples — replace with your project's public API:
  apiUrl:       'readonly',
  escHtml:      'readonly',
  openModal:    'readonly',
  closeModal:   'readonly',
};

// ── Third-party CDN globals ───────────────────────────────────────────────────
const cdnGlobals = {
  hljs:   'readonly',   // highlight.js
  marked: 'readonly',   // marked.js markdown parser
  // Add others as needed (e.g. Chart, dayjs, Sortable, ...)
};

// ── Rules shared by all files ─────────────────────────────────────────────────
const sharedRules = {
  'no-undef':             'error',
  'no-dupe-keys':         'error',
  'no-duplicate-case':    'error',
  'no-unreachable':       'warn',
  'no-use-before-define': ['warn', { functions: false, classes: true, variables: true }],
  'no-empty':             ['warn', { allowEmptyCatch: true }],
  'no-unused-vars':       ['warn', { vars: 'local', args: 'none',
                                     varsIgnorePattern: '^_', ignoreRestSiblings: true }],
  'eqeqeq':               ['warn', 'always', { null: 'ignore' }],
  'no-console':            'off',
  'no-var':                'off',
  'prefer-const':          'off',
  'no-redeclare':          'off',
};

export default [
  js.configs.recommended,

  // ── Main / shared script (defines the public API) ─────────────────────────
  {
    files: ['static/js/main.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType:  'script',
      globals: { ...globals.browser, ...cdnGlobals },
    },
    rules: sharedRules,
  },

  // ── Feature scripts (consume the public API) ──────────────────────────────
  {
    files: ['static/js/feature-a.js', 'static/js/feature-b.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType:  'script',
      globals: { ...globals.browser, ...cdnGlobals, ...sharedGlobals },
    },
    rules: sharedRules,
  },
];
