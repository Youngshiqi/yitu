"""Prune test-created stations, keeping only BJS-001 and SHS-001.

0037 已收敛过一次网点集合，但运营/测试过程中又通过建网点接口产生了
杂散网点，它们被流水表（shipments / transport_legs / courier_tasks 等，
均为 ondelete=RESTRICT）引用，无法直接物理删除。此处复用 0037 的策略：
先把引用杂散网点的流水重定向到同城核心网点，再把可空外键置 NULL，
最后删除 service_areas 与 stations 本身。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 运单始发/目的网点：按网点区划前两位归并到上海（31）或北京（其余）。
    op.execute(
        """
        UPDATE shipments AS target
        SET origin_station_id = CASE WHEN left(source.district_code, 2) = '31'
                                     THEN (SELECT id FROM stations WHERE code = 'SHS-001')
                                     ELSE (SELECT id FROM stations WHERE code = 'BJS-001')
                                END
        FROM stations AS source
        WHERE source.id = target.origin_station_id
          AND source.code NOT IN ('BJS-001', 'SHS-001')
        """
    )
    op.execute(
        """
        UPDATE shipments AS target
        SET destination_station_id = CASE WHEN left(source.district_code, 2) = '31'
                                          THEN (SELECT id FROM stations WHERE code = 'SHS-001')
                                          ELSE (SELECT id FROM stations WHERE code = 'BJS-001')
                                     END
        FROM stations AS source
        WHERE source.id = target.destination_station_id
          AND source.code NOT IN ('BJS-001', 'SHS-001')
        """
    )
    op.execute(
        """
        UPDATE transport_legs AS target
        SET origin_station_id = CASE WHEN left(source.district_code, 2) = '31'
                                     THEN (SELECT id FROM stations WHERE code = 'SHS-001')
                                     ELSE (SELECT id FROM stations WHERE code = 'BJS-001')
                                END
        FROM stations AS source
        WHERE source.id = target.origin_station_id
          AND source.code NOT IN ('BJS-001', 'SHS-001')
        """
    )
    op.execute(
        """
        UPDATE transport_legs AS target
        SET destination_station_id = CASE WHEN left(source.district_code, 2) = '31'
                                          THEN (SELECT id FROM stations WHERE code = 'SHS-001')
                                          ELSE (SELECT id FROM stations WHERE code = 'BJS-001')
                                     END
        FROM stations AS source
        WHERE source.id = target.destination_station_id
          AND source.code NOT IN ('BJS-001', 'SHS-001')
        """
    )
    # 快递员任务网点：跟随其运单的始发网点。
    op.execute(
        """
        UPDATE courier_tasks AS target
        SET station_id = shipment.origin_station_id
        FROM shipments AS shipment, stations AS source
        WHERE shipment.id = target.shipment_id
          AND source.id = target.station_id
          AND source.code NOT IN ('BJS-001', 'SHS-001')
        """
    )
    # 可空外键一律置 NULL，避免残留杂散网点引用。
    op.execute(
        """
        UPDATE users SET station_id = NULL
        WHERE station_id NOT IN (SELECT id FROM stations WHERE code IN ('BJS-001', 'SHS-001'))
        """
    )
    op.execute(
        """
        UPDATE pickup_credentials SET station_id = NULL
        WHERE station_id IS NOT NULL
          AND station_id NOT IN (SELECT id FROM stations WHERE code IN ('BJS-001', 'SHS-001'))
        """
    )
    op.execute(
        """
        UPDATE proofs_of_delivery SET station_id = NULL
        WHERE station_id IS NOT NULL
          AND station_id NOT IN (SELECT id FROM stations WHERE code IN ('BJS-001', 'SHS-001'))
        """
    )
    op.execute(
        """
        UPDATE exception_cases SET responsible_station_id = NULL
        WHERE responsible_station_id IS NOT NULL
          AND responsible_station_id NOT IN (
              SELECT id FROM stations WHERE code IN ('BJS-001', 'SHS-001')
          )
        """
    )
    op.execute(
        """
        DELETE FROM service_areas
        WHERE station_id NOT IN (SELECT id FROM stations WHERE code IN ('BJS-001', 'SHS-001'))
        """
    )
    op.execute(
        """
        DELETE FROM stations
        WHERE code NOT IN ('BJS-001', 'SHS-001')
        """
    )


def downgrade() -> None:
    # 被删除的测试网点无法重建原始 UUID 与元数据；核心网点集合为永久收敛。
    pass
