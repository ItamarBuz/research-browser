import subprocess
import sys
import threading

from rb_engine.runtime.watchdog import watch_parent


def test_fires_when_parent_exits() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    fired = threading.Event()

    watch_parent(child.pid, fired.set, interval_s=0.05)
    child.wait()

    assert fired.wait(timeout=5)
