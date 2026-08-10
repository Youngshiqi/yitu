from collections.abc import Mapping

from yitu.platform.errors import AppError
from yitu.shipments.enums import ShipmentStatus

_TRANSITIONS: Mapping[ShipmentStatus, frozenset[ShipmentStatus]] = {
    ShipmentStatus.PENDING_PAYMENT: frozenset({ShipmentStatus.PENDING_PICKUP, ShipmentStatus.WAITING_FOR_DROPOFF, ShipmentStatus.CANCELLED}),
    ShipmentStatus.PENDING_PICKUP: frozenset({ShipmentStatus.PICKUP_ASSIGNED, ShipmentStatus.CANCELLED}),
    ShipmentStatus.PICKUP_ASSIGNED: frozenset({ShipmentStatus.PICKED_UP}),
    ShipmentStatus.WAITING_FOR_DROPOFF: frozenset({ShipmentStatus.AT_ORIGIN_STATION, ShipmentStatus.CANCELLED}),
    ShipmentStatus.PICKED_UP: frozenset({ShipmentStatus.AT_ORIGIN_STATION}),
    ShipmentStatus.AT_ORIGIN_STATION: frozenset({ShipmentStatus.IN_LINEHAUL}),
    ShipmentStatus.IN_LINEHAUL: frozenset({ShipmentStatus.AT_DESTINATION_STATION}),
    ShipmentStatus.AT_DESTINATION_STATION: frozenset({ShipmentStatus.DELIVERY_ASSIGNED, ShipmentStatus.WAITING_FOR_RECIPIENT_PICKUP}),
    ShipmentStatus.DELIVERY_ASSIGNED: frozenset({ShipmentStatus.OUT_FOR_DELIVERY}),
    ShipmentStatus.OUT_FOR_DELIVERY: frozenset({ShipmentStatus.DELIVERED}),
    ShipmentStatus.WAITING_FOR_RECIPIENT_PICKUP: frozenset({ShipmentStatus.DELIVERED}),
    ShipmentStatus.DELIVERED: frozenset(),
    ShipmentStatus.CANCELLED: frozenset(),
}

_ACTIONS: Mapping[ShipmentStatus, frozenset[str]] = {
    ShipmentStatus.PENDING_PAYMENT: frozenset({"confirm_payment", "cancel"}),
    ShipmentStatus.PENDING_PICKUP: frozenset({"assign_pickup", "cancel"}),
    ShipmentStatus.PICKUP_ASSIGNED: frozenset({"confirm_pickup"}),
    ShipmentStatus.WAITING_FOR_DROPOFF: frozenset({"confirm_origin_arrival", "cancel"}),
    ShipmentStatus.PICKED_UP: frozenset({"confirm_origin_arrival"}),
    ShipmentStatus.AT_ORIGIN_STATION: frozenset({"dispatch_linehaul"}),
    ShipmentStatus.IN_LINEHAUL: frozenset({"arrive_destination"}),
    ShipmentStatus.AT_DESTINATION_STATION: frozenset({"assign_delivery", "issue_pickup_credential"}),
    ShipmentStatus.DELIVERY_ASSIGNED: frozenset({"start_delivery"}),
    ShipmentStatus.OUT_FOR_DELIVERY: frozenset({"confirm_delivery"}),
    ShipmentStatus.WAITING_FOR_RECIPIENT_PICKUP: frozenset({"verify_station_pickup"}),
    ShipmentStatus.DELIVERED: frozenset(),
    ShipmentStatus.CANCELLED: frozenset(),
}


def transition(current: ShipmentStatus, target: ShipmentStatus) -> ShipmentStatus:
    """校验并返回下一状态，拒绝跳过必要履约节点。"""
    if target not in _TRANSITIONS[current]:
        raise AppError("INVALID_SHIPMENT_TRANSITION", "不允许该运单状态跳转", 409)
    return target


def allowed_actions(status: ShipmentStatus) -> frozenset[str]:
    """返回当前状态可执行的业务动作名称。"""
    return _ACTIONS[status]
