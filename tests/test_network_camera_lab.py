import struct,unittest
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from tools.network_camera_lab import NetworkCameraLab,h264_rtp,nals,parse_xml,envelope,SOAP,TDS,TRT

class NetworkCameraPacketTests(unittest.TestCase):
    def test_single_nal_rtp_preserves_nal_bytes_and_90khz_timestamp(self):
        payload=b'\x00\x00\x00\x01\x67ABC'+b'\x00\x00\x01\x65DEF'
        packets=list(h264_rtp(payload,65535,90000,123));self.assertEqual(len(packets),2)
        self.assertEqual(struct.unpack('!BBHII',packets[0][:12]),(128,96,65535,90000,123))
        self.assertEqual(struct.unpack('!BBHII',packets[1][:12]),(128,224,0,90000,123))
        self.assertEqual([p[12:] for p in packets],[b'\x67ABC',b'\x65DEF'])
    def test_fragmentation_reconstructs_exact_nal_and_marks_only_last_fragment(self):
        nal=b'\x65'+bytes(range(256))*20;packets=list(h264_rtp(b'\0\0\0\1'+nal,7,0xffffffff+1,123,mtu=1200))
        self.assertGreater(len(packets),1);self.assertTrue(all(len(p)<=1212 for p in packets))
        actual=bytes([(packets[0][12]&0xe0)|(packets[0][13]&31)])+b''.join(p[14:] for p in packets)
        self.assertEqual(actual,nal);self.assertTrue(packets[0][13]&128);self.assertTrue(packets[-1][13]&64)
        self.assertTrue(all(not p[1]&128 for p in packets[:-1]));self.assertTrue(packets[-1][1]&128)
        self.assertTrue(all(struct.unpack('!I',p[4:8])[0]==0 for p in packets))
    def test_malformed_xml_and_allocation_bounds_are_rejected(self):
        for value in (b'<!DOCTYPE x><x/>',b'<!ENTITY a "value"><x/>',b' '*65537):
            with self.assertRaises(ValueError):parse_xml(value)
        for mtu in (1,1500):
            with self.assertRaises(ValueError):list(h264_rtp(b'\0\0\1\x65abc',0,0,1,mtu))
    def test_service_capabilities_are_included_only_when_requested_and_reply_is_correlated(self):
        fixture=b'\0\0\0\1\x67\x42\0\x1f\0\0\1\x68AB'
        lab=NetworkCameraLab('127.0.0.1',[(fixture,0)],b'generated-only')
        lab.http=SimpleNamespace(server_port=12001)
        lab.rtsp=SimpleNamespace(server_address=('127.0.0.1',12002))
        address='http://www.w3.org/2005/08/addressing'
        for include in ('true','false'):
            request=envelope('<tds:GetServices><tds:IncludeCapability>'+include+'</tds:IncludeCapability></tds:GetServices>',f'<a:MessageID xmlns:a="{address}">urn:uuid:example-request</a:MessageID>')
            response=ET.fromstring(lab.soap(request))
            services=response.findall('.//{'+TDS+'}Service')
            self.assertEqual(len(services),2)
            self.assertEqual(response.find('.//{'+address+'}RelatesTo').text,'urn:uuid:example-request')
            self.assertEqual(response.find('.//{'+address+'}Action').text,TDS+'/GetServicesResponse')
            for service in services:
                capability=service.find('{'+TDS+'}Capabilities')
                if include=='true':
                    self.assertIsNotNone(capability)
                    self.assertEqual(len(capability),1)
                    namespace=service.find('{'+TDS+'}Namespace').text
                    self.assertEqual(capability[0].tag,'{'+namespace+'}Capabilities')
                else:self.assertIsNone(capability)
