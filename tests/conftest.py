import pytest
import time
import tempfile
from pathlib import Path

import unoserver

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")

def is_uno_available() -> bool:
    """Check if the 'uno' library (LibreOffice Python bridge) is available."""
    try:
        import uno  # noqa: F401
        return True
    except ImportError:
        return False

@pytest.fixture(scope="session")
def server_fixture():
    with tempfile.TemporaryDirectory() as tmpuserdir:
        user_installation = Path(tmpuserdir).as_uri()
        srvr = unoserver.server.UnoServer(user_installation=user_installation)
        process = srvr.start()
        # Give libreoffice a chance to start
        time.sleep(8)
        yield process  # provide the fixture value
        print("Teardown Unoserver")
        srvr.stop()

@pytest.fixture(scope="session")
def visible_slideshow_server():
    """Dedicated fixture for slideshow tests (non-headless ready)"""
    if not is_uno_available():
        pytest.skip("Skipping slideshow server fixture: 'uno' library not available. "
                   "Run tests using LibreOffice's bundled Python.")

    with tempfile.TemporaryDirectory() as tmpuserdir:
        user_installation = Path(tmpuserdir).as_uri()
        srvr = unoserver.server.UnoServer(
            user_installation=user_installation,
            port="2005",
            uno_port="2004"
        )
        process = srvr.start()
        time.sleep(8)
        yield process, srvr
        print("Teardown Visible Slideshow Server")
        srvr.stop()