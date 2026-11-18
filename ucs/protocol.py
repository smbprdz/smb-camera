"""Independent UCS1 reference codec. All integers are network byte order."""
from dataclasses import dataclass
import json
import struct

HEADER = struct.Struct('!4sBBHIQQI')
HELLO, ACCEPT, VIDEO, PING, PONG, STOP = range(1, 7)
CAPS,CONTROL,RESULT=7,8,9
AUDIO, MIC, MIC_ERROR = 10, 11, 12
MAX_VIDEO = 4 * 1024 * 1024
MAX_CONTROL = 64 * 1024

class ProtocolError(ValueError):
    pass

@dataclass(frozen=True)
class Message:
    kind: int
    payload: bytes = b''
    seq: int = 0
    pts_us: int = 0
    flags: int = 0

def validate(kind, flags, size, reserved=0):
    if kind not in range(1, 13) or reserved or flags & ~1 or (kind != VIDEO and flags):
        raise ProtocolError('invalid type, flags or reserved field')
    if size > (MAX_VIDEO if kind == VIDEO else MAX_CONTROL):
        raise ProtocolError('payload too large')
    if kind == MIC and size != 1 or kind == MIC_ERROR and size != 0:
        raise ProtocolError('invalid microphone control length')
    if kind == AUDIO and size < 8:
        raise ProtocolError('empty audio')
    if kind == VIDEO and not size:
        raise ProtocolError('empty video')

def pcm_format(payload):
    rate, channels = struct.unpack_from('!IH', payload)
    if rate not in (44100, 48000) or channels not in (1, 2) or (len(payload)-6) % (2*channels):
        raise ProtocolError('invalid PCM format')
    return rate, channels

def encode(msg):
    validate(msg.kind, msg.flags, len(msg.payload))
    return HEADER.pack(b'UCS1', 1, msg.kind, msg.flags, len(msg.payload),
                       msg.seq, msg.pts_us, 0) + msg.payload

def exact(sock, size):
    data = bytearray(size)
    view = memoryview(data)
    offset = 0
    while offset < size:
        n = sock.recv_into(view[offset:])
        if not n:
            raise EOFError('peer closed before message completed')
        offset += n
    return bytes(data)

def receive(sock):
    magic, version, kind, flags, size, seq, pts, reserved = HEADER.unpack(exact(sock, HEADER.size))
    if magic != b'UCS1' or version != 1:
        raise ProtocolError('unsupported magic/version')
    validate(kind, flags, size, reserved)
    return Message(kind, exact(sock, size), seq, pts, flags)

def json_message(kind, obj):
    return Message(kind, json.dumps(obj, separators=(',', ':'), allow_nan=False).encode())

def read_json(msg):
    try:
        obj = json.loads(msg.payload)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError('invalid JSON') from exc
    if not isinstance(obj, dict):
        raise ProtocolError('expected object')
    return obj

def validate_stream(obj):
    if obj.get('codec') != 'h264' or obj.get('pixel_format') != 'yuv420p' or obj.get('color') != 'bt709-sdr':
        raise ProtocolError('bench supports H.264 8-bit 4:2:0 BT.709 SDR only')
    for key, maximum in [('width', 8192), ('height', 8192), ('fps', 240)]:
        n = obj.get(key)
        if type(n) is not int or not 1 <= n <= maximum:
            raise ProtocolError('invalid ' + key)
    if obj['width'] % 2 or obj['height'] % 2:
        raise ProtocolError('4:2:0 requires even dimensions')
    return {k: obj[k] for k in ('codec', 'width', 'height', 'fps', 'pixel_format', 'color')}
