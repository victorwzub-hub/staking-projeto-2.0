from pharma_api.infrastructure.email.tasks import deliver_email, system_ping
from pharma_api.infrastructure.messaging.broker import configure_broker

broker = configure_broker()

__all__ = ["broker", "deliver_email", "system_ping"]
