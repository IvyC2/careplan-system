"""
Unit tests for exception classes and AppExceptionMiddleware.
No database access required.
"""
import json
import pytest
from django.test import RequestFactory
from django.http import JsonResponse

from careplan_app.exceptions import ValidationError, BlockError, WarningException, BaseAppException
from careplan_app.exception_handler import AppExceptionMiddleware, handle_exception


# ── ValidationError ────────────────────────────────────────────────────────────

def test_validation_error_attributes():
    exc = ValidationError("bad input", code="FOO")
    assert exc.http_status == 400
    assert exc.type == "VALIDATION_ERROR"
    assert exc.code == "FOO"
    assert exc.message == "bad input"


def test_validation_error_default_code():
    exc = ValidationError("bad input")
    assert exc.code == "INVALID_INPUT"


def test_validation_error_to_response_dict():
    exc = ValidationError("bad input", code="SOME_CODE")
    d = exc.to_response_dict()
    assert d["success"] is False
    assert d["type"] == "VALIDATION_ERROR"
    assert d["code"] == "SOME_CODE"
    assert d["message"] == "bad input"
    assert "detail" in d


def test_validation_error_with_detail():
    exc = ValidationError("bad input", code="X", detail={"field": "npi"})
    d = exc.to_response_dict()
    assert d["detail"] == {"field": "npi"}


# ── BlockError ─────────────────────────────────────────────────────────────────

def test_block_error_attributes():
    exc = BlockError("blocked")
    assert exc.http_status == 409
    assert exc.type == "BLOCK_ERROR"
    assert exc.code == "BUSINESS_RULE_VIOLATION"


def test_block_error_custom_code():
    exc = BlockError("blocked", code="MY_RULE")
    assert exc.code == "MY_RULE"


# ── WarningException ───────────────────────────────────────────────────────────

def test_warning_exception_attributes():
    exc = WarningException("heads up", code="WARN_X")
    assert exc.http_status == 200
    assert exc.type == "WARNING"
    assert exc.code == "WARN_X"


def test_warning_exception_default_code():
    exc = WarningException("heads up")
    assert exc.code == "DUPLICATE_WARNING"


# ── BaseAppException is parent ─────────────────────────────────────────────────

def test_all_exceptions_are_subclasses_of_base():
    assert issubclass(ValidationError, BaseAppException)
    assert issubclass(BlockError, BaseAppException)
    assert issubclass(WarningException, BaseAppException)


# ── handle_exception ───────────────────────────────────────────────────────────

def test_handle_exception_app_error_returns_json_response():
    exc = ValidationError("test error", code="TEST")
    response = handle_exception(exc)
    assert response is not None
    assert response.status_code == 400
    # response is JsonResponse (DRF not installed in test env)
    data = json.loads(response.content)
    assert data["code"] == "TEST"
    assert data["success"] is False


def test_handle_exception_block_error_returns_409():
    exc = BlockError("blocked", code="DUPE")
    response = handle_exception(exc)
    assert response.status_code == 409
    data = json.loads(response.content)
    assert data["code"] == "DUPE"


def test_handle_exception_warning_returns_200():
    exc = WarningException("warn", code="W1")
    response = handle_exception(exc)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["type"] == "WARNING"


def test_handle_exception_non_app_exception_returns_none():
    response = handle_exception(ValueError("unrelated"))
    assert response is None


def test_handle_exception_standard_exception_returns_none():
    response = handle_exception(RuntimeError("crash"))
    assert response is None


# ── AppExceptionMiddleware ─────────────────────────────────────────────────────

@pytest.fixture
def factory():
    return RequestFactory()


def test_middleware_converts_app_exception_to_json(factory):
    request = factory.get("/")
    middleware = AppExceptionMiddleware(get_response=lambda r: None)
    exc = ValidationError("test error", code="TEST")
    response = middleware.process_exception(request, exc)
    assert response is not None
    assert response.status_code == 400
    data = json.loads(response.content)
    assert data["code"] == "TEST"


def test_middleware_ignores_non_app_exceptions(factory):
    request = factory.get("/")
    middleware = AppExceptionMiddleware(get_response=lambda r: None)
    response = middleware.process_exception(request, ValueError("unrelated"))
    assert response is None


def test_middleware_call_passes_through(factory):
    sentinel = object()
    request = factory.get("/")
    middleware = AppExceptionMiddleware(get_response=lambda r: sentinel)
    result = middleware(request)
    assert result is sentinel
