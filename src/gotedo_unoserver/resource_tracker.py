import threading
import time
import os
import tempfile
import psutil
from collections import deque
import logging

logger = logging.getLogger("unoserver")

class ResourceTracker:
    def __init__(self):
        # 12 samples * 5s = 60 seconds max capacity
        self.history = deque(maxlen=12)
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
        # Pre-computed object ready for immediate RPC retrieval
        self.summaries = {
            "5s": None,
            "15s": None,
            "60s": None
        }

    def start(self, port):
        self.running = True
        self.thread = threading.Thread(target=self._poll, args=(port,), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _poll(self, port):
        pid_file_path = os.path.join(tempfile.gettempdir(), f"unoserver_{port}.pid")
        process = None
        
        while self.running:
            try:
                if os.path.exists(pid_file_path):
                    with open(pid_file_path, "rt") as f:
                        pid = int(f.read().strip())
                    
                    # Initialize or re-initialize process tracking
                    if process is None or process.pid != pid:
                        process = psutil.Process(pid)
                        # Prime the CPU tracker (first call with interval=None returns 0.0)
                        process.cpu_percent(interval=None) 
                    
                    mem_info = process.memory_info()
                    
                    sample = {
                        'cpu_percent': process.cpu_percent(interval=None),
                        'mem_bytes': mem_info.rss, # Resident Set Size in bytes
                        'mem_percent': process.memory_percent()
                    }
                    
                    with self.lock:
                        self.history.append(sample)
                        self._aggregate_summaries()

            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, FileNotFoundError) as e:
                # Process died or pid file is invalid
                process = None
                with self.lock:
                    self.history.clear()
                    self.summaries = {"5s": None, "15s": None, "60s": None}
                logger.debug(f"Telemetry tracker error (process likely dead): {e}")
            
            time.sleep(5)
            
    def _aggregate_summaries(self):
        """Calculates averages and stores them in the static object. Must be called within a lock."""
        samples = list(self.history)
        if not samples:
            self.summaries = {"5s": None, "15s": None, "60s": None}
            return

        def calculate_avg(num_samples):
            slice_samples = samples[-num_samples:]
            if not slice_samples:
                return None
            
            count = len(slice_samples)
            return {
                'cpu_percent': sum(s['cpu_percent'] for s in slice_samples) / count,
                'mem_bytes': sum(s['mem_bytes'] for s in slice_samples) / count,
                'mem_percent': sum(s['mem_percent'] for s in slice_samples) / count
            }

        # 1 sample = 5s, 3 samples = 15s, 12 samples = 60s
        self.summaries["5s"] = calculate_avg(1)    
        self.summaries["15s"] = calculate_avg(3)   
        self.summaries["60s"] = calculate_avg(12)  

    def get_summaries(self):
        """RPC Getter - Returns the pre-computed dictionary instantly."""
        with self.lock:
            return self.summaries