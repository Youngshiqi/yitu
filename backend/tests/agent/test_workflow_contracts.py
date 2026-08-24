"""工作流测试基础必须与开发数据库彻底隔离。"""

import pytest
from conftest import require_test_database_url


def test_database_tests_reject_non_test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "YITU_TEST_DATABASE_URL",
        "postgresql+asyncpg://user:pass@localhost/yitu",
    )

    with pytest.raises(RuntimeError, match="_test"):
        require_test_database_url()
