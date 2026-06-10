import sys
import types


def _install_route_import_stubs():
    youtube = types.ModuleType("backend.services.youtube_uploader")
    youtube.upload_video = lambda *args, **kwargs: None
    sys.modules["backend.services.youtube_uploader"] = youtube


_install_route_import_stubs()
from backend.api import routes


def test_find_active_video_job_ignores_script_and_finished_jobs():
    routes.jobs.clear()
    routes.jobs.update({
        "script1": {"status": "generating_script", "job_type": "script"},
        "done1": {"status": "completed", "job_type": "video"},
        "err1": {"status": "error", "job_type": "video"},
        "vid1": {"status": "generating_images", "job_type": "video", "progress": 20, "message": "이미지 생성 중"},
    })

    active = routes._find_active_video_job()

    assert active is not None
    assert active["job_id"] == "vid1"
    assert active["status"] == "generating_images"


def test_find_active_video_job_treats_legacy_video_jobs_without_type_as_active():
    routes.jobs.clear()
    routes.jobs.update({
        "legacy1": {"status": "composing_video", "progress": 80, "message": "렌더링 중"},
    })

    active = routes._find_active_video_job()

    assert active is not None
    assert active["job_id"] == "legacy1"


def test_can_start_video_job_rejects_when_another_video_is_running():
    routes.jobs.clear()
    routes.jobs.update({
        "vid1": {"status": "composing_video", "job_type": "video", "progress": 72},
    })

    allowed, active = routes._can_start_video_job()

    assert allowed is False
    assert active["job_id"] == "vid1"
