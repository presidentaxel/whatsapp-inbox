#!/usr/bin/env node
/**
 * Reproduit localement les vérifications bloquantes des jobs
 * test-backend et test-frontend du workflow GitHub Actions
 * (dont pytest sur backend/tests).
 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const python = process.env.PYTHON || "python";

function run(cmd, args, cwd, env) {
  const rel = path.relative(root, cwd) || ".";
  const shown = args?.length ? `${cmd} ${args.join(" ")}` : cmd;
  console.log(`\n\x1b[1m→ ${shown}\x1b[0m (cwd: ${rel})\n`);
  const r = spawnSync(cmd, args ?? [], {
    cwd,
    stdio: "inherit",
    shell: false,
    env: env ? { ...process.env, ...env } : process.env,
  });
  if (r.status !== 0) {
    process.exit(r.status ?? 1);
  }
}

const backend = path.join(root, "backend");
const frontend = path.join(root, "frontend");

run(python, ["-m", "pip", "install", "-r", "requirements.txt"], backend);
run(python, ["-m", "pip", "install", "ruff"], backend);
run(python, ["-m", "py_compile", "app/main.py"], backend);
run(
  python,
  [
    "-c",
    "import pathlib, py_compile; [py_compile.compile(str(p), doraise=True) for p in pathlib.Path('app').rglob('*.py')]",
  ],
  backend,
);
run(python, ["-m", "ruff", "check", "app"], backend);

const pytestEnv = {
  SUPABASE_URL: "https://mock.supabase.co",
  SUPABASE_KEY: "mock_key_123456789012345678901234567890",
  WHATSAPP_TOKEN: "mock_token",
  WHATSAPP_VERIFY_TOKEN: "mock_verify_token",
  WHATSAPP_PHONE_ID: "mock_phone_id",
  WHATSAPP_PHONE_NUMBER: "+1234567890",
  GEMINI_API_KEY: "mock_gemini_key",
  APP_ENV: "test",
};
run(python, ["-m", "pytest", "tests/", "-q", "--tb=short"], backend, pytestEnv);

run("npm", ["ci"], frontend);
run("npm", ["run", "lint:ci"], frontend);
run("npm", ["run", "build:ci"], frontend);
run("npm", ["run", "test:ci"], frontend);

console.log("\n\x1b[1m✔ Vérifications locales (backend + frontend) terminées.\x1b[0m\n");
