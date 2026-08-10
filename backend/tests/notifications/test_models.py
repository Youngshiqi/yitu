from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from yitu.notifications.models import NotificationDelivery, NotificationMessage


def test_delivery_has_event_recipient_channel_idempotency_constraint() -> None:
    constraints = [
        item
        for item in NotificationDelivery.__table__.constraints
        if isinstance(item, UniqueConstraint)
    ]
    assert any(
        constraint.name == "uq_notification_deliveries_event_recipient_channel"
        and tuple(column.name for column in constraint.columns)
        == ("event_id", "recipient_id", "channel")
        for constraint in constraints
    )


def test_message_has_event_recipient_idempotency_constraint() -> None:
    assert NotificationMessage.__tablename__ == "notification_messages"
    constraints = [
        item
        for item in NotificationMessage.__table__.constraints
        if isinstance(item, UniqueConstraint)
    ]
    assert any(
        constraint.name == "uq_notification_messages_event_recipient"
        and tuple(column.name for column in constraint.columns)
        == ("event_id", "recipient_id")
        for constraint in constraints
    )


def test_notification_event_ids_reference_outbox_events() -> None:
    foreign_keys = [
        item
        for table in (NotificationMessage.__table__, NotificationDelivery.__table__)
        for item in table.constraints
        if isinstance(item, ForeignKeyConstraint)
    ]
    assert sum(
        tuple(element.parent.name for element in constraint.elements) == ("event_id",)
        and tuple(element.column.table.name for element in constraint.elements)
        == ("outbox_events",)
        for constraint in foreign_keys
    ) == 2
