import pytest
import time
import tempfile
import sys
from pathlib import Path

from gotedo_unoserver import server

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")

def is_uno_available() -> bool:
    """Check if the 'uno' library (LibreOffice Python bridge) is available."""
    try:
        import uno  # noqa: F401
        return True
    except ImportError:
        return False

def cleanup_lock_files():
    """Remove LibreOffice lock files after tests."""
    documents_dir = Path(__file__).parent / "documents"
    for lock_file in documents_dir.glob(".~lock.*"):
        try:
            lock_file.unlink()
            print(f"Cleaned lock file: {lock_file.name}")
        except Exception as e:
            print(f"Failed to remove lock file {lock_file.name}: {e}")

def find_soffice_executable() -> str:
    """Automatically find soffice executable from LibreOffice bundle."""
    python_path = Path(sys.executable).resolve()

    # Build multiple candidate paths based on typical LibreOffice structures
    candidates = [
        # Your exact structure
        python_path.parent.parent.parent.parent.parent.parent.parent.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent.parent.parent.parent.parent.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent.parent.parent.parent.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent.parent.parent.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent.parent.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent.parent / "MacOS" / "soffice",
        python_path.parent.parent / "MacOS" / "soffice",
        python_path.parent / "soffice",
        # General fallbacks
        python_path.parent.parent / "MacOS" / "libreoffice",
        python_path.parent / "libreoffice",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            print(f"Found soffice at: {candidate}")
            return str(candidate)

    # Final fallback: search in PATH
    import shutil
    for name in ("soffice", "libreoffice"):
        if path := shutil.which(name):
            return path

    raise FileNotFoundError(
        f"Could not find 'soffice' executable. Python path: {python_path}\n"
        "Please check your LibreOffice bundle structure."
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")

@pytest.fixture(scope="session", autouse=True)
def cleanup_locks_after_tests():
    """Automatically clean lock files after all tests finish."""
    yield
    cleanup_lock_files()

@pytest.fixture(scope="session")
def server_fixture():
    """Headless conversion server fixture - now with proper soffice detection"""
    if not is_uno_available():
        pytest.skip("uno library not available")

    soffice_path = find_soffice_executable()
    print(f"Using soffice executable: {soffice_path}")

    with tempfile.TemporaryDirectory() as tmpuserdir:
        user_installation = Path(tmpuserdir).as_uri()

        srvr = server.UnoServer(
            user_installation=user_installation,
            # You can add these if your UnoServer supports them:
            # port=2003,
            # uno_port=2002,
        )

        # Pass the executable explicitly
        process = srvr.start(executable=soffice_path, headless=True)
        
        print("Waiting for server to start...")
        time.sleep(8)   # Give it time to initialize

        yield process
        print("Teardown Unoserver")
        srvr.stop()


@pytest.fixture(scope="function")
def visible_slideshow_server(request):
    """Dedicated fixture for slideshow tests with clean launch"""
    if not is_uno_available():
        pytest.skip("uno library not available")

    # Extract the parametrized filename from the test
    filename = "presentation_test.odp" # Default fallback
    if "filename" in request.fixturenames:
        filename = request.getfixturevalue("filename")

    presentation_path = str(Path(__file__).parent / "documents" / filename)

    with tempfile.TemporaryDirectory() as tmpuserdir:
        user_installation = Path(tmpuserdir).as_uri()
        print(f"Using fresh profile: {user_installation}")

        soffice_path = find_soffice_executable()

        srvr = server.UnoServer(
            user_installation=user_installation,
            port="2005",
            uno_port="2004"
        )

        # Important: Pass executable and let UnoServer use it without forcing headless
        # headless=False is critical for slideshow
        process = srvr.start(executable=soffice_path, headless=False)
        
        # Longer wait for full initialization
        print("Waiting for LibreOffice to fully initialize...")
        time.sleep(10)

        yield process, srvr
        print("Teardown Visible Slideshow Server")
        srvr.stop()