class BaseAppException(Exception):
    type: str = "APP_ERROR"
    http_status: int = 500
    default_code: str = "APP_ERROR"

    def __init__(self, message: str, code: str = None, detail=None):
        self.message = message
        self.code = code if code is not None else self.default_code
        self.detail = detail
        super().__init__(message)

    def to_response_dict(self) -> dict:
        return {
            "success": False,
            "type": self.type,
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
        }


class ValidationError(BaseAppException):
    type = "VALIDATION_ERROR"
    http_status = 400
    default_code = "INVALID_INPUT"


class BlockError(BaseAppException):
    type = "BLOCK_ERROR"
    http_status = 409
    default_code = "BUSINESS_RULE_VIOLATION"


class WarningException(BaseAppException):
    type = "WARNING"
    http_status = 200
    default_code = "DUPLICATE_WARNING"
