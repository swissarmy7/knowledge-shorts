import importlib
import json
import os
import sys
import types
from pathlib import Path


def import_image_generator(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_GEMINI_API", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven")
    monkeypatch.setenv("IMAGE_PROVIDER", "auto")
    monkeypatch.setenv("AGY_IMAGE_TIMEOUT", "2")

    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.genai")
    types_mod = types.ModuleType("google.genai.types")
    genai_mod.Client = lambda *a, **k: object()
    types_mod.Modality = types.SimpleNamespace(IMAGE="IMAGE")
    types_mod.GenerateContentConfig = lambda *a, **k: object()
    setattr(google_mod, "genai", genai_mod)
    setattr(genai_mod, "types", types_mod)
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_mod)

    pil_mod = types.ModuleType("PIL")
    image_mod = types.ModuleType("PIL.Image")
    image_ops_mod = types.ModuleType("PIL.ImageOps")
    image_mod.open = lambda *a, **k: None
    image_mod.Resampling = types.SimpleNamespace(LANCZOS=object())
    image_ops_mod.fit = lambda *a, **k: types.SimpleNamespace(save=lambda *aa, **kk: None)
    monkeypatch.setitem(sys.modules, "PIL", pil_mod)
    monkeypatch.setitem(sys.modules, "PIL.Image", image_mod)
    monkeypatch.setitem(sys.modules, "PIL.ImageOps", image_ops_mod)

    sys.path.insert(0, str(Path(__file__).parent))
    for name in ["backend.config", "backend.services.image_generator"]:
        sys.modules.pop(name, None)
    return importlib.import_module("backend.services.image_generator")


def test_agy_request_paths_are_inside_shared_output(monkeypatch, tmp_path):
    ig = import_image_generator(monkeypatch, tmp_path)
    monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path / "output")
    ig.OUTPUT_DIR.mkdir(parents=True)

    request = ig.build_agy_image_request(
        prompt="draw a robot",
        output_rel="cache/images/agy/test.png",
        request_id="req-test",
    )

    assert request["request_id"] == "req-test"
    assert request["output_rel"] == "cache/images/agy/test.png"
    assert request["output_container_path"].endswith("/cache/images/agy/test.png")
    assert ".." not in Path(request["output_rel"]).parts


def test_agy_response_validation_rejects_missing_or_invalid_files(monkeypatch, tmp_path):
    ig = import_image_generator(monkeypatch, tmp_path)
    monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path / "output")
    ig.OUTPUT_DIR.mkdir(parents=True)

    missing_response = {"status": "ok", "output_rel": "cache/images/agy/missing.png"}
    try:
        ig.resolve_agy_response_image(missing_response)
    except Exception as e:
        assert "missing" in str(e).lower() or "not found" in str(e).lower()
    else:
        raise AssertionError("missing agy output should fail validation")


def test_agy_worker_request_roundtrip_files(monkeypatch, tmp_path):
    ig = import_image_generator(monkeypatch, tmp_path)
    monkeypatch.setattr(ig, "OUTPUT_DIR", tmp_path / "output")
    ig.OUTPUT_DIR.mkdir(parents=True)

    req_path, res_path = ig.write_agy_image_request(
        prompt="draw a robot",
        output_rel="cache/images/agy/test.png",
        request_id="req-roundtrip",
    )

    assert req_path.exists()
    payload = json.loads(req_path.read_text(encoding="utf-8"))
    assert payload["prompt"] == "draw a robot"
    assert payload["output_rel"] == "cache/images/agy/test.png"
    assert res_path.name == "req-roundtrip.response.json"
