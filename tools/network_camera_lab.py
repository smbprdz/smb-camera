"""Generated-video ONVIF/RTSP tooling experiment, excluded from the app engine.

Only tools/probe_network_camera.py constructs this service, with generated
H.264/JPEG. No phone, microphone, recording, driver install or firewall changes.
HTTP/RTSP accept local-machine clients only; discovery exposes metadata only.
"""
import base64,datetime,ipaddress,json,re,secrets,socket,socketserver,struct,threading,time,uuid
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from xml.sax.saxutils import escape

SOAP='http://www.w3.org/2003/05/soap-envelope'
TDS='http://www.onvif.org/ver10/device/wsdl';TRT='http://www.onvif.org/ver10/media/wsdl'
TT='http://www.onvif.org/ver10/schema';WSA='http://schemas.xmlsoap.org/ws/2004/08/addressing'
WSD='http://schemas.xmlsoap.org/ws/2005/04/discovery'

def nals(data):
    return [part for part in re.split(b'\x00\x00(?:\x00)?\x01',data) if part]

def h264_rtp(data,sequence,timestamp,ssrc,mtu=1200):
    """RFC6184 single NAL/FU-A, one source access unit and one RTP timestamp."""
    if not 64<=mtu<=1400:raise ValueError('Invalid RTP payload bound')
    parts=nals(data)
    if not parts or any(not p or len(p)>4*1024*1024 for p in parts):raise ValueError('Invalid H264 access unit')
    for index,nal in enumerate(parts):
        fragments=[nal] if len(nal)<=mtu else [bytes([(nal[0]&0xe0)|28,(nal[0]&31)|(0x80 if i==0 else 0)|(0x40 if i+mtu-2>=len(nal)-1 else 0)])+nal[1+i:1+i+mtu-2] for i in range(0,len(nal)-1,mtu-2)]
        for fragment_index,fragment in enumerate(fragments):
            marker=index==len(parts)-1 and fragment_index==len(fragments)-1
            yield struct.pack('!BBHII',0x80,96|(0x80 if marker else 0),sequence&65535,timestamp&0xffffffff,ssrc)+fragment
            sequence+=1

def parse_xml(data):
    if len(data)>65536 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('Unsafe XML')
    return ET.fromstring(data)

def envelope(body,header=''):
    return (f'<s:Envelope xmlns:s="{SOAP}" xmlns:tds="{TDS}" xmlns:trt="{TRT}" xmlns:tt="{TT}" xmlns:wsa="{WSA}" xmlns:d="{WSD}" xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><s:Header>{header}</s:Header><s:Body>{body}</s:Body></s:Envelope>').encode()

class NetworkCameraLab:
    def __init__(self,ip,units,jpeg,width=1280,height=720,fps=30,identity=None,http_port=0,rtsp_port=0):
        address=ipaddress.ip_address(ip)
        if address.version!=4 or not address.is_private:raise ValueError('Private local interface required')
        if not units or width<2 or height<2 or not 1<=fps<=60:raise ValueError('Invalid generated fixture')
        self.ip=ip;self.units=tuple(bytes(x[0]) for x in units);self.jpeg=bytes(jpeg);self.width=width;self.height=height;self.fps=fps
        self.id=str(uuid.UUID(identity)) if identity else str(uuid.uuid4());self.path='/generated/'+self.id.replace('-','');self.stop=threading.Event();self.lock=threading.Lock();self.operations=[];self.sent=0
        if any(type(p) is not int or (p!=0 and not 1024<=p<=65535) for p in (http_port,rtsp_port)):raise ValueError('Invalid owned listener ports')
        self.http_port=http_port;self.rtsp_port=rtsp_port
        self.http=self.rtsp=self.discovery=None;self.threads=[];self.clients=0
        all_nals=[p for au in self.units for p in nals(au)]
        self.sps=next(p for p in all_nals if p[0]&31==7);self.pps=next(p for p in all_nals if p[0]&31==8)
    def local(self,peer):return peer in ('127.0.0.1',self.ip)
    def log(self,name):
        with self.lock:
            self.operations.append(name)
            if len(self.operations)>200:self.operations.pop(0)
    @property
    def device_url(self):return f'http://{self.ip}:{self.http.server_port}/onvif/device_service'
    @property
    def media_url(self):return f'http://{self.ip}:{self.http.server_port}/onvif/media_service'
    @property
    def rtsp_url(self):return f'rtsp://{self.ip}:{self.rtsp.server_address[1]}{self.path}'
    def encoder(self):
        return f'<tt:VideoEncoderConfiguration token="example-encoder"><tt:Name>Generated H264</tt:Name><tt:UseCount>1</tt:UseCount><tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>{self.width}</tt:Width><tt:Height>{self.height}</tt:Height></tt:Resolution><tt:Quality>5</tt:Quality><tt:RateControl><tt:FrameRateLimit>{self.fps}</tt:FrameRateLimit><tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>12000</tt:BitrateLimit></tt:RateControl><tt:H264><tt:GovLength>{self.fps}</tt:GovLength><tt:H264Profile>Baseline</tt:H264Profile></tt:H264><tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address><tt:Port>0</tt:Port><tt:TTL>1</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast><tt:SessionTimeout>PT60S</tt:SessionTimeout></tt:VideoEncoderConfiguration>'
    def source(self):
        return f'<tt:VideoSourceConfiguration token="example-source"><tt:Name>Generated source</tt:Name><tt:UseCount>1</tt:UseCount><tt:SourceToken>example-source1</tt:SourceToken><tt:Bounds x="0" y="0" width="{self.width}" height="{self.height}"/></tt:VideoSourceConfiguration>'
    def service_capabilities(self,namespace):
        if namespace==TRT:
            return '<trt:Capabilities SnapshotUri="true" Rotation="false"><trt:ProfileCapabilities MaximumNumberOfProfiles="1"/><trt:StreamingCapabilities RTPMulticast="false" RTP_TCP="false" RTP_RTSP_TCP="false"/></trt:Capabilities>'
        return '<tds:Capabilities><tds:Network IPFilter="false" ZeroConfiguration="false" IPVersion6="false" DynDNS="false"/><tds:System DiscoveryResolve="false" DiscoveryBye="true" RemoteDiscovery="false"/><tds:Security TLS1.0="false" TLS1.1="false" TLS1.2="false"/></tds:Capabilities>'
    def soap(self,data):
        root=parse_xml(data);body=root.find('{'+SOAP+'}Body')
        if body is None or len(body)!=1:raise ValueError('Invalid SOAP body')
        operation=body[0].tag.rsplit('}',1)[-1]
        if len(operation)>128:raise ValueError('Operation bound')
        self.log(operation)
        if operation=='GetSystemDateAndTime':
            now=datetime.datetime.now(datetime.timezone.utc)
            result=f'<tds:SystemDateAndTime><tt:DateTimeType>NTP</tt:DateTimeType><tt:DaylightSavings>false</tt:DaylightSavings><tt:TimeZone><tt:TZ>UTC0</tt:TZ></tt:TimeZone><tt:UTCDateTime><tt:Time><tt:Hour>{now.hour}</tt:Hour><tt:Minute>{now.minute}</tt:Minute><tt:Second>{now.second}</tt:Second></tt:Time><tt:Date><tt:Year>{now.year}</tt:Year><tt:Month>{now.month}</tt:Month><tt:Day>{now.day}</tt:Day></tt:Date></tt:UTCDateTime></tds:SystemDateAndTime>'
        elif operation=='GetDeviceInformation':result='<tds:Manufacturer>SMB</tds:Manufacturer><tds:Model>Generated network camera lab</tds:Model><tds:FirmwareVersion>0.1</tds:FirmwareVersion><tds:SerialNumber>generated-only</tds:SerialNumber><tds:HardwareId>SMB-LAB</tds:HardwareId>'
        elif operation=='GetServices':
            include=body[0].find('{'+TDS+'}IncludeCapability')
            include=include is not None and (include.text or '').strip() in ('true','1')
            self.log('GetServices capabilities '+str(include))
            result=''.join(f'<tds:Service><tds:Namespace>{ns}</tds:Namespace><tds:XAddr>{url}</tds:XAddr>'+(f'<tds:Capabilities>{self.service_capabilities(ns)}</tds:Capabilities>' if include else '')+'<tds:Version><tt:Major>2</tt:Major><tt:Minor>0</tt:Minor></tds:Version></tds:Service>' for ns,url in ((TDS,self.device_url),(TRT,self.media_url)))
        elif operation=='GetCapabilities':result=f'<tds:Capabilities><tt:Device><tt:XAddr>{self.device_url}</tt:XAddr><tt:Network><tt:IPFilter>false</tt:IPFilter><tt:ZeroConfiguration>false</tt:ZeroConfiguration><tt:IPVersion6>false</tt:IPVersion6><tt:DynDNS>false</tt:DynDNS></tt:Network><tt:System><tt:DiscoveryResolve>false</tt:DiscoveryResolve><tt:DiscoveryBye>true</tt:DiscoveryBye><tt:RemoteDiscovery>false</tt:RemoteDiscovery><tt:SystemBackup>false</tt:SystemBackup><tt:SystemLogging>false</tt:SystemLogging><tt:FirmwareUpgrade>false</tt:FirmwareUpgrade><tt:SupportedVersions><tt:Major>2</tt:Major><tt:Minor>0</tt:Minor></tt:SupportedVersions></tt:System><tt:Security><tt:TLS1.1>false</tt:TLS1.1><tt:TLS1.2>false</tt:TLS1.2></tt:Security></tt:Device><tt:Media><tt:XAddr>{self.media_url}</tt:XAddr><tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>false</tt:RTP_TCP><tt:RTP_RTSP_TCP>false</tt:RTP_RTSP_TCP></tt:StreamingCapabilities></tt:Media></tds:Capabilities>'
        elif operation=='GetScopes':result='<tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/name/SMB_Camera_generated_lab</tt:ScopeItem></tds:Scopes><tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/type/video_encoder</tt:ScopeItem></tds:Scopes>'
        elif operation=='GetHostname':result='<tds:HostnameInformation><tt:FromDHCP>false</tt:FromDHCP><tt:Name>smb-camera-lab</tt:Name></tds:HostnameInformation>'
        elif operation=='GetNetworkProtocols':result=f'<tds:NetworkProtocols><tt:Name>HTTP</tt:Name><tt:Enabled>true</tt:Enabled><tt:Port>{self.http.server_port}</tt:Port></tds:NetworkProtocols><tds:NetworkProtocols><tt:Name>RTSP</tt:Name><tt:Enabled>true</tt:Enabled><tt:Port>{self.rtsp.server_address[1]}</tt:Port></tds:NetworkProtocols>'
        elif operation=='GetNetworkInterfaces':result=f'<tds:NetworkInterfaces token="example-generated"><tt:Enabled>true</tt:Enabled><tt:Info><tt:Name>generated-local</tt:Name><tt:HwAddress>02:00:00:00:00:01</tt:HwAddress><tt:MTU>1500</tt:MTU></tt:Info><tt:IPv4><tt:Enabled>true</tt:Enabled><tt:Config><tt:Manual><tt:Address>{self.ip}</tt:Address><tt:PrefixLength>24</tt:PrefixLength></tt:Manual><tt:DHCP>false</tt:DHCP></tt:Config></tt:IPv4></tds:NetworkInterfaces>'
        elif operation=='GetServiceCapabilities':result=self.service_capabilities(TRT if body[0].tag.startswith('{'+TRT+'}') else TDS)
        elif operation in ('GetProfiles','GetProfile'):result=f'<trt:{"Profiles" if operation=="GetProfiles" else "Profile"} token="example-main" fixed="true"><tt:Name>Generated main</tt:Name>{self.source()}{self.encoder()}</trt:{"Profiles" if operation=="GetProfiles" else "Profile"}>'
        elif operation=='GetVideoSources':result=f'<trt:VideoSources token="example-source1"><tt:Framerate>{self.fps}</tt:Framerate><tt:Resolution><tt:Width>{self.width}</tt:Width><tt:Height>{self.height}</tt:Height></tt:Resolution></trt:VideoSources>'
        elif operation in ('GetVideoEncoderConfigurations','GetVideoEncoderConfiguration'):result=self.encoder().replace('tt:VideoEncoderConfiguration','trt:Configurations' if operation.endswith('Configurations') else 'trt:Configuration')
        elif operation in ('GetVideoSourceConfigurations','GetVideoSourceConfiguration'):result=self.source().replace('tt:VideoSourceConfiguration','trt:Configurations' if operation.endswith('Configurations') else 'trt:Configuration')
        elif operation=='GetVideoEncoderConfigurationOptions':result=f'<trt:Options><tt:QualityRange><tt:Min>1</tt:Min><tt:Max>10</tt:Max></tt:QualityRange><tt:H264><tt:ResolutionsAvailable><tt:Width>{self.width}</tt:Width><tt:Height>{self.height}</tt:Height></tt:ResolutionsAvailable><tt:GovLengthRange><tt:Min>1</tt:Min><tt:Max>120</tt:Max></tt:GovLengthRange><tt:FrameRateRange><tt:Min>{self.fps}</tt:Min><tt:Max>{self.fps}</tt:Max></tt:FrameRateRange><tt:EncodingIntervalRange><tt:Min>1</tt:Min><tt:Max>1</tt:Max></tt:EncodingIntervalRange><tt:H264ProfilesSupported>Baseline</tt:H264ProfilesSupported></tt:H264></trt:Options>'
        elif operation=='GetStreamUri':result=f'<trt:MediaUri><tt:Uri>{escape(self.rtsp_url)}</tt:Uri><tt:InvalidAfterConnect>false</tt:InvalidAfterConnect><tt:InvalidAfterReboot>true</tt:InvalidAfterReboot><tt:Timeout>PT60S</tt:Timeout></trt:MediaUri>'
        elif operation=='GetSnapshotUri':result=f'<trt:MediaUri><tt:Uri>http://{self.ip}:{self.http.server_port}/generated.jpg</tt:Uri><tt:InvalidAfterConnect>false</tt:InvalidAfterConnect><tt:InvalidAfterReboot>true</tt:InvalidAfterReboot><tt:Timeout>PT60S</tt:Timeout></trt:MediaUri>'
        elif operation.startswith('SetVideo'):
            for node in body[0].iter():
                name=node.tag.rsplit('}',1)[-1]
                if name in ('Width','Height','FrameRateLimit') and int(node.text or '0')!={'Width':self.width,'Height':self.height,'FrameRateLimit':self.fps}[name]:raise ValueError('Unsupported fixture mode')
            result=''
        elif operation=='Get':return self.metadata()
        else:raise ValueError('Unsupported operation')
        prefix='trt' if body[0].tag.startswith('{'+TRT+'}') else 'tds'
        message=next((n for n in root.iter() if n.tag.rsplit('}',1)[-1]=='MessageID'),None)
        namespace=body[0].tag[1:].split('}',1)[0] if body[0].tag.startswith('{') else TDS
        address=message.tag[1:].split('}',1)[0] if message is not None else WSA
        headers=f'<a:Action xmlns:a="{address}">{namespace}/{operation}Response</a:Action><a:MessageID xmlns:a="{address}">urn:uuid:{uuid.uuid4()}</a:MessageID>'
        if message is not None:headers+=f'<a:RelatesTo xmlns:a="{address}">{escape(message.text or "")}</a:RelatesTo>'
        return envelope(f'<{prefix}:{operation}Response>{result}</{prefix}:{operation}Response>',headers)
    def metadata(self):
        return envelope(f'<wsx:Metadata xmlns:wsx="http://schemas.xmlsoap.org/ws/2004/09/mex" xmlns:dp="http://schemas.xmlsoap.org/ws/2006/02/devprof"><wsx:MetadataSection Dialect="http://schemas.xmlsoap.org/ws/2006/02/devprof/ThisDevice"><dp:ThisDevice><dp:FriendlyName xml:lang="en-US">SMB Camera generated lab</dp:FriendlyName><dp:FirmwareVersion>0.1</dp:FirmwareVersion><dp:SerialNumber>generated-only</dp:SerialNumber></dp:ThisDevice></wsx:MetadataSection><wsx:MetadataSection Dialect="http://schemas.xmlsoap.org/ws/2006/02/devprof/ThisModel"><dp:ThisModel><dp:Manufacturer>SMB</dp:Manufacturer><dp:ModelName>Generated network camera lab</dp:ModelName></dp:ThisModel></wsx:MetadataSection><wsx:MetadataSection Dialect="http://schemas.xmlsoap.org/ws/2006/02/devprof/Relationship"><dp:Relationship Type="http://schemas.xmlsoap.org/ws/2006/02/devprof/host"><dp:Host><wsa:EndpointReference><wsa:Address>urn:uuid:{self.id}</wsa:Address></wsa:EndpointReference><dp:Types>dn:NetworkVideoTransmitter</dp:Types><dp:ServiceId>urn:uuid:{self.id}</dp:ServiceId></dp:Host></dp:Relationship></wsx:MetadataSection></wsx:Metadata>')
    def probe_reply(self,data):
        root=parse_xml(data);body=root.find('{'+SOAP+'}Body')
        if body is None or len(body)!=1:return None
        operation=body[0].tag.rsplit('}',1)[-1]
        if operation not in ('Probe','Resolve'):return None
        ident=root.find('.//{'+WSA+'}MessageID');relation=escape(ident.text or '') if ident is not None else ''
        if operation=='Resolve' and f'urn:uuid:{self.id}'.encode() not in data:return None
        item=f'<wsa:EndpointReference><wsa:Address>urn:uuid:{self.id}</wsa:Address></wsa:EndpointReference><d:Types>dn:NetworkVideoTransmitter</d:Types><d:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/name/SMB_Camera_generated_lab</d:Scopes><d:XAddrs>{self.device_url}</d:XAddrs><d:MetadataVersion>1</d:MetadataVersion>'
        self.log('WS'+operation)
        return envelope(f'<d:{operation}Matches><d:{operation}Match>{item}</d:{operation}Match></d:{operation}Matches>',f'<wsa:MessageID>urn:uuid:{uuid.uuid4()}</wsa:MessageID><wsa:RelatesTo>{relation}</wsa:RelatesTo><wsa:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To><wsa:Action>{WSD}/{operation}Matches</wsa:Action>')
    def start(self,discovery=True):
        lab=self
        class HTTP(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if not lab.local(self.client_address[0]):self.send_error(403);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=65536:raise ValueError('Body bound')
                    self.connection.settimeout(3);reply=lab.soap(self.rfile.read(size))
                except (ValueError,ET.ParseError,OSError) as error:lab.log('HTTP error '+type(error).__name__);self.send_error(400);return
                self.send_response(200);self.send_header('Content-Type','application/soap+xml; charset=utf-8');self.send_header('Content-Length',str(len(reply)));self.end_headers();self.wfile.write(reply)
            def do_GET(self):
                if not lab.local(self.client_address[0]):self.send_error(403);return
                data=lab.jpeg if self.path=='/generated.jpg' else lab.metadata()
                self.send_response(200);self.send_header('Content-Type','image/jpeg' if self.path=='/generated.jpg' else 'application/soap+xml');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        class RTSP(socketserver.StreamRequestHandler):
            def handle(self):
                if not lab.local(self.client_address[0]):return
                with lab.lock:
                    if lab.clients>=4:return
                    lab.clients+=1
                rtp=rtcp=None;sender=None;ended=threading.Event();session=secrets.token_hex(8)
                try:
                    self.connection.settimeout(15)
                    while not lab.stop.is_set():
                        line=self.rfile.readline(8193)
                        if not line:break
                        if len(line)>8192:break
                        parts=line.decode('ascii').strip().split(' ')
                        if len(parts)!=3:break
                        method,url,version=parts;headers={};size=0
                        while True:
                            line=self.rfile.readline(8193);size+=len(line)
                            if not line or len(line)>8192 or size>65536:raise ValueError('RTSP header bound')
                            if line in (b'\r\n',b'\n'):break
                            key,value=line.decode('ascii').split(':',1);headers[key.lower()]=value.strip()
                        cseq=headers.get('cseq','0')
                        if not cseq.isdigit() or not url.split('?',1)[0].endswith((lab.path,lab.path+'/',lab.path+'/trackID=0')):break
                        payload=b'';extra=[];code='200 OK';lab.log('RTSP '+method)
                        if method=='OPTIONS':extra=['Public: OPTIONS, DESCRIBE, SETUP, PLAY, GET_PARAMETER, TEARDOWN']
                        elif method=='DESCRIBE':
                            sps=base64.b64encode(lab.sps).decode();pps=base64.b64encode(lab.pps).decode()
                            payload=(f'v=0\r\no=- 1 1 IN IP4 {lab.ip}\r\ns=SMB generated camera\r\nc=IN IP4 {lab.ip}\r\nt=0 0\r\na=control:*\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\na=fmtp:96 packetization-mode=1;profile-level-id={lab.sps[1:4].hex()};sprop-parameter-sets={sps},{pps}\r\na=framerate:{lab.fps}\r\na=control:trackID=0\r\n').encode();extra=['Content-Type: application/sdp','Content-Base: '+lab.rtsp_url+'/']
                        elif method=='SETUP':
                            transport=headers.get('transport','');match=re.search(r'client_port=(\d+)-(\d+)',transport)
                            if not match or 'TCP' in transport.upper():code='461 Unsupported Transport'
                            else:
                                ports=tuple(map(int,match.groups()))
                                if not all(1024<=p<=65535 for p in ports) or ports[0]==ports[1]:raise ValueError('Invalid client ports')
                                for _ in range(32):
                                    rtp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);rtp.bind((lab.ip,0));port=rtp.getsockname()[1]
                                    if port%2:rtp.close();rtp=None;continue
                                    rtcp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                                    try:rtcp.bind((lab.ip,port+1));break
                                    except OSError:rtp.close();rtcp.close();rtp=rtcp=None
                                if rtp is None or rtcp is None:raise OSError('No local RTP/RTCP pair available')
                                ssrc=secrets.randbits(32);first_seq=secrets.randbits(16);first_stamp=secrets.randbits(32)
                                extra=[f'Transport: RTP/AVP;unicast;source={lab.ip};client_port={ports[0]}-{ports[1]};server_port={rtp.getsockname()[1]}-{rtcp.getsockname()[1]};ssrc={ssrc:08X}',f'Session: {session};timeout=60']
                        elif method=='PLAY' and rtp:
                            extra=['Session: '+session,'Range: npt=0.000-',f'RTP-Info: url={lab.rtsp_url}/trackID=0;seq={first_seq};rtptime={first_stamp}']
                        elif method in ('TEARDOWN','GET_PARAMETER'):extra=['Session: '+session]
                        else:code='405 Method Not Allowed'
                        response='RTSP/1.0 '+code+'\r\nCSeq: '+cseq+'\r\n'+''.join(h+'\r\n' for h in extra)+f'Content-Length: {len(payload)}\r\n\r\n'
                        self.wfile.write(response.encode()+payload);self.wfile.flush()
                        if method=='PLAY' and rtp and sender is None:
                            sender=threading.Thread(target=lab.send_rtp,args=(rtp,rtcp,self.client_address[0],ports,ssrc,ended,first_seq,first_stamp),daemon=True);sender.start()
                        if method=='TEARDOWN':break
                except (OSError,ValueError,UnicodeError):pass
                finally:
                    ended.set()
                    if sender:sender.join(timeout=2)
                    if rtp:rtp.close()
                    if rtcp:rtcp.close()
                    with lab.lock:lab.clients-=1
        class TCP(socketserver.ThreadingTCPServer):allow_reuse_address=False;daemon_threads=True
        self.http=ThreadingHTTPServer((self.ip,self.http_port),HTTP);self.http.daemon_threads=True
        self.rtsp=TCP((self.ip,self.rtsp_port),RTSP)
        for server in (self.http,self.rtsp):
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.threads.append(thread)
        if discovery:
            self.discovery=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
            self.discovery.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);self.discovery.bind(('',3702))
            self.discovery.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,socket.inet_aton('239.255.255.250')+socket.inet_aton(self.ip));self.discovery.settimeout(.3)
            thread=threading.Thread(target=self.discover,daemon=True);thread.start();self.threads.append(thread)
        return self
    def discover(self):
        while not self.stop.is_set():
            try:data,peer=self.discovery.recvfrom(65537)
            except socket.timeout:continue
            except OSError:break
            try:
                reply=self.probe_reply(data)
                if reply:self.discovery.sendto(reply,peer)
            except (ValueError,ET.ParseError,OSError):continue
    def send_rtp(self,rtp,rtcp,peer,ports,ssrc,ended,sequence,initial):
        index=0;start=time.monotonic();last_report=0;packets=octets=0
        while not self.stop.is_set() and not ended.is_set():
            if ended.wait(max(0,start+index/self.fps-time.monotonic())):break
            timestamp=(initial+round(index*90000/self.fps))&0xffffffff
            try:
                for packet in h264_rtp(self.units[index%len(self.units)],sequence,timestamp,ssrc):
                    rtp.sendto(packet,(peer,ports[0]));sequence+=1;packets+=1;octets+=len(packet)-12
                now=time.time()
                if now-last_report>=1:
                    seconds=int(now)+2208988800;fraction=int((now-int(now))*2**32)
                    report=struct.pack('!BBHIIIIII',0x80,200,6,ssrc,seconds,fraction,timestamp,packets&0xffffffff,octets&0xffffffff)
                    cname=b'smb-generated';chunk=struct.pack('!I',ssrc)+bytes([1,len(cname)])+cname+b'\x00';chunk+=b'\x00'*((-len(chunk))%4)
                    description=struct.pack('!BBH',0x81,202,len(chunk)//4)+chunk
                    rtcp.sendto(report+description,(peer,ports[1]));last_report=now
                index+=1
                with self.lock:self.sent+=1
            except OSError:break
    def close(self):
        self.stop.set()
        if self.discovery:self.discovery.close()
        for server in (self.http,self.rtsp):
            if server:server.shutdown();server.server_close()
        for thread in self.threads:thread.join(timeout=2)
