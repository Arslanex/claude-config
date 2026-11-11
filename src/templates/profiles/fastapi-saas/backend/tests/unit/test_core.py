"""core: kimlik, hata modeli, istek baglami, sema tabanlari (ARCH-0004, ARCH-0005)."""

import time

import pytest
from pydantic import ValidationError

from PKG_NAME.core import (
    TRACE_ID,
    AppError,
    ErrorCode,
    ErrorKind,
    FeatureIn,
    FeatureOut,
    current_trace_id,
    new_id,
)


def test_new_id_is_uuid7_and_time_ordered():
    first = new_id()
    time.sleep(0.002)
    second = new_id()
    assert first.version == 7
    assert first.variant == "specified in RFC 4122"
    assert first < second
    assert abs((first.int >> 80) - time.time_ns() // 1_000_000) < 1_000


def test_app_error_carries_code_and_details():
    code = ErrorCode("NOTE_NOT_FOUND", ErrorKind.NOT_FOUND, "Not bulunamadi.")
    error = AppError(code, {"id": "1"})
    assert str(error) == "NOTE_NOT_FOUND: Not bulunamadi."
    assert error.details == {"id": "1"}
    assert AppError(code).details == {}


def test_trace_id_defaults_to_empty_and_follows_the_context():
    assert current_trace_id() == ""
    token = TRACE_ID.set("abc")
    try:
        assert current_trace_id() == "abc"
    finally:
        TRACE_ID.reset(token)


def test_feature_in_rejects_unknown_fields_and_is_frozen():
    class NoteIn(FeatureIn):
        title: str

    note = NoteIn(title="a")
    with pytest.raises(ValidationError):
        NoteIn(title="a", extra=1)
    with pytest.raises(ValidationError):
        note.title = "b"


def test_feature_out_reads_attributes():
    class Row:
        title = "a"

    class NoteOut(FeatureOut):
        title: str

    assert NoteOut.model_validate(Row()).title == "a"
