from app.core.response import failure, success
from app.schemas.common import HealthData, PaginationMeta, ResponseEnvelope


def test_success_envelope_shape() -> None:
    env = success({"hello": "world"})
    dumped = env.model_dump()
    assert dumped == {"success": True, "data": {"hello": "world"}, "error": None}


def test_failure_envelope_shape() -> None:
    env = failure("AUTH_INVALID_TOKEN", "認證失敗", details={"hint": "expired"})
    dumped = env.model_dump()
    assert dumped["success"] is False
    assert dumped["data"] is None
    assert dumped["error"] == {
        "code": "AUTH_INVALID_TOKEN",
        "message": "認證失敗",
        "details": {"hint": "expired"},
    }


def test_typed_envelope_with_health_data() -> None:
    env: ResponseEnvelope[HealthData] = success(HealthData(status="ok", version="0.1.0"))
    assert env.data is not None
    assert env.data.status == "ok"


def test_pagination_meta_fields() -> None:
    p = PaginationMeta(total=100, page=2, limit=20, total_pages=5)
    assert p.total_pages == 5
