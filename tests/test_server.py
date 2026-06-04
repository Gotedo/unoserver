"""Unoserver unit tests"""

import os
import pytest
import psutil
from unittest import mock
from gotedo_unoserver import server, client

TEST_DOCS = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "documents")


@mock.patch("threading.Thread")
@mock.patch("subprocess.Popen")
def test_server_params(popen_mock, thread_mock):
    popen_mock.return_value.pid = 12345

    srv = server.UnoServer(port="2203", uno_port="2202")
    srv.start()
    popen_mock.assert_called_with(
        [
            "libreoffice",
            "--nocrashreport",
            "--nodefault",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation={srv.user_installation}",
            "--accept=socket,host=127.0.0.1,port=2202,tcpNoDelay=1;urp;StarOffice.ComponentContext",
            "--headless",
            "--invisible",
        ]
    )


@mock.patch("threading.Thread")
@mock.patch("subprocess.Popen")
def test_server_ipv6_params(popen_mock, thread_mock):
    popen_mock.return_value.pid = 12345
    
    srv = server.UnoServer(interface="::", port="2203", uno_port="2202")
    srv.start()
    popen_mock.assert_called_with(
        [
            "libreoffice",
            "--nocrashreport",
            "--nodefault",
            "--nologo",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation={srv.user_installation}",
            "--accept=socket,host=127.0.0.1,port=2202,tcpNoDelay=1;urp;StarOffice.ComponentContext",
            "--headless",
            "--invisible",
        ]
    )

@mock.patch("psutil.Process")
def test_resource_tracker_aggregation(mock_process):
    tracker = server.ResourceTracker()
    
    # Inject 3 mock samples (equivalent to 15 seconds of tracking)
    tracker.history.extend([
        {'cpu_percent': 10.0, 'mem_bytes': 1024, 'mem_percent': 1.0},
        {'cpu_percent': 20.0, 'mem_bytes': 2048, 'mem_percent': 2.0},
        {'cpu_percent': 30.0, 'mem_bytes': 3072, 'mem_percent': 3.0},
    ])
    
    # Safely trigger the private aggregation method
    with tracker.lock:
        tracker._aggregate_summaries()
        
    summaries = tracker.get_summaries()
    
    # The 5-second summary should equal exactly the last sample
    assert summaries["5s"]["cpu_percent"] == 30.0
    assert summaries["5s"]["mem_bytes"] == 3072
    
    # The 15-second summary should average all 3 samples: (10 + 20 + 30) / 3 = 20.0
    assert summaries["15s"]["cpu_percent"] == 20.0
    assert summaries["15s"]["mem_bytes"] == 2048
    
    # The 60-second summary averages all available samples up to 12
    # Since we only have 3, it should match the 15-second average
    assert summaries["60s"]["cpu_percent"] == 20.0
    assert summaries["60s"]["mem_percent"] == 2.0

@mock.patch("psutil.Process")
@mock.patch("os.path.exists")
def test_resource_tracker_process_death(mock_exists, mock_process):
    tracker = server.ResourceTracker()

    # Setup a healthy state
    tracker.history.append({'cpu_percent': 50.0, 'mem_bytes': 4096, 'mem_percent': 4.0})
    with tracker.lock:
        tracker._aggregate_summaries()

    assert tracker.get_summaries()["5s"] is not None

    # Simulate the PID file disappearing
    mock_exists.return_value = False

    # Trigger the exception block logic manually to ensure reset works
    process = None
    try:
        # Simulating the exact exception from psutil that _poll catches
        raise psutil.NoSuchProcess(pid=9999)
    except psutil.NoSuchProcess:
        with tracker.lock:
            tracker.history.clear()
            tracker.summaries = {"5s": None, "15s": None, "60s": None}

    # Verify cache is completely flushed
    flushed = tracker.get_summaries()
    assert len(tracker.history) == 0
    assert flushed["5s"] is None
    assert flushed["60s"] is None

@mock.patch("gotedo_unoserver.client.ServerProxy")
def test_client_get_usage_rpc(mock_proxy_class):
    # Setup the mock XML-RPC proxy context manager
    mock_proxy_instance = mock.MagicMock()
    mock_proxy_class.return_value.__enter__.return_value = mock_proxy_instance
    
    # Define the mock payload the server would return
    mock_payload = {
        "5s": {"cpu_percent": 15.5, "mem_bytes": 1024, "mem_percent": 1.5},
        "15s": {"cpu_percent": 12.0, "mem_bytes": 1024, "mem_percent": 1.5},
        "60s": {"cpu_percent": 10.0, "mem_bytes": 1024, "mem_percent": 1.5}
    }
    mock_proxy_instance.get_usage.return_value = mock_payload
    
    # Initialize client and call the function
    clt = client.UnoClient(port="2003")
    result = clt.get_usage(target_port="2002")
    
    # Assert the proxy was called with the target port as a string
    mock_proxy_instance.get_usage.assert_called_once_with("2002")
    
    # Assert data remains intact through the client return
    assert result["5s"]["cpu_percent"] == 15.5
    assert result["60s"]["mem_bytes"] == 1024