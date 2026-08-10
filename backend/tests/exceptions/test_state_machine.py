import pytest

from yitu.identity.models import Role
from yitu.platform.errors import AppError


def test_exception_state_machine_supports_the_complete_processing_flow() -> None:
    from yitu.exceptions.enums import ExceptionStatus
    from yitu.exceptions.state_machine import transition

    assert transition(ExceptionStatus.OPEN, "assign") is ExceptionStatus.ASSIGNED
    assert transition(ExceptionStatus.ASSIGNED, "start_processing") is ExceptionStatus.PROCESSING
    assert (
        transition(ExceptionStatus.PROCESSING, "wait_for_customer")
        is ExceptionStatus.WAITING_FOR_CUSTOMER
    )
    assert (
        transition(ExceptionStatus.WAITING_FOR_CUSTOMER, "resume_processing")
        is ExceptionStatus.PROCESSING
    )
    assert transition(ExceptionStatus.PROCESSING, "resolve") is ExceptionStatus.RESOLVED
    assert (
        transition(ExceptionStatus.WAITING_FOR_CUSTOMER, "resolve")
        is ExceptionStatus.RESOLVED
    )
    assert transition(ExceptionStatus.RESOLVED, "close") is ExceptionStatus.CLOSED


@pytest.mark.parametrize(
    ("status", "action"),
    [
        ("OPEN", "resolve"),
        ("RESOLVED", "start_processing"),
        ("CLOSED", "assign"),
    ],
)
def test_exception_state_machine_rejects_invalid_actions(
    status: str, action: str
) -> None:
    from yitu.exceptions.enums import ExceptionStatus
    from yitu.exceptions.state_machine import transition

    with pytest.raises(AppError) as captured:
        transition(ExceptionStatus(status), action)

    assert captured.value.code == "INVALID_EXCEPTION_TRANSITION"
    assert captured.value.status_code == 409


def test_default_exception_policies_match_the_approved_business_rules() -> None:
    from yitu.exceptions.enums import ExceptionSeverity, ExceptionType
    from yitu.exceptions.state_machine import default_policy

    expected = {
        ExceptionType.PICKUP_FAILED: (ExceptionSeverity.MEDIUM, False),
        ExceptionType.ADDRESS_ERROR: (ExceptionSeverity.MEDIUM, True),
        ExceptionType.RECIPIENT_UNREACHABLE: (ExceptionSeverity.MEDIUM, False),
        ExceptionType.REFUSED: (ExceptionSeverity.HIGH, False),
        ExceptionType.DAMAGE: (ExceptionSeverity.HIGH, False),
        ExceptionType.WEIGHT_MISMATCH: (ExceptionSeverity.MEDIUM, False),
        ExceptionType.STATION_DELAY: (ExceptionSeverity.HIGH, False),
        ExceptionType.SUSPECTED_LOSS: (ExceptionSeverity.CRITICAL, True),
        ExceptionType.WAITING_FOR_SUPPLEMENT: (ExceptionSeverity.MEDIUM, True),
    }

    assert {
        case_type: (default_policy(case_type).severity, default_policy(case_type).blocks_fulfillment)
        for case_type in ExceptionType
    } == expected


def test_reportable_exception_types_are_limited_by_role() -> None:
    from yitu.exceptions.enums import ExceptionType
    from yitu.exceptions.state_machine import reportable_types

    assert reportable_types(Role.CUSTOMER) == frozenset(
        {
            ExceptionType.ADDRESS_ERROR,
            ExceptionType.RECIPIENT_UNREACHABLE,
            ExceptionType.REFUSED,
            ExceptionType.DAMAGE,
            ExceptionType.SUSPECTED_LOSS,
        }
    )
    assert reportable_types(Role.COURIER) == frozenset(
        {
            ExceptionType.PICKUP_FAILED,
            ExceptionType.ADDRESS_ERROR,
            ExceptionType.RECIPIENT_UNREACHABLE,
            ExceptionType.REFUSED,
            ExceptionType.DAMAGE,
            ExceptionType.WEIGHT_MISMATCH,
            ExceptionType.SUSPECTED_LOSS,
        }
    )
    assert reportable_types(Role.STATION_OPERATOR) == frozenset(
        set(ExceptionType) - {ExceptionType.WAITING_FOR_SUPPLEMENT}
    )
    assert reportable_types(Role.OPERATIONS_ADMIN) == frozenset(ExceptionType)
    assert reportable_types(Role.SYSTEM_ADMIN) == frozenset()


def test_task_six_recovery_resolutions_are_not_executable_in_task_five() -> None:
    from yitu.exceptions.enums import ResolutionCode
    from yitu.exceptions.state_machine import resolution_is_executable

    assert resolution_is_executable(ResolutionCode.INFORMATION_CORRECTED) is True
    assert resolution_is_executable(ResolutionCode.NO_FURTHER_ACTION) is True
    assert resolution_is_executable(ResolutionCode.CANCEL_SHIPMENT) is False
    assert resolution_is_executable(ResolutionCode.INTERCEPT_SHIPMENT) is False
    assert resolution_is_executable(ResolutionCode.REDELIVER) is False
    assert resolution_is_executable(ResolutionCode.CONVERT_TO_PICKUP) is False
    assert resolution_is_executable(ResolutionCode.RETURN_SHIPMENT) is False
