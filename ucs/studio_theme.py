"""Native widgets using the owner's SMB Live Chat design tokens and dimensions.

Reference: own SMB_LIVE_CHAT/web/styles.css; no Electron/browser dependency.
"""
import tkinter as tk
from tkinter import ttk

TOKENS={'bg':'#101216','panel':'#181c23','panel2':'#1e232d','hover':'#252b36',
        'line':'#2c3340','text':'#edf0f6','muted':'#99a4b6','subtle':'#737e90',
        'accent':'#f09bc9','accent_bg':'#302131','action':'#b82f75','good':'#7ed4ad'}

def button_style(root,style):
    """Small original nine-slice textures give ttk the same corner radius as SMB."""
    from PIL import Image,ImageDraw,ImageTk
    root.smb_button_images=[]
    def tile(fill,border):
        image=Image.new('RGBA',(24,24));draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((0,0,23,23),radius=8,fill=fill,outline=border,width=1)
        photo=ImageTk.PhotoImage(image,master=root);root.smb_button_images.append(photo);return photo
    for prefix,fill,hover,border in [('SMB',TOKENS['panel2'],TOKENS['hover'],TOKENS['line']),
                                     ('SMBPrimary',TOKENS['action'],'#cf3d88',TOKENS['action']),
                                     ('SMBRecord','#aa2544','#bd3151','#db5872'),
                                     ('SMBLens',TOKENS['accent_bg'],TOKENS['hover'],TOKENS['accent'])]:
        normal=tile(fill,border);active=tile(hover,TOKENS['subtle']);disabled=tile(TOKENS['panel'],TOKENS['line'])
        name=prefix+'.Button.border'
        try:style.element_create(name,'image',normal,('disabled',disabled),('active',active),border=8,sticky='nsew')
        except tk.TclError:pass
        layout=[(name,{'sticky':'nsew','children':[('Button.padding',{'sticky':'nsew','children':[('Button.label',{'sticky':'nsew'})]})]})]
        target={'SMB':'TButton','SMBPrimary':'Accent.TButton','SMBLens':'LensActive.TButton','SMBRecord':'Recording.TButton'}[prefix];style.layout(target,layout)
        style.configure(target,padding=(13,8),font=('Segoe UI',9),foreground=TOKENS['text'])
        style.map(target,foreground=[('disabled',TOKENS['subtle'])])
    style.configure('Lens.TButton',padding=(4,8),font=('Segoe UI',8))
    style.configure('LensActive.TButton',padding=(4,8),font=('Segoe UI',8),foreground=TOKENS['accent'])

class LensButtons(ttk.Frame):
    def __init__(self,parent,on_select):
        super().__init__(parent,style='Panel.TFrame');self.on_select=on_select;self.buttons={};self.last_key=None
        self.row=ttk.Frame(self,style='Panel.TFrame');self.row.pack(fill='x')
        self.caption=ttk.Label(self,text='Aguardando câmeras...',style='Muted.TLabel',font=('Segoe UI',8),wraplength=280)
        self.caption.pack(anchor='w',pady=(7,0));self.selected_id=None
    @staticmethod
    def short_label(label):
        lower=label.lower()
        if 'frontal' in lower or 'front' in lower:return 'Frontal'
        if 'ultra' in lower:return 'Ultra'
        if 'tele' in lower:return 'Tele'
        if 'principal' in lower or 'wide' in lower:return 'Principal'
        return label.rsplit(':',1)[-1].strip()[:12]
    def set_capabilities(self,caps):
        cameras=caps['cameras'] if caps else []
        active=caps['active'] if caps else None
        key=(tuple((c['id'],c['label'],c['available']) for c in cameras),active)
        if key==self.last_key:return
        if caps is None:
            for button in self.buttons.values():button.configure(state='disabled')
            self.caption.configure(text='Aguardando câmeras...');self.selected_id=None;self.last_key=key;return
        if tuple(self.buttons)!=tuple(c['id'] for c in cameras):
            for i,button in enumerate(self.buttons.values()):button.destroy();self.row.columnconfigure(i,weight=0)
            self.buttons={}
            for index,camera in enumerate(cameras):
                id=camera['id'];button=ttk.Button(self.row,command=lambda id=id:self.on_select(id),style='Lens.TButton')
                button.grid(row=0,column=index,sticky='ew',padx=(0,4 if index<len(cameras)-1 else 0));self.row.columnconfigure(index,weight=1,uniform='camera')
                self.buttons[id]=button
        for camera in cameras:
            self.buttons[camera['id']].configure(text=self.short_label(camera['label']),state='normal' if camera['available'] else 'disabled',
                style='LensActive.TButton' if camera['id']==active else 'Lens.TButton')
        self.selected_id=active;self.caption.configure(text=next((c['label'] for c in cameras if c['id']==active),'Câmera conectada'))
        self.last_key=key

class Slider(tk.Canvas):
    """Small native rounded slider, keyboard usable; no polling/animation timer."""
    def __init__(self,parent,from_=0,to=1,command=None,state='normal',value=None,default=None,**kwargs):
        super().__init__(parent,height=23,bg=TOKENS['panel'],bd=0,highlightthickness=0,takefocus=1,**kwargs)
        self.minimum=float(from_);self.maximum=float(to);self.command=command;self.state=state
        self.value=self.minimum if value is None else float(value);self.focused=False;self.last_paint=None
        self.default=default
        self.bind('<Configure>',lambda _:self.redraw());self.bind('<Button-1>',self.pointer);self.bind('<B1-Motion>',self.pointer)
        self.bind('<Double-Button-1>',self.reset)
        self.bind('<FocusIn>',lambda _:self.focus(True));self.bind('<FocusOut>',lambda _:self.focus(False))
        for key,amount in [('Left',-1),('Down',-1),('Right',1),('Up',1)]:
            self.bind('<'+key+'>',lambda _,amount=amount:self.keyboard(amount))
        self.bind('<Home>',lambda _:self.set(self.minimum) if self.state!='disabled' else None)
        self.bind('<End>',lambda _:self.set(self.maximum) if self.state!='disabled' else None)
    def focus(self,value):self.focused=value;self.redraw()
    def keyboard(self,amount):
        if self.state!='disabled':self.set(self.value+amount*(self.maximum-self.minimum)/100)
    def pointer(self,event):
        if self.state=='disabled':return
        self.focus_set();self.set(self.minimum+max(0,min(1,(event.x-8)/max(1,self.winfo_width()-16)))*(self.maximum-self.minimum))
    def set(self,value):
        self.value=max(self.minimum,min(self.maximum,float(value)));self.redraw()
        if self.command and self.state!='disabled':self.command(str(self.value))
    def get(self):return self.value
    def reset(self,event=None):
        if self.state!='disabled':
            self.focus_set();self.set(self.minimum if self.default is None else self.default)
        return 'break'
    def configure(self,cnf=None,**kwargs):
        if not hasattr(self,'minimum'):return super().configure(cnf,**kwargs)
        for key,target in [('from_','minimum'),('from','minimum'),('to','maximum'),('state','state'),('command','command')]:
            if key in kwargs:setattr(self,target,kwargs.pop(key))
        result=super().configure(cnf,**kwargs) if cnf is not None or kwargs else None
        self.value=max(self.minimum,min(self.maximum,self.value));self.redraw();return result
    config=configure
    def redraw(self):
        if not self.winfo_exists():return
        w=max(16,self.winfo_width());key=(w,self.value,self.minimum,self.maximum,self.state,self.focused)
        if key==self.last_paint:return
        self.last_paint=key;self.delete('all');fraction=(self.value-self.minimum)/max(1e-9,self.maximum-self.minimum)
        x=8+fraction*(w-16);color=TOKENS['action'] if self.state!='disabled' else TOKENS['subtle']
        self.create_line(8,12,w-8,12,fill=TOKENS['line'],width=5,capstyle='round')
        if x>8:self.create_line(8,12,x,12,fill=color,width=5,capstyle='round')
        self.create_oval(x-6,6,x+6,18,fill=color,outline=TOKENS['accent'] if self.focused else color)

class NavButton(tk.Canvas):
    def __init__(self,parent,text,symbol,command):
        super().__init__(parent,height=42,bg=TOKENS['panel'],highlightthickness=0,bd=0,cursor='hand2',takefocus=1)
        self.text=text;self.symbol=symbol;self.command=command;self.active=False;self.hover=False;self.last_paint=None
        self.bind('<Configure>',lambda _:self.draw());self.bind('<Button-1>',lambda _:self.command())
        self.bind('<Return>',lambda _:self.command());self.bind('<space>',lambda _:self.command())
        self.bind('<Enter>',lambda _:self.highlight(True));self.bind('<Leave>',lambda _:self.highlight(False))
    def highlight(self,value):self.hover=value;self.draw()
    def draw(self):
        width=max(40,self.winfo_width());key=(width,self.text,self.symbol,self.active,self.hover)
        if key==self.last_paint:return
        self.last_paint=key;self.delete('all');fill=TOKENS['accent_bg'] if self.active else TOKENS['hover'] if self.hover else TOKENS['panel']
        # Smooth polygon yields rounded9px corners using native Tk primitives.
        r=9;self.create_polygon(1+r,1,width-1-r,1,width-1,1,width-1,1+r,width-1,41-r,width-1,41,width-1-r,41,1+r,41,1,41,1,41-r,1,1+r,1,1,smooth=True,fill=fill,outline='')
        fg=TOKENS['accent'] if self.active else TOKENS['text'] if self.hover else TOKENS['muted']
        self.create_text(23,21,text=self.symbol,font=('Segoe UI Symbol',14),fill=fg)
        if width>100:self.create_text(46,21,text=self.text,font=('Segoe UI',9),fill=fg,anchor='w')
        if self.active:self.create_line(1,11,1,31,fill=TOKENS['accent'],width=3)
