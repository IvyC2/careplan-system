from django.http import JsonResponse
from .exceptions import BaseAppException


def handle_exception(exc, context=None):
    """
    Unified exception handler.

    Dual-mode:
      - Django:  registered via AppExceptionMiddleware (process_exception)
      - DRF:     registered via REST_FRAMEWORK['EXCEPTION_HANDLER'] in settings.py

    Handled exceptions → consistent JSON with {success, type, code, message, detail}.
    Unrecognised exceptions → return None (let the framework handle them normally).
    """
    if isinstance(exc, BaseAppException):
        return _make_response(exc.to_response_dict(), exc.http_status)

    # DRF ValidationError compatibility (no-op if DRF is not installed)
    try:
        from rest_framework.exceptions import ValidationError as DRFValidationError
        if isinstance(exc, DRFValidationError):
            data = {
                "success": False,
                "type": "VALIDATION_ERROR",
                "code": "INVALID_INPUT",
                "message": "Validation failed",
                "detail": exc.detail,
            }
            return _make_response(data, 400)
    except ImportError:
        pass

    return None  # unrecognised — let Django / DRF handle it


def _make_response(data: dict, status: int):
    """Return a DRF Response when DRF is available, otherwise a plain JsonResponse."""
    try:
        from rest_framework.response import Response
        return Response(data, status=status)
    except ImportError:
        return JsonResponse(data, status=status)


class AppExceptionMiddleware:
    """
    Django middleware adapter.
    Catches any BaseAppException raised in a view and converts it to JSON
    via handle_exception — no try/except needed in views.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exc):
        return handle_exception(exc)
