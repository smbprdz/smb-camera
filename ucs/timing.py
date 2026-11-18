"""Negotiated timing-v1 over existing PING/PONG. All units explicitly named."""
import math
import struct
from .protocol import ProtocolError

def pong_timestamps(receive_us,send_us):
    if not 0 <= receive_us <= send_us < 2**64:
        raise ProtocolError('invalid local clock sample')
    return struct.pack('!QQ',receive_us,send_us)

def phone_metrics(obj):
    if not isinstance(obj,dict):raise ProtocolError('expected phone timing object')
    out={}
    numeric={'clock_offset_us':(-1e18,1e18),'clock_uncertainty_us':(0,2_500_000),
             'encoder_p95_ms':(0,60_000),'capture_callback_age_p95_ms':(0,60_000),
             'capture_skipped':(0,2**53),'capture_callbacks':(0,2**53),'thermal_state':(0,3)}
    for key,(lo,hi) in numeric.items():
        if key not in obj:continue
        value=obj[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
            raise ProtocolError('invalid phone timing metric')
        out[key]=value
    policy=obj.get('encoder_policy')
    if policy in ('hardware-low-latency','hardware-realtime','default'):
        out['encoder_policy']=policy
    unsupported=obj.get('unsupported_properties')
    if isinstance(unsupported,list) and len(unsupported)<=16 and all(isinstance(x,str) and len(x)<=128 for x in unsupported):
        out['unsupported_properties']=unsupported
    return out

def receive_age(receive_us,pts_us,metrics):
    offset=metrics.get('clock_offset_us');error=metrics.get('clock_uncertainty_us')
    if offset is None or error is None or error>100_000:return {}
    age=(receive_us-(pts_us+offset))/1000
    if age < -error/1000-5 or age>60_000:return {}
    return {'capture_to_receive_estimate_ms':round(age,2),
            'clock_uncertainty_ms':round(error/1000,2)}
