"""Own Lua receiver tested with generated packets and a real local Windows pipe.

Uses the existing OBS LuaJIT library as an interpreter, without starting OBS or
loading its graphics engine. This does not validate composition inside OBS.
"""
import ctypes as C
import json
import os
from pathlib import Path
import struct
import threading
import time
import unittest
from ucs.frame_output import FrameOutput, FramePublisher, REQUEST, REPLY

ROOT = Path(__file__).resolve().parents[1]
LUA_DLL = Path('C:/Program Files/obs-studio/bin/64bit/lua51.dll')


class Lua:
    def __init__(self,transport='alpha_transport.lua'):
        self.dll = C.CDLL(str(LUA_DLL))
        for name, arguments, result in (
            ('luaL_newstate', [], C.c_void_p),
            ('luaL_openlibs', [C.c_void_p], None),
            ('luaL_loadbuffer', [C.c_void_p, C.c_char_p, C.c_size_t, C.c_char_p], C.c_int),
            ('lua_pcall', [C.c_void_p, C.c_int, C.c_int, C.c_int], C.c_int),
            ('lua_tolstring', [C.c_void_p, C.c_int, C.POINTER(C.c_size_t)], C.c_void_p),
            ('lua_pushlstring', [C.c_void_p, C.c_char_p, C.c_size_t], C.c_void_p),
            ('lua_setfield', [C.c_void_p, C.c_int, C.c_char_p], None),
            ('lua_settop', [C.c_void_p, C.c_int], None),
            ('lua_close', [C.c_void_p], None),
        ):
            function = getattr(self.dll, name)
            function.argtypes, function.restype = arguments, result
        self.state = self.dll.luaL_newstate()
        if not self.state:
            raise RuntimeError('Lua state unavailable')
        self.dll.luaL_openlibs(self.state)
        self.run('ffi=require("ffi"); transport=dofile(' + json.dumps(
            (ROOT/'integrations/obs'/transport).as_posix()) + ')')

    def error(self):
        size = C.c_size_t()
        pointer = self.dll.lua_tolstring(self.state, -1, C.byref(size))
        message = C.string_at(pointer, size.value).decode(errors='replace') if pointer else 'Lua error'
        self.dll.lua_settop(self.state, 0)
        raise AssertionError(message)

    def run(self, code, execute=True):
        data = code.encode()
        if self.dll.luaL_loadbuffer(self.state, data, len(data), b'own-generated-test'):
            self.error()
        if execute and self.dll.lua_pcall(self.state, 0, 0, 0):
            self.error()
        self.dll.lua_settop(self.state, 0)

    def binary(self, name, data):
        self.dll.lua_pushlstring(self.state, data, len(data))
        self.dll.lua_setfield(self.state, -10002, name.encode())

    def endpoint(self, value):
        literal = '{' + ','.join('[' + json.dumps(k) + ']=' + json.dumps(v)
                                 for k, v in value.items()) + '}'
        self.run('endpoint=' + literal + '; client=transport.new(endpoint)')

    def close(self):
        if self.state:
            try:
                self.run('if client then client:close() end')
            finally:
                self.dll.lua_close(self.state)
                self.state = None


@unittest.skipUnless(os.name == 'nt' and LUA_DLL.is_file(), 'requires existing Windows OBS LuaJIT')
class OwnOBSAlphaTransportTests(unittest.TestCase):
    def setUp(self):
        self.lua = Lua()

    def tearDown(self):
        self.lua.close()

    def endpoint(self, **change):
        import uuid
        from ucs.frame_pipe_windows import PipeServer
        name = '\\\\.\\pipe\\UCS.FrameBridge.' + str(uuid.uuid4())
        return dict(schema=1, alpha_mode='premultiplied', width=4, height=2,
                    pipe_name=name, producer_pid=os.getpid(), owner_sid=PipeServer(name).owner_sid,
                    epoch_hex='fffffffffedcba98', **change)

    def packet(self):
        out = FrameOutput(clock=lambda: 1., tick_ms=lambda: 1000,
                          epoch=0xfffffffffedcba98, formats=(3,))
        out.set_canvas(4, 2)
        request = REQUEST.pack(0x51534355, 1, 24, 3, 4, 2, 0)
        out.request(request, wait=0)
        pixels = bytes([0, 0, 0, 0, 30, 40, 50, 128, 40, 60, 80, 255, 0, 0, 0, 0])*2
        self.assertTrue(out.publish(4, 2, pixels, 1., 3))
        return out.request(request, wait=0), pixels

    def test_native_envelope_preserves_uint64_epoch_and_exact_rgba_pixels(self):
        self.lua.endpoint(self.endpoint())
        packet, pixels = self.packet()
        self.lua.binary('packet_bytes', packet)
        self.lua.binary('expected', pixels)
        self.lua.run('ffi.copy(client.buffer,packet_bytes,#packet_bytes); frame=client:validate(#packet_bytes,1100); '
                     'assert(frame and ffi.string(frame.pixels,32)==expected); assert(frame.stride==16)')

    def test_next_pending_buffer_never_overwrites_last_validated_frame(self):
        self.lua.endpoint(self.endpoint())
        packet, pixels = self.packet()
        self.lua.binary('packet_bytes', packet)
        self.lua.binary('expected', pixels)
        self.lua.run('ffi.copy(client.buffer,packet_bytes,#packet_bytes); frame=client:validate(#packet_bytes,1100); '
                     'ffi.fill(client.buffer,128,99); assert(ffi.string(frame.pixels,32)==expected)')

    def test_wrong_epoch_opaque_flags_future_expired_and_oversized_frames_are_rejected(self):
        packet, _ = self.packet()
        cases = []
        wrong_epoch = bytearray(packet)
        struct.pack_into('<Q', wrong_epoch, 24, 7)
        cases.append((bytes(wrong_epoch), 1100))
        opaque = bytearray(packet)
        struct.pack_into('<I', opaque, 92, 0)
        cases.extend(((bytes(opaque), 1100), (packet, 999), (packet, 1251), (packet[:-1], 1100)))
        bad_empty = REPLY.pack(0, 1, 0, 0, 0, 0, 0xfffffffffedcba98)
        cases.append((bad_empty, 1100))
        for data, now in cases:
            self.lua.run('if client then client:close() end')
            self.lua.endpoint(self.endpoint())
            self.lua.binary('packet_bytes', data)
            self.lua.run(f'ffi.copy(client.buffer,packet_bytes,#packet_bytes); '
                         f'assert(client:validate(#packet_bytes,{now})==nil); assert(client.error ~= nil)')

    def test_remote_endpoints_and_large_or_wrong_alpha_modes_are_refused_before_io(self):
        self.lua.endpoint(self.endpoint())
        self.lua.run('client:close(); '
                     'endpoint.pipe_name="\\\\\\\\remote\\\\pipe\\\\camera"; assert(not pcall(transport.new,endpoint)); '
                     'endpoint.pipe_name="\\\\\\\\.\\\\pipe\\\\UCS.FrameBridge.00000000-0000-0000-0000-000000000000"; '
                     'endpoint.width=16384; endpoint.height=16384; assert(not pcall(transport.new,endpoint)); '
                     'endpoint.width=4; endpoint.height=2; endpoint.alpha_mode="opaque"; assert(not pcall(transport.new,endpoint))')

    def test_real_windows_pipe_and_lua_receiver_preserve_generated_alpha_and_expire(self):
        publisher = FramePublisher(epoch=0xfffffffffedcba98, formats=(3,))
        publisher.set_canvas(4, 2)
        end = threading.Event()
        pixels = self.packet()[1]
        endpoint = publisher.endpoint()
        self.lua.endpoint({k: endpoint[k] for k in ('schema', 'pipe_name', 'producer_pid', 'epoch_hex',
                                                   'owner_sid', 'width', 'height', 'alpha_mode')})
        self.lua.binary('expected', pixels)

        def feed():
            while not end.wait(.003):
                if publisher.wanted():
                    publisher.publish(4, 2, pixels, time.perf_counter(), 3)

        worker = threading.Thread(target=feed)
        worker.start()
        try:
            self.lua.run('received=0')
            for _ in range(120):
                self.lua.run('local frame=client:poll(); if frame then '
                             'assert(ffi.string(frame.pixels,32)==expected); received=received+1 end')
                time.sleep(.003)
            self.lua.run('assert(received>=5); assert(client:fresh()); assert(client.error==nil)')
            end.set()
            worker.join(1)
            time.sleep(.35)
            self.lua.run('assert(client:fresh())')
            time.sleep(.75)
            self.lua.run('assert(not client:fresh())')
        finally:
            end.set()
            worker.join(1)
            self.lua.run('client:close()')
            publisher.close()
        self.assertEqual(publisher.server, None)

    def test_wrong_server_pid_is_refused_and_own_obs_module_has_valid_lua_syntax(self):
        publisher = FramePublisher(formats=(3,))
        publisher.set_canvas(4, 2)
        endpoint = publisher.endpoint()
        value = {k: endpoint[k] for k in ('schema', 'pipe_name', 'producer_pid', 'epoch_hex',
                                        'owner_sid', 'width', 'height', 'alpha_mode')}
        value['producer_pid'] += 1
        try:
            self.lua.endpoint(value)
            self.lua.run('assert(client:poll()==nil); assert(client.error ~= nil); assert(not client:fresh())')
        finally:
            self.lua.run('client:close()')
            publisher.close()
        self.lua.run((ROOT/'integrations/obs/smb-camera.lua').read_text(encoding='utf-8'), execute=False)
