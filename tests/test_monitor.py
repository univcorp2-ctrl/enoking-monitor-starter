from src import monitor


def test_legacy_monitor_entrypoint_imports():
    assert callable(monitor.main)
