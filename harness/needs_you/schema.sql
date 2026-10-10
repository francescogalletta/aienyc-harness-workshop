-- Layer 4: when the harness needs the person (SPEC 6). Applied on every connect while layer 4 is on.

CREATE TABLE IF NOT EXISTS assumptions (   -- what a run took as given without the person's word (SPEC 6.1)
    id      INTEGER PRIMARY KEY AUTOINCREMENT,   -- shown as "a<id>"
    key     TEXT NOT NULL UNIQUE,                -- the sentence on one line, case-folded
    text    TEXT NOT NULL,                       -- the sentence on one line, as first written
    status  TEXT NOT NULL,                       -- "unconfirmed" | "confirmed" | "corrected"
    words   TEXT NOT NULL DEFAULT '',            -- the person's words when corrected
    ts      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_assumptions (
    run_id        INTEGER NOT NULL REFERENCES calc_runs(id),
    assumption_id INTEGER NOT NULL REFERENCES assumptions(id),
    PRIMARY KEY (run_id, assumption_id)
);

CREATE TABLE IF NOT EXISTS decisions (   -- calls that are the person's (SPEC 6.2)
    id           INTEGER PRIMARY KEY AUTOINCREMENT,   -- shown as "d<id>"
    ts           TEXT NOT NULL,
    conversation TEXT NOT NULL,
    step_id      TEXT NOT NULL,
    question     TEXT NOT NULL,
    options      TEXT NOT NULL,          -- JSON list of sentences
    suggested    INTEGER,                -- the number of the suggested option, or NULL
    why          TEXT NOT NULL,
    choice       TEXT,                   -- "2" or "something else"; NULL until answered
    words        TEXT NOT NULL DEFAULT '',   -- the person's words, or the option's text
    runs         TEXT NOT NULL,          -- JSON list of calc_runs ids it rests on
    message      TEXT,                   -- the decision message in the chat
    status       TEXT NOT NULL DEFAULT 'open'   -- "open" | "answered" | "dropped" (its process ended unanswered)
);
