-- Step 2: calculation steps added in a conversation, not in the brief (SPEC 5.5).

CREATE TABLE added_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- the step id is 'added_<id>'
    ts          TEXT NOT NULL,        -- UTC, ISO 8601
    session_id  TEXT NOT NULL,        -- the conversation it was added in
    name        TEXT NOT NULL,        -- what it works out, in the agent's words
    formula     TEXT NOT NULL,
    needs       TEXT NOT NULL,        -- what it is worked out from, in the agent's words
    produces    TEXT NOT NULL,
    reason      TEXT NOT NULL         -- why the agent asked for it
);
