-- Relay schema, idempotent

CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    phone TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL DEFAULT '',
    attributes JSONB NOT NULL DEFAULT '{}',
    opted_out BOOLEAN NOT NULL DEFAULT FALSE,
    opted_out_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    template TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    campaign_id INTEGER REFERENCES campaigns(id),
    state TEXT NOT NULL DEFAULT 'open',
    intent TEXT,
    handoff_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    campaign_id INTEGER REFERENCES campaigns(id),
    direction TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    provider_sid TEXT,
    queued_for TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_queued ON messages(status, queued_for) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id);
CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations(contact_id, state);
