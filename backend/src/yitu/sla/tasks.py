"""定期扫描 SLA 超时实例的后台任务。"""

from yitu.platform.database import SessionFactory
from yitu.sla.service import SLAService
from yitu.worker import celery_app, run_async


@celery_app.task(name="yitu.scan_sla_breaches")  # type: ignore[untyped-decorator]
def scan_sla_breaches(scan_key: str) -> int:
    """扫描一个窗口内的超时 SLA，返回首次标记的数量。"""
    return run_async(_scan_sla_breaches(scan_key))


async def _scan_sla_breaches(scan_key: str) -> int:
    async with SessionFactory() as session, session.begin():
        return len(await SLAService(session).scan_breaches(scan_key))
