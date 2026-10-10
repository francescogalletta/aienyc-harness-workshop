-- Layer 3: answers with evidence (SPEC 5.3). Applied on every connect while layer 3 is on.

CREATE TABLE IF NOT EXISTS inputs (   -- what the person has told the harness, kept between sessions
    name        TEXT PRIMARY KEY,
    value       TEXT NOT NULL,        -- JSON
    note        TEXT NOT NULL,
    ts          TEXT NOT NULL,
    session_id  TEXT NOT NULL
);
