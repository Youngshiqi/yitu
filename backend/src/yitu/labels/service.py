"""电子面单投影服务。"""

import hashlib
import hmac
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.platform.config import get_settings
from yitu.platform.errors import AppError
from yitu.shipments.models import Shipment


class LabelProjection(BaseModel):
    """不含个人敏感信息的电子面单投影。"""

    shipment_id: UUID
    shipment_no: str
    code128_value: str
    qr_token: str
    qr_payload: str


class LabelService:
    """生成面单条码和二维码查询令牌，避免暴露姓名、电话和详细地址。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def project(self, shipment_id: UUID) -> LabelProjection:
        shipment = await self._session.get(Shipment, shipment_id)
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        token = _token_for_shipment(shipment.id, shipment.shipment_no)
        return LabelProjection(
            shipment_id=shipment.id,
            shipment_no=shipment.shipment_no,
            code128_value=shipment.shipment_no,
            qr_token=token,
            qr_payload=f"yitu://shipments/{shipment.shipment_no}?token={token}",
        )


def _token_for_shipment(shipment_id: UUID, shipment_no: str) -> str:
    """使用本地密钥为运单生成稳定短令牌。"""
    secret = get_settings().jwt_secret.encode("utf-8")
    message = f"{shipment_id}:{shipment_no}".encode()
    digest = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return digest[:32]
