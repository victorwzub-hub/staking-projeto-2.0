from pharma_worker.tasks import system_ping


def test_system_ping_actor_function() -> None:
    assert system_ping.fn("ready") == "ready"
