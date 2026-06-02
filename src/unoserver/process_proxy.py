class ExistingProcessProxy:
    """
    A duck-typed proxy that mimics a subprocess.Popen object for a process 
    spawned by a previous Python invocation.
    """
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        import os
        try:
            os.kill(self.pid, 0)
            return None  # Still running
        except ProcessLookupError:
            self.returncode = 0  # Process has exited
            return self.returncode
        except PermissionError:
            return None  # Running, but owned by another user

    def wait(self, timeout=None):
        import time
        start_time = time.time()
        # We cannot use os.waitpid() because this process is not our child. 
        # We must poll the OS to check if it has exited.
        while self.poll() is None:
            if timeout is not None and (time.time() - start_time) > timeout:
                import subprocess
                raise subprocess.TimeoutExpired(cmd="attached_libreoffice", timeout=timeout)
            time.sleep(0.5)
        return self.returncode

    def send_signal(self, sig):
        import os
        try:
            os.kill(self.pid, sig)
        except ProcessLookupError:
            pass  # Already dead

    def terminate(self):
        import signal
        self.send_signal(signal.SIGTERM)

    def kill(self):
        import signal
        self.send_signal(signal.SIGKILL)