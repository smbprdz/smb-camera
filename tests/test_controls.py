import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from ucs.controls import ControlBus,capabilities
from ucs.protocol import *
from ucs.receiver import serve_session
from test_protocol import Fragmented

SESSION='a'*32
def caps(session=SESSION,revision=1,active='wide'):
    return dict(session=session,revision=revision,active=active,
        cameras=[dict(id='wide',label='Wide',available=True),dict(id='front',label='Front',available=True),
                 dict(id='ultra',label='Ultra',available=False)],zoom_min=1,zoom_max=5,
        focus_auto_supported=True,focus_manual_supported=True,
        state=dict(zoom=1,focus=.5,focus_mode='auto'))

class ControlTests(unittest.TestCase):
    def setup_bus(self):
        bus=ControlBus();bus.begin(SESSION);bus.update(caps());return bus
    def test_slider_queue_is_bounded_and_coalesces(self):
        bus=self.setup_bus()
        for n in range(1000):bus.enqueue('zoom',1+(n%400)/100)
        message=bus.next_message(now=1)
        self.assertEqual(read_json(message)['value'],2.99)
        self.assertIsNone(bus.next_message(now=2))
        self.assertEqual(len(bus.pending),0)
    def test_only_confirmed_values_update_applied_state(self):
        bus=self.setup_bus();bus.enqueue('zoom',2.5);sent=read_json(bus.next_message(now=1))
        self.assertEqual(bus.snapshot()['caps']['state']['zoom'],1)
        result=dict(session=SESSION,request=sent['request'],revision=1,status='applied',state=dict(zoom=2.49,focus=.5,focus_mode='auto'))
        bus.result(result)
        self.assertEqual(bus.snapshot()['caps']['state']['zoom'],2.49)
    def test_stale_result_cannot_revive_previous_session(self):
        bus=self.setup_bus();bus.enqueue('zoom',2);sent=read_json(bus.next_message(now=1));bus.close();bus.begin('c'*32)
        self.assertFalse(bus.result(dict(session=SESSION,request=sent['request'],status='applied')))
        self.assertIsNone(bus.snapshot()['caps']);self.assertIsNone(bus.next_message(now=2))
    def test_revision_change_discards_queued_slider_values(self):
        bus=self.setup_bus();bus.enqueue('lens','front');sent=read_json(bus.next_message(now=1));bus.enqueue('zoom',3)
        bus.update(caps(revision=2,active='front'))
        bus.result(dict(session=SESSION,request=sent['request'],revision=2,status='applied',active='front',state=caps()['state']))
        self.assertIsNone(bus.next_message(now=2));self.assertEqual(bus.snapshot()['caps']['active'],'front')
    def test_invalid_unsupported_and_timeout_do_not_apply_values(self):
        bus=self.setup_bus()
        for value in [True,float('inf'),float('nan'),0,6]:
            with self.assertRaises(ProtocolError):bus.enqueue('zoom',value)
        self.assertFalse(bus.enqueue('lens','ultra'))
        bus.enqueue('zoom',2);bus.next_message(now=1);bus.enqueue('focus',.4)
        self.assertIsNone(bus.next_message(now=7));self.assertIsNone(bus.next_message(now=8))
        self.assertEqual(bus.snapshot()['caps']['state']['zoom'],1)
        invalid=caps();invalid['cameras'].append(copy.deepcopy(invalid['cameras'][0]))
        with self.assertRaises(ProtocolError):capabilities(invalid,SESSION)
        with self.assertRaises(ProtocolError):bus.update(caps(session='wrong'))
    def test_rejected_command_keeps_applied_state(self):
        bus=self.setup_bus();bus.enqueue('focus',.1);sent=read_json(bus.next_message(now=1))
        bus.result(dict(session=SESSION,request=sent['request'],revision=1,status='rejected',reason='unsupported'))
        self.assertEqual(bus.snapshot()['caps']['state']['focus'],.5)

    def test_negotiated_session_dispatch_and_confirmation_use_same_connection(self):
        bus=ControlBus()
        class Sink:
            failure=None
            def __init__(self,folder,*args):self.folder=folder
            def close(self):
                (self.folder/'decoded.framemd5').write_text('#dimensions 0: 1920x1080\n')
                return 0
        class Phone:
            def __init__(self):
                hello=dict(token='d'*64,codec='h264',width=1920,height=1080,fps=30,pixel_format='yuv420p',color='bt709-sdr',controls=1)
                self.buffer=bytearray(encode(json_message(HELLO,hello)));self.applied=False;self.command=None
            def settimeout(self,n):pass
            def recv_into(self,view):
                if not self.buffer:return 0
                size=min(len(view),len(self.buffer),11);view[:size]=self.buffer[:size];del self.buffer[:size];return size
            def sendall(self,data):
                msg=receive(Fragmented(data))
                if msg.kind==ACCEPT:
                    session=read_json(msg)['session'];self.session=session
                    self.buffer.extend(encode(json_message(CAPS,caps(session))))
                    original=bus.update
                    def update(value):original(value);bus.enqueue('zoom',2)
                    bus.update=update
                elif msg.kind==CONTROL:
                    cmd=read_json(msg);self.command=cmd
                    self.buffer.extend(encode(json_message(RESULT,dict(session=self.session,request=cmd['request'],revision=1,
                        status='applied',state=dict(zoom=2,focus=.5,focus_mode='auto')))))
                    self.buffer.extend(encode(Message(STOP)))
                    original=bus.result
                    def result(value):
                        applied=original(value);self.applied=bus.snapshot()['caps']['state']['zoom']==2;return applied
                    bus.result=result
        with tempfile.TemporaryDirectory() as tmp,patch('ucs.receiver.DecodeSink',Sink):
            phone=Phone();serve_session(phone,'d'*64,tmp,control_bus=bus)
        self.assertTrue(phone.applied);self.assertEqual(phone.command['control'],'zoom')
        self.assertIsNone(bus.snapshot()['caps'])

if __name__=='__main__':unittest.main()
