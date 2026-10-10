CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,      -- UTC, ISO 8601
    session_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,      -- dotted name, e.g. "harness.check"
    actor       TEXT NOT NULL,      -- "harness" | "agent" | "person"
    payload     TEXT NOT NULL       -- JSON object
);

-- events is append-only: a record that can be edited afterwards is not evidence.
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events is append-only');
END;

CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events is append-only');
END;
