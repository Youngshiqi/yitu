"""异常工单生命周期中的稳定枚举。"""

import enum


class ExceptionType(str, enum.Enum):
    """阶段三任务五支持的异常类型。"""

    PICKUP_FAILED = "PICKUP_FAILED"
    ADDRESS_ERROR = "ADDRESS_ERROR"
    RECIPIENT_UNREACHABLE = "RECIPIENT_UNREACHABLE"
    REFUSED = "REFUSED"
    DAMAGE = "DAMAGE"
    WEIGHT_MISMATCH = "WEIGHT_MISMATCH"
    STATION_DELAY = "STATION_DELAY"
    SUSPECTED_LOSS = "SUSPECTED_LOSS"
    WAITING_FOR_SUPPLEMENT = "WAITING_FOR_SUPPLEMENT"


class ExceptionSeverity(str, enum.Enum):
    """异常默认严重度。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExceptionStatus(str, enum.Enum):
    """异常工单处理状态。"""

    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    PROCESSING = "PROCESSING"
    WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class ExceptionSourceType(str, enum.Enum):
    """异常来源类型。"""

    MANUAL = "MANUAL"
    SLA_SCAN = "SLA_SCAN"


class ResolutionCode(str, enum.Enum):
    """异常解决结果。

    任务五只执行信息修正和无需后续动作；其余恢复动作留给任务六。
    """

    INFORMATION_CORRECTED = "INFORMATION_CORRECTED"
    NO_FURTHER_ACTION = "NO_FURTHER_ACTION"
    CANCEL_SHIPMENT = "CANCEL_SHIPMENT"
    INTERCEPT_SHIPMENT = "INTERCEPT_SHIPMENT"
    REDELIVER = "REDELIVER"
    CONVERT_TO_PICKUP = "CONVERT_TO_PICKUP"
    RETURN_SHIPMENT = "RETURN_SHIPMENT"

