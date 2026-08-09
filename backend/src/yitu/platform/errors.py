class AppError(Exception):
    """表示可安全返回给 API 调用方的已知业务错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
