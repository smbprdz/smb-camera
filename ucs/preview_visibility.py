"""Thread-safe presentation intent. Tk is only queried by its UI thread."""
import threading

class PreviewVisibility:
    def __init__(self):self.lock=threading.Lock();self.visible=True
    def set_visible(self,value):
        if type(value) is not bool:raise ValueError('Invalid preview visibility')
        with self.lock:self.visible=value
    def is_visible(self):
        with self.lock:return self.visible
