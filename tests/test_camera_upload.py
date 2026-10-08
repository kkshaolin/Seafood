"""Tests for real-media YOLO upload inference, separate from application runtime."""

import asyncio
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

workspace_root = Path(__file__).resolve().parents[1]
backend_src = workspace_root / "backend" / "src"
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))

from api import camera as camera_api  # noqa: E402


def _jpeg_bytes() -> bytes:
    image = np.full((64, 96, 3), (20, 110, 210), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def test_uploaded_real_image_returns_yolo_annotated_result(monkeypatch):
    class FakeBoxes:
        conf = np.array([0.8, 0.9])

        def __len__(self):
            return len(self.conf)

    class FakeModel:
        def predict(self, frame, conf, verbose):
            assert frame.shape == (64, 96, 3)
            assert conf == 0.15
            assert verbose is False
            result = SimpleNamespace(
                boxes=FakeBoxes(),
                plot=lambda labels, conf: frame,
            )
            return [result]

    monkeypatch.setattr(camera_api, "get_yolo_model", lambda: FakeModel())
    camera_api._LATEST_UPLOADS.clear()
    upload = UploadFile(filename="actual-camera-frame.jpg", file=io.BytesIO(_jpeg_bytes()))

    response = asyncio.run(camera_api.upload_camera_media("cam_main", upload))

    assert response.media_type == "image/jpeg"
    assert response.headers["x-detected-boxes"] == "2"
    assert response.headers["x-detection-confidence"] == "0.85"
    assert response.headers["x-source-type"] == "image"
    assert response.body.startswith(b"\xff\xd8")
    assert asyncio.run(camera_api.get_latest_camera_inference("cam_main"))["detected_boxes"] == 2


def test_camera_upload_rejects_unsupported_media():
    upload = UploadFile(filename="camera-data.csv", file=io.BytesIO(b"not media"))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(camera_api.upload_camera_media("cam_main", upload))
    assert exc_info.value.status_code == 415


def test_camera_upload_does_not_accept_unknown_zone():
    upload = UploadFile(filename="actual-camera-frame.jpg", file=io.BytesIO(_jpeg_bytes()))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(camera_api.upload_camera_media("unknown", upload))
    assert exc_info.value.status_code == 404
