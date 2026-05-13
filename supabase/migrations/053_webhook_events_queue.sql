-- File durable des webhooks WhatsApp entrants.
--
-- Pourquoi : avant cette table, le endpoint /webhook/whatsapp lançait
-- `asyncio.create_task(handle_incoming_message(...))` puis renvoyait 200 OK.
-- En cas de redémarrage du process (crash, déploiement, OOM...) entre la
-- réponse et la fin du traitement, l'évènement Meta était PERDU - Meta
-- considère le webhook livré et ne réessaie plus.
--
-- Avec cette table : le endpoint INSERT le payload et répond 200 OK
-- immédiatement. Un worker périodique consomme les lignes en `pending` /
-- `failed` (avec back-off), les passe à `processing` (via `FOR UPDATE SKIP LOCKED`
-- pour permettre plusieurs workers), puis `done` ou `failed`.
--
-- Avantage bonus : audit complet (rejouable, observable) et idempotence via
-- `signature_id` (déduplication des retries Meta).

create table if not exists webhook_events (
    id              uuid primary key default gen_random_uuid(),
    -- Identifiant déduit du payload Meta (premier message id ou hash du body)
    -- pour ignorer les retries Meta sans retraiter.
    signature_id    text unique,
    source          text not null default 'whatsapp',
    -- Body brut tel que reçu (utile pour rejouer / debug forensic).
    payload         jsonb not null,
    -- "pending" → "processing" → "done" | "failed"
    status          text not null default 'pending'
                       check (status in ('pending', 'processing', 'done', 'failed')),
    attempts        int not null default 0,
    max_attempts    int not null default 5,
    last_error      text,
    -- Lock distribué simple (qui traite, depuis quand)
    locked_by       text,
    locked_at       timestamptz,
    -- Quand on peut retenter (back-off exponentiel posé par le worker)
    next_attempt_at timestamptz not null default now(),
    received_at     timestamptz not null default now(),
    processed_at    timestamptz
);

-- Worker poll : “ce qui est prêt à traiter”.
create index if not exists idx_webhook_events_ready
    on webhook_events (status, next_attempt_at)
    where status in ('pending', 'failed');

-- Détection des locks orphelins (worker mort en cours de traitement).
create index if not exists idx_webhook_events_processing
    on webhook_events (locked_at)
    where status = 'processing';

-- Cleanup / observabilité.
create index if not exists idx_webhook_events_received_at
    on webhook_events (received_at desc);

comment on table webhook_events is
    'File durable des webhooks WhatsApp. Évite la perte d''évènements lors d''un crash entre 200 OK et fin de traitement.';
comment on column webhook_events.signature_id is
    'Empreinte stable du payload (ex: premier message.id Meta ou sha256 du body). UNIQUE pour dédupliquer les retries Meta.';
comment on column webhook_events.locked_by is
    'Identifiant du worker (hostname:pid) qui traite la ligne. Permet de récupérer les locks orphelins.';
