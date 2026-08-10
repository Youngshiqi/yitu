from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yitu.shipments.enums import DeliveryMethod, PickupMethod, ShipmentStatus


class ShipmentDraft(BaseModel):
    """对话或表单逐步填写的运单草稿。"""

    model_config = ConfigDict(extra="forbid")

    sender_address_id: UUID | None = None
    receiver_address_id: UUID | None = None
    origin_station_id: UUID | None = None
    destination_station_id: UUID | None = None
    pickup_method: PickupMethod
    delivery_method: DeliveryMethod

    @model_validator(mode="after")
    def validate_service_combination(self) -> "ShipmentDraft":
        """根据寄收方式校验必须提供的地址或网点。"""
        required = {
            PickupMethod.DOOR_PICKUP: ("sender_address_id", self.sender_address_id),
            PickupMethod.STATION_DROPOFF: ("origin_station_id", self.origin_station_id),
        }[self.pickup_method]
        if required[1] is None:
            raise ValueError(f"{required[0]} 为当前寄件方式必填")
        required = {
            DeliveryMethod.HOME_DELIVERY: ("receiver_address_id", self.receiver_address_id),
            DeliveryMethod.STATION_PICKUP: (
                "destination_station_id",
                self.destination_station_id,
            ),
        }[self.delivery_method]
        if required[1] is None:
            raise ValueError(f"{required[0]} 为当前收件方式必填")
        return self


class CreateShipmentCommand(BaseModel):
    """创建运单命令，仅负责输入校验，不写数据库。"""

    model_config = ConfigDict(extra="forbid")
    draft: ShipmentDraft
    status: ShipmentStatus = ShipmentStatus.PENDING_PAYMENT


class ShipmentResumeCommand(BaseModel):
    """显式恢复被冻结履约的请求。"""

    target_status: ShipmentStatus
    reason: str = Field(min_length=1, max_length=1000)


class ShipmentResumeView(BaseModel):
    """恢复履约后的稳定响应。"""

    shipment_id: UUID
    status: ShipmentStatus
    resumed_hold_count: int
