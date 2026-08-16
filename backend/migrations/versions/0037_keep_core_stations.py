"""Keep only the Beijing Dongcheng and Shanghai Changning stations."""

from collections.abc import Sequence

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep existing shipment history usable by mapping test/generated stations
    # back to the retained station in the same municipality.
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
        "UPDATE service_areas SET district_code = '110101' "
        "WHERE station_id = (SELECT id FROM stations WHERE code = 'BJS-001') "
        "AND district_code = '110105'"
    )
    op.execute(
        """
        INSERT INTO service_areas (id, district_code, service_type, station_id, version)
        SELECT gen_random_uuid(), '310105', 'STATION_DROP_OFF', id, 1
        FROM stations
        WHERE code = 'SHS-001'
          AND NOT EXISTS (
              SELECT 1 FROM service_areas
              WHERE district_code = '310105' AND service_type = 'STATION_DROP_OFF'
          )
        """
    )
    op.execute(
        """
        DELETE FROM stations
        WHERE code NOT IN ('BJS-001', 'SHS-001')
        """
    )
    op.execute(
        "UPDATE stations SET name = '北京东城网点', district_code = '110101' "
        "WHERE code = 'BJS-001'"
    )


def downgrade() -> None:
    # Deleted station rows cannot be reconstructed without their original UUIDs
    # and associated metadata; the core-station set is intentionally permanent.
    pass
