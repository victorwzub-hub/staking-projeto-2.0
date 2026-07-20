from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from pharma_api.core.config import Settings
from pharma_api.infrastructure import object_storage


@pytest.mark.parametrize(
    ("encryption", "expected"),
    [("AES256", "AES256"), (None, None)],
)
def test_s3_upload_encryption_is_configurable(
    tmp_path, monkeypatch: pytest.MonkeyPatch, encryption: str | None, expected: str | None
) -> None:
    client = MagicMock()
    client.head_object.side_effect = ClientError(
        {
            "Error": {"Code": "NoSuchKey", "Message": "missing"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        "HeadObject",
    )
    monkeypatch.setattr(object_storage.boto3, "client", lambda *args, **kwargs: client)
    settings = Settings(
        object_storage_backend="s3",
        s3_endpoint_url="http://minio:9000",
        s3_bucket="landing",
        s3_access_key_id="local-user",
        s3_secret_access_key="local-password",  # noqa: S106 - non-secret test fixture
        s3_server_side_encryption=encryption,
        _env_file=None,
    )
    storage = object_storage.S3ObjectStorage(settings)
    payload = tmp_path / "payload.ndjson"
    payload.write_bytes(b"{}\n")

    storage.put_file(
        payload,
        key="landing/tenant/payload.ndjson",
        content_type="application/x-ndjson",
        metadata={"tenant-id": "tenant"},
    )

    extra_args = client.upload_fileobj.call_args.kwargs["ExtraArgs"]
    assert extra_args.get("ServerSideEncryption") == expected
