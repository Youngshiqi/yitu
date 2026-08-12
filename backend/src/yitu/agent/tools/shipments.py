"""本人运单、轨迹、费用和 ETA 只读工具。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from yitu.agent.tools.base import ToolContext, ToolResult
from yitu.shipments.service import ShipmentApplicationService


class ShipmentReadInput(BaseModel):
    """允许按运单号查询；为空时返回当前客户最近一票运单。"""

    model_config = ConfigDict(extra="forbid")

    shipment_no: str | None = Field(default=None, max_length=32)


class TrackingSummary(BaseModel):
    """面向模型的最小轨迹字段。"""

    model_config = ConfigDict(extra="forbid")

    sequence_no: int
    event_type: str
    message: str
    occurred_at: datetime


class ShipmentReadResult(BaseModel):
    """不含地址、姓名和电话的本人运单聚合。"""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    shipment_no: str
    status: str
    paid_total_cents: int
    eta_at: datetime | None
    promised_delivery_at: datetime | None
    tracking: list[TrackingSummary]


class ShipmentReadTool:
    """调用运单应用服务，模型无法通过输入覆盖当前用户身份。"""

    async def execute(
        self,
        request: ShipmentReadInput,
        context: ToolContext,
    ) -> ToolResult[ShipmentReadResult]:
        view = await ShipmentApplicationService(context.session).get_read_view(
            context.actor,
            shipment_no=request.shipment_no,
        )
        if view is None:
            return ToolResult(
                tool="shipment_read",
                found=False,
                data=None,
                message="没有找到当前客户有权访问的运单。",
            )
        shipment = view.shipment
        return ToolResult(
            tool="shipment_read",
            found=True,
            data=ShipmentReadResult(
                id=shipment.id,
                shipment_no=shipment.shipment_no,
                status=shipment.status.value,
                paid_total_cents=view.paid_total_cents,
                eta_at=view.eta_at,
                promised_delivery_at=view.promised_delivery_at,
                tracking=[
                    TrackingSummary(
                        sequence_no=event.sequence_no,
                        event_type=event.event_type,
                        message=event.message,
                        occurred_at=event.occurred_at,
                    )
                    for event in view.tracking
                ],
            ),
            message="已读取当前客户的运单信息。",
        )
