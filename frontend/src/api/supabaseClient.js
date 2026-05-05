import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  const missing = [
    !supabaseUrl && "VITE_SUPABASE_URL",
    !supabaseAnonKey && "VITE_SUPABASE_ANON_KEY",
  ].filter(Boolean);
  throw new Error(
    `[supabase] Variables manquantes : ${missing.join(", ")}. Copier frontend/.env.example vers .env.local.`
  );
}

export const supabaseClient = createClient(supabaseUrl, supabaseAnonKey, {
  realtime: {
    params: { eventsPerSecond: 20 },
    heartbeatIntervalMs: 15000,
    reconnectAfterMs: (tries) => Math.min(1000 * 2 ** tries, 30000),
  },
});

