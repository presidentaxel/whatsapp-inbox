// ESLint v9 flat config (https://eslint.org/docs/latest/use/configure/configuration-files-new).
//
// Fichier .mjs : évite l'avertissement Node sur eslint.config.js sans "type":"module"
// (le script scripts/update-version.js reste en CommonJS).
//
// Choix:
//  - On reste *permissif* sur l'existant : la base de code est en JS et a déjà
//    pas mal de patterns en place. L'objectif est d'attraper les vrais bugs
//    (variables non utilisées, hooks mal appelés, exhaustive-deps, refresh
//    component) sans noyer la console au premier `npm run lint`.
//  - Les fichiers générés (`dist/`, builds) et les bundles copiés dans `public/`
//    sont ignorés (ex. worker PDF minifié : pas du code à linter).
//  - Les règles trop intrusives sont en `warn` plutôt que `error` pour qu'on
//    puisse durcir progressivement.
import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  {
    ignores: [
      "dist/**",
      "build/**",
      "node_modules/**",
      "coverage/**",
      "scripts/update-version.js",
      // Worker PDF minifié (vendor) : globals navigateur, pas du code projet
      "public/pdf.worker*.mjs",
      "public/**/*.min.mjs",
      // Service worker : API `clients` / `self` hors scope ESLint navigateur classique
      "public/sw.js",
    ],
  },

  js.configs.recommended,

  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2024,
        ...globals.node,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: "detect" },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // Bugs probables
      "no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" },
      ],
      "no-undef": "error",
      "no-empty": ["warn", { allowEmptyCatch: true }],
      "no-constant-condition": ["warn", { checkLoops: false }],

      // React (mode 17+: pas besoin d'importer React partout)
      "react/jsx-uses-react": "off",
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "react/jsx-key": "warn",
      "react/no-unknown-property": "warn",

      // Hooks: ce sont les règles qui sauvent le plus
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",

      // HMR Vite
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },

  // Tests Vitest
  {
    files: ["**/*.{test,spec}.{js,jsx}", "**/__tests__/**"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
];
