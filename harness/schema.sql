-- Layer 0: the base tables (SPEC 2.2). Applied on every connect; no migration history.
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
    kind          TEXT NOT NULL,                        -- "side" | "review"
    step          TEXT,
    title         TEXT NOT NULL,
    status        TEXT NOT NULL                         -- "open" | "used" | "dismissed"
);
