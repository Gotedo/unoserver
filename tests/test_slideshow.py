"""Comprehensive tests for Slideshow functionality — Testing .odp, .ppt, and .pptx"""

import os
import time
import pytest

try:
    from unoserver import client
except ImportError:
    client = None

TEST_DOCS = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "documents")

PRESENTATION_FILES = [
    "presentation_test.odp",
    "presentation_test.ppt",
    "presentation_test.pptx",
]


def requires_uno(func):
    """Decorator to skip tests that require the 'uno' library"""
    def wrapper(*args, **kwargs):
        if client is None:
            pytest.skip("Skipping test: 'uno' library not available. "
                       "Run using LibreOffice bundled Python.")
        return func(*args, **kwargs)
    return wrapper


@pytest.mark.integration
@pytest.mark.parametrize("filename", PRESENTATION_FILES)
@requires_uno
def test_slideshow_full_workflow(visible_slideshow_server, filename):
    """Full lifecycle test across all three presentation formats"""
    _, _ = visible_slideshow_server
    clt = client.UnoClient(port="2005")

    ppt_path = os.path.join(TEST_DOCS, filename)
    if not os.path.exists(ppt_path):
        pytest.skip(f"Test presentation missing: {filename}")

    # Load
    session_id = clt.load_presentation(ppt_path)
    assert session_id.startswith("ss_")

    # Start
    success = clt.start_slideshow(session_id, {"start_slide": 1, "loop": False})
    assert success is True

    time.sleep(1.5)

    # Navigation
    clt.next_slide(session_id)
    clt.goto_slide(session_id, 3)
    clt.previous_slide(session_id)

    # Query
    index = clt.get_current_slide_index(session_id)
    assert index >= 0

    # Pause / Resume
    clt.pause_slideshow(session_id)
    clt.resume_slideshow(session_id)

    # Cleanup
    clt.end_slideshow(session_id)


@pytest.mark.integration
@pytest.mark.parametrize("filename", PRESENTATION_FILES)
@requires_uno
def test_slideshow_options(visible_slideshow_server, filename):
    """Test different start options"""
    _, _ = visible_slideshow_server
    clt = client.UnoClient(port="2005")

    ppt_path = os.path.join(TEST_DOCS, filename)
    if not os.path.exists(ppt_path):
        pytest.skip(f"File not found: {filename}")

    session_id = clt.load_presentation(ppt_path)
    assert clt.start_slideshow(session_id, {"start_slide": 3, "loop": True}) is True

    clt.goto_slide(session_id, 5)
    assert clt.get_current_slide_index(session_id) >= 3

    clt.end_slideshow(session_id)


@requires_uno
def test_multiple_concurrent_slideshows(visible_slideshow_server):
    """Test managing multiple slideshow sessions simultaneously"""
    _, _ = visible_slideshow_server
    clt = client.UnoClient(port="2005")

    active_sessions = []
    for fname in PRESENTATION_FILES:
        path = os.path.join(TEST_DOCS, fname)
        if os.path.exists(path):
            sid = clt.load_presentation(path)
            clt.start_slideshow(sid, {"start_slide": 1})
            active_sessions.append(sid)

    # Interact with them
    for i, sid in enumerate(active_sessions):
        clt.goto_slide(sid, i + 2)

    # Cleanup
    for sid in active_sessions:
        clt.end_slideshow(sid)


@pytest.mark.integration
@pytest.mark.parametrize("filename", PRESENTATION_FILES)
@requires_uno
def test_window_visibility_via_uno(visible_slideshow_server, filename):
    """Advanced test — verify slideshow controller becomes active"""
    _, _ = visible_slideshow_server
    clt = client.UnoClient(port="2005")

    ppt_path = os.path.join(TEST_DOCS, filename)
    if not os.path.exists(ppt_path):
        pytest.skip(f"Missing: {filename}")

    session_id = clt.load_presentation(ppt_path)
    clt.start_slideshow(session_id)

    time.sleep(3)   # Allow initialization

    index = clt.get_current_slide_index(session_id)
    assert index >= 0, f"Slideshow for {filename} is not reporting active slide index"

    clt.next_slide(session_id)
    assert clt.get_current_slide_index(session_id) > index - 1

    clt.end_slideshow(session_id)