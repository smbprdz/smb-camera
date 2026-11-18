import heapq,os,unittest
from ucs.desktop import Desktop
from ucs.controls import ControlBus
from ucs.protocol import read_json
from test_controls import caps

class Scheduler:
    def __init__(self):self.now=0;self.counter=0;self.jobs=[];self.cancelled=set()
    def after(self,delay,callback):
        self.counter+=1;heapq.heappush(self.jobs,(self.now+delay,self.counter,callback));return self.counter
    def after_cancel(self,id):self.cancelled.add(id)
    def advance(self,milliseconds):
        target=self.now+milliseconds
        while self.jobs and self.jobs[0][0]<=target:
            at,id,callback=heapq.heappop(self.jobs);self.now=at
            if id not in self.cancelled:callback()
        self.now=target

def controller(bus=None):
    item=Desktop.__new__(Desktop);item.root=Scheduler();item.closing=False;item.applying_controls=False
    item.pending_zoom=item.pending_focus=None;item.slider_values={};item.events=[]
    class Bus:
        def enqueue(self,key,value):item.events.append((item.root.now,key,value));return True
    item.controls=bus or Bus();return item

class SliderDispatchTests(unittest.TestCase):
    def test_continuous_drag_sends_before_release_and_keeps_the_final_value(self):
        item=controller();item.zoom_changed('1.1')
        self.assertEqual(item.events,[(0,'zoom',1.1)])
        for step in range(1,51):
            item.root.advance(20);item.zoom_changed(str(1.1+step/50))
        self.assertGreater(len(item.events),5) # Updates occurred while dragging.
        item.root.advance(200)
        self.assertEqual(item.events[-1][2],2.1);self.assertLessEqual(len(item.events),12)
        self.assertTrue(all(b[0]-a[0]>=100 for a,b in zip(item.events,item.events[1:])))
    def test_stopped_controller_cannot_dispatch_the_trailing_value(self):
        item=controller();item.zoom_changed('1.2');item.zoom_changed('2');item.closing=True;item.root.advance(300)
        self.assertEqual(len(item.events),1)
    def test_slow_phone_keeps_one_pending_zoom_while_dragging(self):
        bus=ControlBus();bus.begin('a'*32);bus.update(caps());item=controller(bus)
        item.zoom_changed('1.1');sent=read_json(bus.next_message(now=0))
        for step in range(100):
            item.root.advance(10);item.zoom_changed(str(1.1+step*.01))
            self.assertLessEqual(len(bus.pending),1);self.assertIsNone(bus.next_message(now=item.root.now/1000))
        item.root.advance(200)
        self.assertEqual(len(bus.pending),1);self.assertAlmostEqual(bus.pending['zoom'][0],2.09)
        self.assertEqual(bus.in_flight['request'],sent['request'])

@unittest.skipUnless(os.environ.get('UCS_TEST_GPU')=='1','requires a local Windows UI session')
class SliderResetTests(unittest.TestCase):
    def tearDown(self):
        # Destroyed Tk interpreters/widgets may retain Python callback cycles.
        # Collect them on their creating thread before later threaded tests run.
        import gc
        gc.collect()
    def test_lens_buttons_reflect_confirmation_and_disable_unsupported_modes(self):
        import tkinter as tk
        from ucs.studio_theme import LensButtons
        root=tk.Tk();root.withdraw();selected=[]
        try:
            widget=LensButtons(root,selected.append);capabilities=caps();widget.set_capabilities(capabilities)
            widget.buttons['front'].invoke();self.assertEqual(selected,['front'])
            self.assertEqual(widget.selected_id,'wide') # Selection only changes on confirmation.
            widget.buttons['ultra'].invoke();self.assertEqual(selected,['front'])
            capabilities['active']='front';widget.set_capabilities(capabilities);self.assertEqual(widget.selected_id,'front')
            children=widget.row.winfo_children()
            for _ in range(100):widget.set_capabilities(capabilities)
            self.assertEqual(widget.row.winfo_children(),children)
            widget.set_capabilities(None);widget.buttons['wide'].invoke();self.assertEqual(selected,['front'])
        finally:root.destroy()
    def test_unchanged_poll_does_not_recreate_native_canvas_items(self):
        import tkinter as tk
        from ucs.studio_theme import Slider,NavButton
        root=tk.Tk();root.withdraw()
        try:
            slider=Slider(root);slider.set(.5);items=slider.find_all()
            for _ in range(100):slider.configure(state='normal');slider.set(.5)
            self.assertEqual(slider.find_all(),items)
            nav=NavButton(root,'Cor','☷',lambda:None);nav.draw();items=nav.find_all()
            for _ in range(100):nav.draw()
            self.assertEqual(nav.find_all(),items)
        finally:root.destroy()
    def test_double_click_reset_obeys_each_default_and_disabled_camera(self):
        import tkinter as tk
        from ucs.studio_theme import Slider
        from ucs.color import ColorState,PARAMETERS
        root=tk.Tk();root.withdraw();state=ColorState()
        try:
            for key,(default,low,high) in PARAMETERS.items():
                widget=Slider(root,from_=low,to=high,default=default,command=lambda value,key=key:state.set(**{key:float(value)}))
                widget.set(high);self.assertTrue(widget.bind('<Double-Button-1>'));widget.reset()
                self.assertEqual(state.get()[key],default);widget.destroy()
            events=[];widget=Slider(root,from_=1,to=5,command=events.append)
            widget.set(4);widget.reset();self.assertEqual(widget.get(),1)
            widget.configure(state='disabled');widget.set(3);count=len(events);widget.reset()
            self.assertEqual(widget.get(),3);self.assertEqual(len(events),count)
        finally:root.destroy()
