from uuid import uuid4

import pytest

from yitu.dispatch.models import CourierTask
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.shipments.schemas import ReweighCommand

pytestmark = pytest.mark.asyncio(loop_scope="function")


class StubSession:
    def __init__(self, task: CourierTask) -> None:
        self.task = task
        self.committed = False

    async def get(self, _model: object, resource_id: object) -> CourierTask | None:
        return self.task if resource_id == self.task.id else None

    async def commit(self) -> None:
        self.committed = True


async def test_reweigh_accepts_pickup_task_loaded_as_string(monkeypatch: pytest.MonkeyPatch) -> None:
    from yitu.dispatch.router import confirm_pickup_with_reweigh

    courier_id = uuid4()
    task = CourierTask(
        id=uuid4(),
        shipment_id=uuid4(),
        station_id=uuid4(),
        task_type="PICKUP",
        status="ACCEPTED",
        assignee_id=courier_id,
    )
    session = StubSession(task)
    reweighed = False
    confirmed = False

    async def reweigh(*_args: object, **_kwargs: object) -> None:
        nonlocal reweighed
        reweighed = True

    async def confirm(*_args: object, **_kwargs: object) -> None:
        nonlocal confirmed
        confirmed = True

    monkeypatch.setattr("yitu.dispatch.router.ShipmentApplicationService.reweigh", reweigh)
    monkeypatch.setattr("yitu.dispatch.router.DispatchService.confirm_pickup", confirm)

    await confirm_pickup_with_reweigh(
        task.id,
        ReweighCommand(
            actual_weight_grams=1000,
            actual_length_cm=30,
            actual_width_cm=20,
            actual_height_cm=20,
        ),
        CurrentUser(id=courier_id, role=Role.COURIER, station_id=task.station_id),
        session,  # type: ignore[arg-type]
    )

    assert reweighed
    assert confirmed
    assert session.committed
