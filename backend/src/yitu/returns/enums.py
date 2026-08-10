import enum


class RecoveryAction(str, enum.Enum):
    """任务六支持的显式恢复动作。"""

    CANCEL = "CANCEL"
    INTERCEPTION = "INTERCEPTION"
    REDELIVERY = "REDELIVERY"
    CONVERT_TO_PICKUP = "CONVERT_TO_PICKUP"
    RETURN = "RETURN"


class RecoveryStatus(str, enum.Enum):
    """恢复工单的轻量生命周期。"""

    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
