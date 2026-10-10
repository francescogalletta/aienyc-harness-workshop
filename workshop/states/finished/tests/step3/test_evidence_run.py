"""SPEC 7.4: `GET /api/work/run?id=N`, one calculation run and the test run it relied on."""


from step3_evidence_helpers import RUN_KEYS


def get(api, run_id):
    return api.get(f"/api/work/run?id={run_id}")


def row_of(world, run_id):
    return world.sql("SELECT * FROM calc_runs WHERE id = ?", (run_id,))[0]


def test_the_keys_of_a_run(api):
    status, body = get(api, 1)
    assert status == 200 and set(RUN_KEYS) <= set(body)


# ---- errors ---------------------------------------------------------------------------------------------------------------------
