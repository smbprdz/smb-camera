"""Local QR enrollment. Private credentials never enter discovery announcements."""
from dataclasses import dataclass, field
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit, quote

SERVICE_TYPE = '_ucs-camera._tcp.local.'
PRIVATE = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))

@dataclass(frozen=True)
class Pairing:
    host: str
    name: str
    pin: str
    token: str = field(repr=False)

    def validate(self):
        address = ipaddress.IPv4Address(self.host)
        if not any(address in network for network in PRIVATE):
            raise ValueError('Pairing requires a private LAN IPv4 address')
        if not 1 <= len(self.name) <= 48 or self.name != self.name.strip():
            raise ValueError('Invalid PC name')
        if any(unicodedata.category(c).startswith('C') for c in self.name):
            raise ValueError('Invalid PC name')
        if not all(re.fullmatch('[0-9a-f]{64}', x) for x in (self.pin, self.token)):
            raise ValueError('Invalid pairing identity')
        return self

    @property
    def service_name(self):
        return 'UCS-'+self.pin[:16]

    def uri(self):
        self.validate()
        return urlunsplit(('universalcamera','pair','',urlencode(
            {'v':'1','host':self.host,'name':self.name,'pin':self.pin,'token':self.token},quote_via=quote),''))

def parse_pairing(value):
    if not isinstance(value,str) or len(value)>4096:
        raise ValueError('Invalid pairing QR')
    try:
        url=urlsplit(value)
        if url.scheme.lower()!='universalcamera' or url.netloc.lower()!='pair' or url.path or url.fragment:
            raise ValueError('Invalid pairing QR')
        values=parse_qs(url.query,keep_blank_values=True,strict_parsing=True)
        if set(values)!={'v','host','name','pin','token'} or any(len(x)!=1 for x in values.values()):
            raise ValueError('Invalid pairing QR')
        if values['v']!=['1']: raise ValueError('Unsupported pairing version')
        return Pairing(values['host'][0],values['name'][0],values['pin'][0].lower(),values['token'][0].lower()).validate()
    except (ValueError,UnicodeError) as exc:
        # Never echo the incoming URI or credentials in errors/logs.
        raise ValueError('Invalid or unsupported pairing QR') from exc

class Advertisement:
    def __init__(self, pairing, port):
        import socket
        from zeroconf import Zeroconf, ServiceInfo, IPVersion
        pairing.validate()
        self.zc=Zeroconf(interfaces=[pairing.host],ip_version=IPVersion.V4Only)
        self.info=ServiceInfo(SERVICE_TYPE,pairing.service_name+'.'+SERVICE_TYPE,
            addresses=[socket.inet_aton(pairing.host)],port=port,
            properties={'v':'1','name':pairing.name},server=pairing.service_name.lower()+'.local.')
        try: self.zc.register_service(self.info)
        except Exception:
            self.zc.close();raise

    def close(self):
        try: self.zc.unregister_service(self.info)
        finally: self.zc.close()
