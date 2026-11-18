import unittest
from ucs.desktop import Desktop

class Widget:
    def __init__(self):self.values={};self.calls=[];self.value=0
    def configure(self,**values):self.calls.append(values);self.values.update(values)
    def get(self):return self.value
    def set(self,value):self.value=value

class DesktopUpdateTests(unittest.TestCase):
    def test_disconnect_then_reconnect_reenables_the_camera_controls(self):
        from types import SimpleNamespace
        from test_controls import caps
        desktop=Desktop.__new__(Desktop);desktop.widget_properties={}
        for key in ('zoom','focus','focus_auto','control_status','zoom_label','focus_label','exposure_bias','exposure_label','sensor_label'):setattr(desktop,key,Widget())
        desktop.lens=SimpleNamespace(set_capabilities=lambda _:None)
        desktop.pending_zoom=desktop.pending_focus=desktop.pending_exposure_bias=None;desktop.slider_values={};desktop.controls_revision=None
        desktop.auto_focus=Widget();snapshot={'caps':caps(),'status':'Confirmed','busy':False}
        desktop.controls=SimpleNamespace(snapshot=lambda:snapshot)
        desktop.refresh_controls();self.assertEqual(desktop.zoom.values['state'],'normal')
        snapshot['caps']=None;desktop.refresh_controls();self.assertEqual(desktop.zoom.values['state'],'disabled')
        snapshot['caps']=caps();desktop.refresh_controls();self.assertEqual(desktop.zoom.values['state'],'normal')
    def test_identical_poll_does_not_reconfigure_labels_or_controls(self):
        desktop=Desktop.__new__(Desktop);desktop.widget_properties={};widget=Widget()
        desktop.update_widget(widget,text='Camera conectada',state='normal')
        for _ in range(100):desktop.update_widget(widget,text='Camera conectada',state='normal')
        self.assertEqual(len(widget.calls),1)
        desktop.update_widget(widget,text='Camera desconectada',state='disabled')
        self.assertEqual(len(widget.calls),2);self.assertEqual(widget.values['state'],'disabled')
    def test_mixed_range_and_state_updates_cannot_leave_a_control_enabled(self):
        desktop=Desktop.__new__(Desktop);desktop.widget_properties={};widget=Widget()
        desktop.update_widget(widget,state='disabled')
        desktop.update_widget(widget,from_=1,to=3,state='normal')
        desktop.update_widget(widget,state='disabled')
        self.assertEqual(widget.values,{'state':'disabled','from_':1,'to':3})
        self.assertEqual(len(widget.calls),3)
