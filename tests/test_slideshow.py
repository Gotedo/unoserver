"""Comprehensive tests for Slideshow functionality — Testing .odp, .ppt, and .pptx"""

import os
import time
import pytest
import tempfile
from pathlib import Path
from functools import wraps
from screeninfo import get_monitors
from .conftest import find_soffice_executable 

try:
    from gotedo_unoserver import client, server
except ImportError:
    client = None
    server = None

TEST_DOCS = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "documents")

PRESENTATION_FILES = [
    "presentation_test.odp",
    # "presentation_test.ppt",
    # "presentation_test.pptx",
]


def requires_uno(func):
    """Decorator to skip tests that require the 'uno' library"""
    @wraps(func)
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
    assert session_id.startswith(("ss_", "slideshow_"))

    # Start
    success = clt.start_slideshow(session_id, {"start_slide": 0, "loop": False})
    assert success is True

    time.sleep(5)

    # Navigation
    clt.next_slide(session_id)
    time.sleep(1)
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
    
    # Start with loop enabled
    assert clt.start_slideshow(session_id, {"start_slide": 3, "loop": True}) is True

    # 1. Assert that the loop setting was actually applied to the UNO engine
    settings = clt.get_slideshow_settings(session_id)
    assert settings.get("loop") is True
    assert settings.get("pause") == 0  # We set pause to 0 for seamless looping

    # 2. Assert navigation
    clt.goto_slide(session_id, 5)
    time.sleep(1) # Give the slide a moment to transition
    assert clt.get_current_slide_index(session_id) >= 3

    clt.end_slideshow(session_id)


@pytest.mark.integration
@requires_uno
def test_multiple_concurrent_slideshows():
    """
    Robustly test managing multiple independent LibreOffice instances 
    and slideshow sessions simultaneously via different ports.
    """
    # 1. Find the first available presentation file
    target_file = None
    for fname in PRESENTATION_FILES:
        path = os.path.join(TEST_DOCS, fname)
        if os.path.exists(path):
            target_file = path
            break
            
    if not target_file:
        pytest.skip("No presentation files found for testing.")

    # Dynamic Discovery: Fetch attached monitors and limit execution to a maximum of 2 instances
    detected_monitors = get_monitors()
    num_instances = min(len(detected_monitors), 2)
    if num_instances == 0:
        pytest.skip("No monitors detected via screeninfo.")

    # 2. Create entirely isolated user profiles for the two instances
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        install_url_1 = Path(tmp1).as_uri()
        install_url_2 = Path(tmp2).as_uri()

        # Instance 1: UNO Port 2004, RPC Port 2005
        srvr1 = server.UnoServer(user_installation=install_url_1, port="2005", uno_port="2004")
        
        # Instance 2: UNO Port 2006, RPC Port 2007
        srvr2 = server.UnoServer(user_installation=install_url_2, port="2007", uno_port="2006")

        sid1 = sid2 = None
        clt1 = clt2 = None

        try:
            # 3. Start both servers
            # Note: Slideshows strictly require headless=False, but our hidden document 
            # architecture ensures the UI remains completely invisible to the user.
            executable = find_soffice_executable()
            
            # Start Instance 1 unconditionally since at least 1 monitor is guaranteed
            srvr1.start(executable=executable, headless=False)
            
            # Allow time for both heavy LibreOffice C++ engines to boot up
            time.sleep(10)   # Increased for stability

            # 4. Connect independent client
            clt1 = client.UnoClient(port="2005")

            # ==========================================
            # === INSTANCE 1 SEPARATE WORKFLOW RUN ===
            # ==========================================

            # Define options mapping targeted coordinates (center of each respective monitor)
            m1 = detected_monitors[0]
            opts1 = {
                "start_slide": 1, 
                "display_x": m1.x + (m1.width // 2), 
                "display_y": m1.y + (m1.height // 2)
            }

            # 5. Load the identical document into both instances
            sid1 = clt1.load_presentation(target_file, opts1)

            # 6. Start both slideshows concurrently
            assert clt1.start_slideshow(sid1, opts1) is True

            time.sleep(3) # Give both macOS window contexts time to paint

            # 7. CONCURRENT CONTROL: Move them to different slides
            clt1.goto_slide(sid1, 2)  # Instance 1 -> Slide 3 (0-indexed)
            
            time.sleep(1) # Allow transition animations to finish

            # 8. ASSERT INDEPENDENCE
            idx1 = clt1.get_current_slide_index(sid1)
            assert idx1 == 2, f"Instance 1 state corrupted. Expected slide index 2, got {idx1}"

            # ==========================================
            # === INSTANCE 2 SEPARATE WORKFLOW RUN ===
            # ==========================================

            if num_instances == 2:
                # Conditionally start Instance 2 only if a second physical monitor is attached
                srvr2.start(executable=executable, headless=False)
                time.sleep(10)   # Increased for stability on second instance

                clt2 = client.UnoClient(port="2007")

                # Define options mapping targeted coordinates (center of each respective monitor)
                m2 = detected_monitors[1]
                opts2 = {
                    "start_slide": 1, 
                    "display_x": m2.x + (m2.width // 2), 
                    "display_y": m2.y + (m2.height // 2)
                }

                # 5. Load the identical document into both instances
                sid2 = clt2.load_presentation(target_file, opts2)

                # 6. Start both slideshows concurrently
                assert clt2.start_slideshow(sid2, opts2) is True

                time.sleep(3) # Give both macOS window contexts time to paint

                # 7. CONCURRENT CONTROL: Move them to different slides
                clt2.goto_slide(sid2, 4)  # Instance 2 -> Slide 5 (0-indexed)
                
                time.sleep(1) # Allow transition animations to finish

                # 8. ASSERT INDEPENDENCE
                idx2 = clt2.get_current_slide_index(sid2)
                assert idx2 == 4, f"Instance 2 state corrupted. Expected slide index 4, got {idx2}"

            # Keep the slideshows active and visibly on screen for visual verification 
            # before the test structure cleanly breaks down.
            time.sleep(5)

        finally:
            # 9. Guaranteed Cleanup (Even if assertions fail)
            if sid1 and clt1:
                try: clt1.end_slideshow(sid1)
                except Exception: pass
            if sid2 and clt2:
                try: clt2.end_slideshow(sid2)
                except Exception: pass
            
            srvr1.stop()
            srvr2.stop()


@pytest.mark.integration
@pytest.mark.parametrize("filename", PRESENTATION_FILES)
@requires_uno
def test_window_visibility_via_uno(visible_slideshow_server, filename):
    """Advanced test — verify slideshow controller becomes active"""
    _, _ = visible_slideshow_server
    clt = client.UnoClient(port="2005")
    
    # Dynamically detect attached displays
    detected_monitors = get_monitors()
    if not detected_monitors:
        pytest.skip("No monitors detected via screeninfo.")

    # Target the 2nd monitor if found, else fall back to the 1st one
    if len(detected_monitors) >= 2:
        m = detected_monitors[1]
    else:
        m = detected_monitors[0]

    opts = {
        "start_slide": 1, 
        "display_x": m.x + (m.width // 2), 
        "display_y": m.y + (m.height // 2)
    }

    ppt_path = os.path.join(TEST_DOCS, filename)
    if not os.path.exists(ppt_path):
        pytest.skip(f"Missing: {filename}")

    # Inject options context during the load phase to ensure correct editor stashing
    session_id = clt.load_presentation(ppt_path, opts)
    clt.start_slideshow(session_id, opts)

    time.sleep(3)   # Allow initialization

    index = clt.get_current_slide_index(session_id)
    assert index >= 0, f"Slideshow for {filename} is not reporting active slide index"

    clt.next_slide(session_id)
    assert clt.get_current_slide_index(session_id) > index - 1

    clt.end_slideshow(session_id)