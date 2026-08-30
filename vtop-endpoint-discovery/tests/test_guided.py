from __future__ import annotations

from unittest.mock import MagicMock
from vtop_discovery.capture.network import NetworkCapture


def test_network_capture_phase_tagging():
    mock_context = MagicMock()
    capture = NetworkCapture(mock_context)

    assert capture.active_purpose is None

    capture.start_phase("attendance")
    assert capture.active_purpose == "attendance"

    capture.stop_phase()
    assert capture.active_purpose is None
