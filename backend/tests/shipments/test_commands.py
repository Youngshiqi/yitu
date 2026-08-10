from uuid import uuid4

import pytest
from pydantic import ValidationError

from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus
from yitu.shipments.schemas import CreateShipmentCommand, ShipmentDraft


@pytest.mark.parametrize(
    ("pickup", "delivery"),
    [
        (PickupMethod.DOOR_PICKUP, DeliveryMethod.HOME_DELIVERY),
        (PickupMethod.DOOR_PICKUP, DeliveryMethod.STATION_PICKUP),
        (PickupMethod.STATION_DROPOFF, DeliveryMethod.HOME_DELIVERY),
        (PickupMethod.STATION_DROPOFF, DeliveryMethod.STATION_PICKUP),
    ],
)
def test_four_shipment_combinations_are_valid(
    pickup: PickupMethod, delivery: DeliveryMethod
) -> None:
    draft = ShipmentDraft(
        sender_address_id=uuid4() if pickup is PickupMethod.DOOR_PICKUP else None,
        receiver_address_id=uuid4() if delivery is DeliveryMethod.HOME_DELIVERY else None,
        origin_station_id=uuid4() if pickup is PickupMethod.STATION_DROPOFF else None,
        destination_station_id=uuid4() if delivery is DeliveryMethod.STATION_PICKUP else None,
        pickup_method=pickup,
        delivery_method=delivery,
    )
    command = CreateShipmentCommand(draft=draft)
    assert command.draft.pickup_method is pickup
    assert command.status is ShipmentStatus.PENDING_PAYMENT


def test_missing_required_address_or_station_is_rejected() -> None:
    with pytest.raises(ValidationError, match="sender_address_id"):
        ShipmentDraft(pickup_method=PickupMethod.DOOR_PICKUP, delivery_method=DeliveryMethod.HOME_DELIVERY, receiver_address_id=uuid4())
    with pytest.raises(ValidationError, match="destination_station_id"):
        ShipmentDraft(pickup_method=PickupMethod.STATION_DROPOFF, delivery_method=DeliveryMethod.STATION_PICKUP, origin_station_id=uuid4())


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ShipmentDraft(pickup_method=PickupMethod.DOOR_PICKUP, delivery_method=DeliveryMethod.HOME_DELIVERY, sender_address_id=uuid4(), receiver_address_id=uuid4(), debug=True)
