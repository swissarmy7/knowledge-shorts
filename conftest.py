"""Test import stubs for helper-only tests on the host Python.

The production container has google-genai and Pillow, but the lightweight host
pytest environment used by Hermes may not. These tests exercise pure prompt and
request-building helpers only, so small import stubs are sufficient.
"""
import sys
import types

if "google" not in sys.modules:
    fake_google = types.ModuleType("google")
    fake_genai = types.ModuleType("google.genai")
    fake_types = types.ModuleType("google.genai.types")
    setattr(fake_genai, "Client", lambda *args, **kwargs: None)
    setattr(fake_types, "Tool", lambda *args, **kwargs: None)
    setattr(fake_types, "GoogleSearch", lambda *args, **kwargs: None)
    setattr(fake_types, "GenerateContentConfig", lambda *args, **kwargs: None)
    setattr(fake_types, "Modality", types.SimpleNamespace(IMAGE="IMAGE"))
    setattr(fake_google, "genai", fake_genai)
    setattr(fake_genai, "types", fake_types)
    sys.modules["google"] = fake_google
    sys.modules["google.genai"] = fake_genai
    sys.modules["google.genai.types"] = fake_types

if "PIL" not in sys.modules:
    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image_ops = types.ModuleType("PIL.ImageOps")
    setattr(fake_image, "open", lambda *args, **kwargs: None)
    setattr(fake_image, "Resampling", types.SimpleNamespace(LANCZOS="LANCZOS"))
    setattr(fake_image_ops, "fit", lambda *args, **kwargs: None)
    setattr(fake_pil, "Image", fake_image)
    setattr(fake_pil, "ImageOps", fake_image_ops)
    sys.modules["PIL"] = fake_pil
    sys.modules["PIL.Image"] = fake_image
    sys.modules["PIL.ImageOps"] = fake_image_ops
