import enum


class ShipmentStatus(str, enum.Enum):
    """运单在创建阶段使用的状态枚举。"""

    PENDING_PAYMENT = "PENDING_PAYMENT"
    PENDING_PICKUP = "PENDING_PICKUP"
    WAITING_FOR_DROPOFF = "WAITING_FOR_DROPOFF"


class PickupMethod(str, enum.Enum):
    """寄件端的交付方式。"""

    DOOR_PICKUP = "DOOR_PICKUP"
    STATION_DROPOFF = "STATION_DROPOFF"


class DeliveryMethod(str, enum.Enum):
    """收件端的交付方式。"""

    HOME_DELIVERY = "HOME_DELIVERY"
    STATION_PICKUP = "STATION_PICKUP"
