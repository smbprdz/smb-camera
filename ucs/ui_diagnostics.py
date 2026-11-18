"""Opt-in numeric UI timing. No capture, text fields, identity or pairing values."""
from collections import deque
from functools import wraps
import threading,time

class UIDiagnostics:
    def __init__(self,enabled=False,clock=time.perf_counter):
        self.enabled=enabled;self.clock=clock;self.lock=threading.Lock()
        self.poll=deque(maxlen=120);self.heartbeat=deque(maxlen=120);self.navigation=deque(maxlen=64)
    def record(self,kind,milliseconds):
        if self.enabled:
            with self.lock:getattr(self,kind).append(max(0,milliseconds))
    def start_navigation(self):return self.clock() if self.enabled else None
    def finish_navigation(self,started):
        if started is not None:self.record('navigation',(self.clock()-started)*1000)
    def snapshot(self):
        if not self.enabled:return {}
        def stats(values):
            values=sorted(values)
            return {'count':len(values),'p95_ms':round(values[int((len(values)-1)*.95)],3) if values else None,
                    'max_ms':round(max(values),3) if values else None}
        with self.lock:return {'ui_diagnostics':{'poll':stats(self.poll),'heartbeat_late':stats(self.heartbeat),'navigation_to_idle':stats(self.navigation)}}

def measure_poll(function):
    @wraps(function)
    def measured(self):
        if not self.diagnostics.enabled:return function(self)
        before=self.diagnostics.clock()
        try:return function(self)
        finally:self.diagnostics.record('poll',(self.diagnostics.clock()-before)*1000)
    return measured
