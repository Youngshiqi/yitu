"""测试套件的安全边界与共享配置。"""

import os


def require_test_database_url() -> str:
    """仅允许显式命名的独立测试库进入数据库集成测试。"""
    url = os.environ.get("YITU_TEST_DATABASE_URL", "")
    database = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not url or not database.endswith("_test"):
        raise RuntimeError(
            "YITU_TEST_DATABASE_URL 必须指向以 _test 结尾的独立数据库"
        )
    return url
