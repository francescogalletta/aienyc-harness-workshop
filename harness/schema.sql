-- Layer 0: the core's tables (SPEC 2.2). Applied on every connect; no migration history.
-- After a change here, delete my/var/harness.db.

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,      -- UTC, ISO 8601
    session_id  TEXT NOT NULL,      -- the conversation, or the command that recorded it
    kind        TEXT NOT NULL,      -- dotted name with the layer's prefix, e.g. "core.message"
    actor       TEXT NOT NULL,      -- "harness" | "agent" | "person"
    payload     TEXT NOT NULL       -- JSON object
);

-- events is append-only: a record that can be edited afterwards is not evidence.
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events is append-only');
END;

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,        -- "conversation": the current conversation id
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,    -- shown as "m<id>"
    ts            TEXT NOT NULL,
    conversation  TEXT NOT NULL,
    thread        INTEGER,                              -- NULL: the main chat
    who           TEXT NOT NULL,                        -- "you" | "assistant" | "harness" | "reviewer"
    text          TEXT NOT NULL,
    step          TEXT,                                 -- the step it is about
    kind          TEXT NOT NULL,                        -- "text" | "plan" | "decision" | "notice" | "withheld"
    data          TEXT NOT NULL DEFAULT '{}'            -- JSON object: the keys layers add
);

CREATE TABLE IF NOT EXISTS threads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,    -- shown as "t<id>"
    ts            TEXT NOT NULL,
    conversation  TEXT NOT NULL,
    kind          TEXT NOT NULL,                        -- "side" | "review" | "harness"
    step          TEXT,
    after         INTEGER,                              -- the main-chat message it follows; NULL: none yet
    title         TEXT NOT NULL,
    status        TEXT NOT NULL,                        -- "open" | "used" | "dismissed"
    -- a thread is a branch (ARCHITECTURE.md 3.5, 12.8)
    origin        TEXT NOT NULL DEFAULT 'you',          -- "you" | "assistant" | "reviewer" | "harness"
    subject       TEXT NOT NULL DEFAULT '{"kind": "plan"}',   -- JSON Subject
    from_node     INTEGER,                              -- trunk.id it left from; NULL before any node
    outcome       TEXT NOT NULL DEFAULT 'open',         -- "open" | "joined" | "dead"
    node          INTEGER                               -- trunk.id it joined as
);

-- The trunk: the decisions of a conversation that changed the analysis (ARCHITECTURE.md 12.1).
CREATE TABLE IF NOT EXISTS trunk (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,    -- shown as "n<id>"
    ts            TEXT NOT NULL,
    conversation  TEXT NOT NULL,
    who           TEXT NOT NULL,                        -- "you" | "assistant" | "harness" | "reviewer"
    kind          TEXT NOT NULL,
    text          TEXT NOT NULL,
    change        TEXT NOT NULL DEFAULT '{}',           -- JSON Change
    touched       TEXT NOT NULL DEFAULT '{"inputs": [], "steps": []}',
    thread        INTEGER,                              -- the branch it joined from
    after         INTEGER                               -- the main-chat message it follows
);
