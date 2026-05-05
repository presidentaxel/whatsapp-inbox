/**
 * WhatsApp / Meta Cloud API webhook - Edge ingress.
 *
 * - GET  : challenge Meta (hub.verify_token) - global WHATSAPP_VERIFY_TOKEN et/ou whatsapp_accounts.verify_token
 * - POST : vérifie X-Hub-Signature-256, INSERT dans webhook_events (même logique que le backend FastAPI)
 *
 * Secrets à définir sur le projet (les noms `SUPABASE_*` sont réservés - ne pas les passer à `secrets set`) :
 *   npx supabase secrets set META_APP_SECRET=... WHATSAPP_VERIFY_TOKEN=...
 * Clé admin DB : `SUPABASE_SERVICE_ROLE_KEY` ou `SUPABASE_SECRET_KEYS` est injecté(e) par la plateforme ; idem `SUPABASE_URL`.
 */
import "@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

function timingSafeEqualStr(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function hmacSha256Hex(secret: string, body: Uint8Array): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, body);
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function sortKeysDeep(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(sortKeysDeep);
  const obj = value as Record<string, unknown>;
  const sorted: Record<string, unknown> = {};
  for (const k of Object.keys(obj).sort()) sorted[k] = sortKeysDeep(obj[k]);
  return sorted;
}

/** Aligné sur `webhook_event_service._compute_signature_id` (Python). */
async function computeSignatureIdAsync(payload: Record<string, unknown>): Promise<string> {
  const ids: string[] = [];
  try {
    const entries = (payload.entry as unknown[]) ?? [];
    for (const entry of entries) {
      if (!entry || typeof entry !== "object") continue;
      const changes = ((entry as Record<string, unknown>).changes as unknown[]) ?? [];
      for (const change of changes) {
        if (!change || typeof change !== "object") continue;
        const value = ((change as Record<string, unknown>).value as Record<string, unknown>) ?? {};
        for (const m of (value.messages as unknown[]) ?? []) {
          if (m && typeof m === "object" && (m as Record<string, unknown>).id) {
            ids.push(`m:${(m as Record<string, unknown>).id as string}`);
          }
        }
        for (const s of (value.statuses as unknown[]) ?? []) {
          if (s && typeof s === "object") {
            const o = s as Record<string, unknown>;
            if (o.id) ids.push(`s:${o.id}:${String(o.status ?? "")}`);
          }
        }
      }
    }
  } catch {
    /* ignore */
  }
  if (ids.length) return ids.sort().join("|").slice(0, 512);
  const canonical = JSON.stringify(sortKeysDeep(payload), null, 0);
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
  const hex = [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `sha256:${hex}`;
}

function getServiceRoleKey(): string | undefined {
  const legacy = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (legacy) return legacy;
  const secretsJson = Deno.env.get("SUPABASE_SECRET_KEYS");
  if (!secretsJson) return undefined;
  try {
    const parsed = JSON.parse(secretsJson) as Record<string, string>;
    return parsed.default ?? parsed["default"];
  } catch {
    return undefined;
  }
}

function getSupabaseAdmin() {
  const url = Deno.env.get("SUPABASE_URL");
  const key = getServiceRoleKey();
  if (!url || !key) throw new Error("missing_supabase_env");
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

async function verifyGetChallenge(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const mode = url.searchParams.get("hub.mode");
  const token = url.searchParams.get("hub.verify_token");
  const challenge = url.searchParams.get("hub.challenge") ?? "";

  if (mode !== "subscribe" || !token) {
    return new Response("forbidden", { status: 403 });
  }

  const globalToken = Deno.env.get("WHATSAPP_VERIFY_TOKEN");
  if (globalToken && timingSafeEqualStr(token, globalToken)) {
    return new Response(challenge, { status: 200, headers: { "Content-Type": "text/plain" } });
  }

  try {
    const supabase = getSupabaseAdmin();
    const { data, error } = await supabase
      .from("whatsapp_accounts")
      .select("id")
      .eq("verify_token", token)
      .maybeSingle();
    if (!error && data?.id) {
      return new Response(challenge, { status: 200, headers: { "Content-Type": "text/plain" } });
    }
  } catch {
    /* fallthrough */
  }

  return new Response("forbidden", { status: 403 });
}

async function handlePost(req: Request): Promise<Response> {
  const raw = new Uint8Array(await req.arrayBuffer());
  const secret = Deno.env.get("META_APP_SECRET");
  const signatureRequired = Deno.env.get("WEBHOOK_SIGNATURE_REQUIRED") !== "false";

  if (!secret) {
    if (signatureRequired) {
      return new Response(JSON.stringify({ detail: "webhook_signature_not_configured" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
    // Dev only : pas de META_APP_SECRET
  } else {
    const received =
      req.headers.get("X-Hub-Signature-256")?.trim() ??
      req.headers.get("x-hub-signature-256")?.trim() ??
      "";
    if (!received) {
      return new Response(JSON.stringify({ detail: "missing_signature" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
    const expected = "sha256=" + await hmacSha256Hex(secret, raw);
    if (!timingSafeEqualStr(received, expected)) {
      return new Response(JSON.stringify({ detail: "invalid_signature" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
  }

  let data: Record<string, unknown>;
  try {
    const text = raw.length ? new TextDecoder().decode(raw) : "{}";
    data = JSON.parse(text) as Record<string, unknown>;
  } catch {
    return new Response(JSON.stringify({ detail: "invalid_json" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const signatureId = await computeSignatureIdAsync(data);
  const supabase = getSupabaseAdmin();

  const { data: inserted, error: insertError } = await supabase
    .from("webhook_events")
    .insert({ signature_id: signatureId, source: "whatsapp", payload: data })
    .select("id")
    .maybeSingle();

  if (!insertError && inserted?.id) {
    return new Response(JSON.stringify({ status: "queued", event_id: inserted.id }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  const isDuplicate =
    insertError?.code === "23505" ||
    (insertError?.message?.toLowerCase().includes("duplicate") ?? false);
  if (isDuplicate) {
    const { data: existing } = await supabase
      .from("webhook_events")
      .select("id")
      .eq("signature_id", signatureId)
      .maybeSingle();
    return new Response(
      JSON.stringify({
        status: "queued",
        event_id: existing?.id ?? null,
        deduplicated: true,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }

  console.error("webhook_events insert error", insertError);
  return new Response(JSON.stringify({ detail: insertError?.message ?? "insert_failed" }), {
    status: 500,
    headers: { "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  try {
    if (req.method === "GET") return await verifyGetChallenge(req);
    if (req.method === "POST") return await handlePost(req);
    // Pas de gestion CORS spécifique : Meta n'envoie pas de preflight et
    // aucun navigateur n'est censé appeler cet endpoint. On répond sec.
    return new Response("method not allowed", {
      status: 405,
      headers: { Allow: "GET, POST" },
    });
  } catch (e) {
    console.error(e);
    return new Response(JSON.stringify({ detail: String(e) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});
