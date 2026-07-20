from __future__ import annotations

from unittest.mock import Mock, patch

from pharma_worker.tasks import system_ping


def test_system_ping_actor_function_returns_none_and_records_probe() -> None:
    redis_client = Mock()

    with patch(
        "pharma_api.infrastructure.email.tasks.Redis.from_url",
        return_value=redis_client,
    ):
        result = system_ping.fn("ready")

    assert result is None
    redis_client.set.assert_called_once_with("worker:probe:ready", "ok", ex=300)
    redis_client.close.assert_called_once_with()
