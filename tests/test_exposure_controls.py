import copy,unittest
from types import SimpleNamespace
from test_controls import caps,SESSION
from test_desktop_updates import Widget
from test_slider_controls import controller
from ucs.controls import ControlBus,capabilities
from ucs.desktop import Desktop
from ucs.protocol import ProtocolError,read_json

def exposure_caps():
    value=caps();value['exposure_bias']={'min':-2,'max':2}
    value['state'].update(exposure_bias=.25,sensor_iso=100,sensor_exposure_us=16666.7)
    return value

class ExposureTests(unittest.TestCase):
    def test_legacy_phone_keeps_old_controls_but_cannot_enqueue_exposure(self):
        bus=ControlBus();bus.begin(SESSION);bus.update(caps())
        self.assertFalse(bus.enqueue('exposure_bias',1));self.assertTrue(bus.enqueue('zoom',2))
        self.assertIsNone(bus.snapshot()['caps']['exposure_bias'])
    def test_device_limits_coalescing_and_applied_reading(self):
        bus=ControlBus();bus.begin(SESSION);bus.update(exposure_caps())
        for value in (True,float('nan'),float('inf'),-2.1,2.1):
            with self.assertRaises(ProtocolError):bus.enqueue('exposure_bias',value)
        for index in range(1000):bus.enqueue('exposure_bias',(index%400)/100-2)
        self.assertEqual(len(bus.pending),1);sent=read_json(bus.next_message(now=0))
        self.assertEqual(bus.snapshot()['caps']['state']['exposure_bias'],.25)
        state=exposure_caps()['state'];state.update(exposure_bias=.75,sensor_iso=120)
        bus.result(dict(session=SESSION,revision=1,request=sent['request'],status='applied',state=state))
        self.assertEqual(bus.snapshot()['caps']['state']['exposure_bias'],.75)
        self.assertEqual(bus.snapshot()['caps']['state']['sensor_iso'],120)
    def test_malformed_capability_or_readings_fail_without_changing_state(self):
        for change in ({'min':3,'max':2},{'min':True,'max':2},{'min':-2,'max':float('inf')},{'min':-2,'max':2,'extra':0}):
            value=exposure_caps();value['exposure_bias']=change
            with self.assertRaises(ProtocolError):capabilities(value,SESSION)
        for key,value in [('exposure_bias',3),('sensor_iso',0),('sensor_exposure_us',-1)]:
            data=exposure_caps();data['state'][key]=value
            with self.assertRaises(ProtocolError):capabilities(data,SESSION)
    def test_exposure_drag_is_coalesced_before_release(self):
        item=controller();item.pending_exposure_bias=None
        item.exposure_bias_changed('.5');self.assertEqual(item.events[0],(0,'exposure_bias',.5))
        for index in range(20):item.root.advance(10);item.exposure_bias_changed(str(index/10))
        item.root.advance(200);self.assertEqual(item.events[-1][2],1.9);self.assertLessEqual(len(item.events),4)
    def test_exposure_ui_confirms_reading_and_disables_on_old_phone_or_disconnect(self):
        desktop=Desktop.__new__(Desktop);desktop.widget_properties={};desktop.applying_controls=False
        for key in ('zoom','focus','focus_auto','control_status','zoom_label','focus_label','exposure_bias','exposure_label','sensor_label'):setattr(desktop,key,Widget())
        desktop.lens=SimpleNamespace(set_capabilities=lambda _:None);desktop.auto_focus=Widget()
        desktop.pending_zoom=desktop.pending_focus=desktop.pending_exposure_bias=None;desktop.slider_values={};desktop.controls_revision=None
        state={'caps':capabilities(exposure_caps(),SESSION),'status':'Confirmed','busy':False};desktop.controls=SimpleNamespace(snapshot=lambda:state)
        desktop.refresh_controls();self.assertEqual(desktop.exposure_bias.get(),.25);self.assertEqual(desktop.exposure_bias.values['state'],'normal')
        self.assertIn('100',desktop.sensor_label.values['text'])
        legacy=caps();legacy['revision']=2;state['caps']=capabilities(legacy,SESSION);desktop.refresh_controls()
        self.assertEqual(desktop.exposure_bias.values['state'],'disabled');self.assertEqual(desktop.sensor_label.values['text'],'')
        state['caps']=None;desktop.refresh_controls();self.assertEqual(desktop.exposure_bias.values['state'],'disabled')
