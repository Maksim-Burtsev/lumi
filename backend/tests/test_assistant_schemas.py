import uuid

import pytest
from pydantic import ValidationError

from lumi.assistant.schemas import MemoryUpdateRequest


def test_memory_update_importance_uses_integer_scale() -> None:
    request = MemoryUpdateRequest.model_validate({
        "memory_id": str(uuid.uuid4()),
        "importance": 5,
    })

    assert request.importance == 5


def test_memory_update_importance_accepts_legacy_fraction() -> None:
    request = MemoryUpdateRequest.model_validate({
        "memory_id": str(uuid.uuid4()),
        "importance": 0.7,
    })

    assert request.importance == 4


def test_memory_update_importance_rejects_out_of_range_value() -> None:
    with pytest.raises(ValidationError):
        MemoryUpdateRequest.model_validate({
            "memory_id": str(uuid.uuid4()),
            "importance": 6,
        })
