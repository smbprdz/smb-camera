"""One small shared orientation state. Current consumer is preview; OBS is future."""
import threading

class ViewTransform:
    def __init__(self):
        self.lock=threading.Lock();self.angle=0;self.mirror=False;self.output_format='landscape';self.pan_x=0.;self.pan_y=0.
    def set(self,angle=None,mirror=None,output_format=None,pan_x=None,pan_y=None):
        import math
        with self.lock:
            if angle is not None:
                if type(angle) is not int or angle not in (0,90,180,270):raise ValueError('Invalid quarter-turn rotation')
                self.angle=angle
            if mirror is not None:
                if type(mirror) is not bool:raise ValueError('Invalid mirror state')
                self.mirror=mirror
            if output_format is not None:
                if output_format not in ('landscape','portrait'):raise ValueError('Invalid output format')
                self.output_format=output_format
            for key,value in [('pan_x',pan_x),('pan_y',pan_y)]:
                if value is not None:
                    if type(value) not in (int,float) or not math.isfinite(value) or not -1<=value<=1:raise ValueError('Invalid crop centre')
                    setattr(self,key,float(value))
    def get(self):
        with self.lock:return {'angle':self.angle,'mirror':self.mirror,'output_format':self.output_format,'pan_x':self.pan_x,'pan_y':self.pan_y}

def crop_geometry(width,height,angle,output_format,pan_x=0,pan_y=0):
    """Fill a 16:9 / 9:16 canvas by cropping source pixels before GPU rotation."""
    if width<=0 or height<=0 or angle not in (0,90,180,270) or output_format not in ('landscape','portrait'):
        raise ValueError('Invalid crop geometry')
    long=max(width,height);short=round(long*9/16)
    out_w,out_h=(long,short) if output_format=='landscape' else (short,long)
    target_aspect=out_h/out_w if angle in (90,270) else out_w/out_h
    if width/height>target_aspect:crop_w,crop_h=round(height*target_aspect),height
    else:crop_w,crop_h=width,round(width/target_aspect)
    crop_w=max(1,min(width,crop_w));crop_h=max(1,min(height,crop_h))
    x=round((width-crop_w)*(max(-1,min(1,pan_x))+1)/2)
    y=round((height-crop_h)*(max(-1,min(1,pan_y))+1)/2)
    pre_w,pre_h=(out_h,out_w) if angle in (90,270) else (out_w,out_h)
    return {'canvas':(out_w,out_h),'source':(x,y,crop_w,crop_h),
            'destination':((out_w-pre_w)//2,(out_h-pre_h)//2,pre_w,pre_h)}
