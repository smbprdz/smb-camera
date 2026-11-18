"""Negotiated controls-v1, bounded queue and applied-value confirmation."""
from collections import OrderedDict
import copy,math,threading,time,uuid
from .protocol import ProtocolError,CONTROL,json_message

def number(value,minimum,maximum):
    if type(value) not in (int,float) or not math.isfinite(value) or not minimum<=value<=maximum:
        raise ProtocolError('invalid control value')
    return value

def short(value,maximum=256):
    if not isinstance(value,str) or not 1<=len(value)<=maximum or any(ord(c)<32 for c in value):
        raise ProtocolError('invalid control identifier')
    return value

def capabilities(obj,session):
    if not isinstance(obj,dict):raise ProtocolError('invalid capabilities')
    if obj.get('session')!=session:raise ProtocolError('stale control session')
    revision=obj.get('revision');number(revision,1,2**53)
    if type(revision) is not int:raise ProtocolError('invalid capability revision')
    cameras=obj.get('cameras')
    if not isinstance(cameras,list) or not 1<=len(cameras)<=16:raise ProtocolError('invalid camera list')
    clean=[];ids=set()
    for cam in cameras:
        if not isinstance(cam,dict):raise ProtocolError('invalid camera capability')
        ident=short(cam.get('id'));label=short(cam.get('label'),120)
        if ident in ids or type(cam.get('available')) is not bool:raise ProtocolError('invalid camera capability')
        ids.add(ident);clean.append({'id':ident,'label':label,'available':cam['available']})
    active=short(obj.get('active'))
    if active not in ids:raise ProtocolError('active camera missing')
    state=obj.get('state')
    if not isinstance(state,dict):raise ProtocolError('invalid camera state')
    low=number(obj.get('zoom_min'),1,1024);high=number(obj.get('zoom_max'),low,1024)
    for key in ('focus_auto_supported','focus_manual_supported'):
        if type(obj.get(key)) is not bool:raise ProtocolError('invalid focus capability')
    checked_state={'zoom':number(state.get('zoom'),low,high),'focus':number(state.get('focus'),0,1)}
    if state.get('focus_mode') not in ('auto','manual','fixed'):raise ProtocolError('invalid focus mode')
    checked_state['focus_mode']=state['focus_mode']
    exposure=None
    if obj.get('exposure_bias') is not None:
        raw=obj['exposure_bias']
        if not isinstance(raw,dict) or set(raw)!= {'min','max'}:raise ProtocolError('invalid exposure capability')
        minimum=number(raw['min'],-128,128);maximum=number(raw['max'],minimum,128)
        exposure={'min':minimum,'max':maximum}
        checked_state['exposure_bias']=number(state.get('exposure_bias'),minimum,maximum)
        for key,maximum in (('sensor_iso',1_000_000),('sensor_exposure_us',1_000_000_000)):
            if key in state:checked_state[key]=number(state[key],.000001,maximum)
    return {'session':session,'revision':revision,'cameras':clean,'active':active,
            'zoom_min':low,'zoom_max':high,'focus_auto_supported':obj['focus_auto_supported'],
            'focus_manual_supported':obj['focus_manual_supported'],'state':checked_state,'exposure_bias':exposure}

class ControlBus:
    def __init__(self):
        self.lock=threading.Lock();self.session=None;self.caps=None
        self.pending=OrderedDict();self.in_flight=None;self.status='Aguardando controles do iPhone.'
    def begin(self,session):
        with self.lock:
            self.session=short(session,64);self.caps=None;self.pending.clear();self.in_flight=None
            self.status='Consultando cameras e controles...'
    def close(self):
        with self.lock:
            self.session=None;self.caps=None;self.pending.clear();self.in_flight=None
            self.status='Camera desconectada.'
    def update(self,obj):
        with self.lock:
            checked=capabilities(obj,self.session)
            if self.caps and checked['revision']<self.caps['revision']:raise ProtocolError('capability revision went backwards')
            if self.caps and checked['revision']!=self.caps['revision']:self.pending.clear()
            self.caps=checked
            if self.in_flight is None:self.status='Controles disponiveis.'
    def enqueue(self,control,value):
        with self.lock:
            if not self.session or not self.caps:return False
            caps=self.caps
            if control=='zoom':number(value,caps['zoom_min'],caps['zoom_max'])
            elif control=='exposure_bias':
                if caps['exposure_bias'] is None:return False
                number(value,caps['exposure_bias']['min'],caps['exposure_bias']['max'])
            elif control=='focus':
                if value=='auto':
                    if not caps['focus_auto_supported']:return False
                else:
                    if not caps['focus_manual_supported']:return False
                    number(value,0,1)
            elif control=='lens':
                short(value)
                if value not in [cam['id'] for cam in caps['cameras'] if cam['available']]:return False
            else:raise ProtocolError('unsupported control')
            # At most four pending actions; a slider replaces its older pending value.
            self.pending[control]=(value,caps['revision'])
            self.status='Aplicando ajuste...'
            return True
    def next_message(self,now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            if self.in_flight:
                if now-self.in_flight['sent_at']<=5:return None
                self.in_flight=None;self.pending.clear();self.status='O iPhone nao confirmou o ajuste. Tente novamente.'
                return None
            if not self.caps or not self.pending:return None
            control,(value,revision)=self.pending.popitem(last=False)
            if revision!=self.caps['revision']:return None
            command={'session':self.session,'revision':revision,'request':uuid.uuid4().hex,'control':control,'value':value}
            self.in_flight=dict(command,sent_at=now)
            return json_message(CONTROL,command)
    def result(self,obj):
        with self.lock:
            sent=self.in_flight
            if obj.get('session')!=self.session:return False
            if not sent or obj.get('request')!=sent['request']:return False
            if obj.get('status') not in ('applied','rejected'):raise ProtocolError('invalid control result')
            if obj.get('status')=='applied':
                if not self.caps:raise ProtocolError('control result without capabilities')
                revision=number(obj.get('revision'),1,2**53)
                if type(revision) is not int or revision!=self.caps['revision']:raise ProtocolError('control result revision mismatch')
                state=obj.get('state')
                checked=capabilities(dict(self.caps,state=state,active=obj.get('active',self.caps['active'])),self.session)
                self.caps=checked;self.status='Ajuste confirmado pelo iPhone.'
            else:
                reasons={'unsupported':'Controle indisponivel nesta lente.','range':'Valor fora do limite da camera.',
                         'stale_revision':'A camera mudou. Tente o ajuste novamente.',
                         'busy':'Camera ocupada. Tente novamente.','format':'Esta lente nao oferece o formato ativo.',
                         'failed':'O iPhone nao conseguiu aplicar o ajuste.'}
                self.status=reasons.get(obj.get('reason'),'Ajuste recusado pelo iPhone.')
            self.in_flight=None
            return True
    def snapshot(self):
        with self.lock:return {'caps':copy.deepcopy(self.caps),'status':self.status,'busy':self.in_flight is not None or bool(self.pending)}
