"""异常工单的纯状态机和默认策略。"""

from collections.abc import Mapping
from dataclasses import dataclass

from yitu.exceptions.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ResolutionCode,
)
from yitu.identity.models import Role
from yitu.platform.errors import AppError


@dataclass(frozen=True, slots=True)
class ExceptionPolicy:
    """服务端根据异常类型给出的默认处理策略。"""

    severity: ExceptionSeverity
    blocks_fulfillment: bool


_TRANSITIONS: Mapping[ExceptionStatus, Mapping[str, ExceptionStatus]] = {
    ExceptionStatus.OPEN: {"assign": ExceptionStatus.ASSIGNED},
    ExceptionStatus.ASSIGNED: {"start_processing": ExceptionStatus.PROCESSING},
    ExceptionStatus.PROCESSING: {
        "wait_for_customer": ExceptionStatus.WAITING_FOR_CUSTOMER,
        "resolve": ExceptionStatus.RESOLVED,
    },
    ExceptionStatus.WAITING_FOR_CUSTOMER: {
        "resume_processing": ExceptionStatus.PROCESSING,
        "resolve": ExceptionStatus.RESOLVED,
    },
    ExceptionStatus.RESOLVED: {"close": ExceptionStatus.CLOSED},
    ExceptionStatus.CLOSED: {},
}

_DEFAULT_POLICIES: Mapping[ExceptionType, ExceptionPolicy] = {
    ExceptionType.PICKUP_FAILED: ExceptionPolicy(ExceptionSeverity.MEDIUM, False),
    ExceptionType.ADDRESS_ERROR: ExceptionPolicy(ExceptionSeverity.MEDIUM, True),
    ExceptionType.RECIPIENT_UNREACHABLE: ExceptionPolicy(ExceptionSeverity.MEDIUM, False),
    ExceptionType.REFUSED: ExceptionPolicy(ExceptionSeverity.HIGH, False),
    ExceptionType.DAMAGE: ExceptionPolicy(ExceptionSeverity.HIGH, False),
    ExceptionType.WEIGHT_MISMATCH: ExceptionPolicy(ExceptionSeverity.MEDIUM, False),
    ExceptionType.STATION_DELAY: ExceptionPolicy(ExceptionSeverity.HIGH, False),
    ExceptionType.SUSPECTED_LOSS: ExceptionPolicy(ExceptionSeverity.CRITICAL, True),
    ExceptionType.WAITING_FOR_SUPPLEMENT: ExceptionPolicy(ExceptionSeverity.MEDIUM, True),
}

_REPORTABLE_TYPES: Mapping[Role, frozenset[ExceptionType]] = {
    Role.CUSTOMER: frozenset(
        {
            ExceptionType.ADDRESS_ERROR,
            ExceptionType.RECIPIENT_UNREACHABLE,
            ExceptionType.REFUSED,
            ExceptionType.DAMAGE,
            ExceptionType.SUSPECTED_LOSS,
        }
    ),
    Role.COURIER: frozenset(
        {
            ExceptionType.PICKUP_FAILED,
            ExceptionType.ADDRESS_ERROR,
            ExceptionType.RECIPIENT_UNREACHABLE,
            ExceptionType.REFUSED,
            ExceptionType.DAMAGE,
            ExceptionType.WEIGHT_MISMATCH,
            ExceptionType.SUSPECTED_LOSS,
        }
    ),
    Role.STATION_OPERATOR: frozenset(
        set(ExceptionType) - {ExceptionType.WAITING_FOR_SUPPLEMENT}
    ),
    Role.OPERATIONS_ADMIN: frozenset(ExceptionType),
    Role.SYSTEM_ADMIN: frozenset(),
}

_TASK_FIVE_EXECUTABLE_RESOLUTIONS = frozenset(
    {
        ResolutionCode.INFORMATION_CORRECTED,
        ResolutionCode.NO_FURTHER_ACTION,
    }
)


def transition(current: ExceptionStatus, action: str) -> ExceptionStatus:
    """按命名动作推进异常工单状态。"""
    target = _TRANSITIONS[current].get(action)
    if target is None:
        raise AppError(
            "INVALID_EXCEPTION_TRANSITION",
            "不允许该异常状态转换",
            409,
        )
    return target


def default_policy(case_type: ExceptionType) -> ExceptionPolicy:
    """返回异常类型的服务端默认严重度和阻断策略。"""
    return _DEFAULT_POLICIES[case_type]


def reportable_types(role: Role) -> frozenset[ExceptionType]:
    """返回指定角色允许人工上报的异常类型。"""
    return _REPORTABLE_TYPES[role]


def resolution_is_executable(resolution_code: ResolutionCode) -> bool:
    """判断解决结果是否能在任务五内直接执行。"""
    return resolution_code in _TASK_FIVE_EXECUTABLE_RESOLUTIONS
