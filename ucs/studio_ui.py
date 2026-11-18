"""Own desktop workspace: embedded GPU preview and compact native controls."""
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from .color import PARAMETERS,MAX_PRESET_BYTES
from . import studio_state
from .studio_theme import TOKENS,Slider,NavButton,LensButtons,button_style

BG=TOKENS['bg'];PANEL=TOKENS['panel'];CARD=TOKENS['panel2'];TEXT=TOKENS['text'];MUTED=TOKENS['muted'];ACCENT=TOKENS['action']

class PreviewSurface(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent);self.aspect=16/9;self.connected=None;self.last_geometry=None
        self.frame=tk.Frame(self,bg='#080a0f',highlightthickness=1,highlightbackground='#333b50')
        self.waiting=tk.Label(self.frame,text='Conecte seu iPhone\n\nUSB ou rede local',bg='#080a0f',fg=MUTED,font=('Segoe UI',16),justify='center')
        self.waiting.place(relx=.5,rely=.5,anchor='center')
        self.bind('<Configure>',lambda _:self.layout())
    def layout(self):
        w=max(16,self.winfo_width()-32);h=max(16,self.winfo_height()-32)
        if w/h>self.aspect:w=round(h*self.aspect)
        else:h=round(w/self.aspect)
        if (w,h)!=self.last_geometry:
            self.last_geometry=(w,h);self.frame.place(relx=.5,rely=.5,anchor='center',width=w,height=h)
    def set_format(self,format):self.aspect=9/16 if format=='portrait' else 16/9;self.layout()
    def status(self,connected):
        if self.connected==connected:return
        self.connected=connected
        if connected:self.waiting.place_forget()
        else:self.waiting.place(relx=.5,rely=.5,anchor='center')

class ScrollPanel(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,bg=PANEL,highlightthickness=0,bd=0)
        scroll=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body=ttk.Frame(self.canvas,style='Panel.TFrame',padding=(14,12))
        window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(window,width=event.width))


def section(parent,title):
    frame=ttk.LabelFrame(parent,text=title,padding=12);frame.pack(fill='x',pady=(0,12));return frame

def build_ui(c):
    root=c.root;root.title('Universal Camera Studio');root.geometry(f'{min(1280,root.winfo_screenwidth()-60)}x{min(820,root.winfo_screenheight()-100)}');root.minsize(980,640);root.configure(bg=BG)
    s=ttk.Style(root);s.theme_use('clam')
    s.configure('.',background=BG,foreground=TEXT,font=('Segoe UI',10),borderwidth=0)
    s.configure('TFrame',background=BG);s.configure('Panel.TFrame',background=PANEL)
    s.configure('TLabel',background=PANEL,foreground=TEXT);s.configure('Muted.TLabel',foreground=MUTED)
    s.configure('Header.TLabel',background=BG,foreground=TEXT);s.configure('Title.TLabel',background=BG,font=('Segoe UI',20,'bold'))
    s.configure('TButton',background=CARD,foreground=TEXT,padding=(12,7),borderwidth=1,relief='flat')
    s.map('TButton',background=[('active','#353e53'),('disabled','#202430')],foreground=[('disabled','#657087')])
    s.configure('Accent.TButton',background=ACCENT,foreground='white');s.map('Accent.TButton',background=[('active','#ff429f')])
    s.configure('TNotebook',background=PANEL);s.configure('TNotebook.Tab',background=CARD,padding=(17,10),foreground=MUTED)
    s.map('TNotebook.Tab',background=[('selected',PANEL)],foreground=[('selected',TEXT)])
    s.configure('TLabelframe',background=PANEL,bordercolor=PANEL,lightcolor=PANEL,darkcolor=PANEL,relief='flat',borderwidth=0)
    s.configure('TLabelframe.Label',background=PANEL,foreground=MUTED,font=('Segoe UI',9,'bold'))
    s.configure('TCheckbutton',background=PANEL,foreground=TEXT);s.map('TCheckbutton',background=[('active',PANEL)])
    s.configure('TCombobox',fieldbackground=CARD,background=CARD,foreground=TEXT,arrowcolor=TEXT,padding=5)
    s.configure('TCombobox',bordercolor=TOKENS['line'],lightcolor=TOKENS['line'],darkcolor=TOKENS['line'],selectbackground=TOKENS['accent_bg'],selectforeground=TEXT)
    s.map('TCombobox',fieldbackground=[('readonly',CARD)],foreground=[('readonly',TEXT),('disabled','#657087')],
          bordercolor=[('focus',TOKENS['accent']),('!focus',TOKENS['line'])],lightcolor=[('!disabled',TOKENS['line'])],darkcolor=[('!disabled',TOKENS['line'])])
    s.configure('TSeparator',background=TOKENS['line'],bordercolor=TOKENS['line'],lightcolor=TOKENS['line'],darkcolor=TOKENS['line'])
    for name in ('Horizontal.TSeparator','Vertical.TSeparator'):
        s.configure(name,background=TOKENS['line'],bordercolor=TOKENS['line'],lightcolor=TOKENS['line'],darkcolor=TOKENS['line'])
    s.configure('TPanedwindow',background=BG,borderwidth=0,relief='flat')
    s.configure('Sash',background=BG,bordercolor=BG,lightcolor=BG,darkcolor=BG,gripcount=0,sashthickness=4)
    s.configure('TCheckbutton',indicatorbackground=BG,indicatorforeground=ACCENT,indicatormargin=4,upperbordercolor=TOKENS['line'],lowerbordercolor=TOKENS['line'],lightcolor=TOKENS['line'],darkcolor=TOKENS['line'],bordercolor=TOKENS['line'])
    s.configure('Horizontal.TScale',background=PANEL,troughcolor='#343d52',lightcolor=ACCENT,darkcolor=ACCENT,bordercolor=ACCENT)
    s.configure('Vertical.TScrollbar',background=CARD,troughcolor=PANEL,arrowcolor=MUTED)
    s.configure('Vertical.TScrollbar',bordercolor=PANEL,lightcolor=PANEL,darkcolor=PANEL,arrowsize=10,width=10,borderwidth=0)
    s.map('Vertical.TScrollbar',background=[('active',TOKENS['line'])],bordercolor=[('active',PANEL)],lightcolor=[('active',PANEL)],darkcolor=[('active',PANEL)])
    s.configure('Card.TFrame',background=PANEL,bordercolor=TOKENS['line'],lightcolor=TOKENS['line'],darkcolor=TOKENS['line'])
    root.option_add('*TCombobox*Listbox.background',CARD);root.option_add('*TCombobox*Listbox.foreground',TEXT)
    button_style(root,s)
    s.configure('Eyebrow.TLabel',background=BG,foreground=TOKENS['accent'],font=('Segoe UI',8,'bold'))
    for name, base in (('RecordReady.TButton','Accent.TButton'), ('RecordActive.TButton','Recording.TButton')):
        s.layout(name,s.layout(base))
        s.configure(name,padding=(4,13),font=('Segoe UI',10,'bold'))
        s.map(name,foreground=[('disabled',TOKENS['subtle'])])
    s.configure('RecordingState.TLabel',background=PANEL,foreground=TEXT,font=('Segoe UI',10,'bold'))
    s.configure('RecordingLive.TLabel',background=PANEL,foreground='#ff7996',font=('Segoe UI',10,'bold'))
    s.configure('Sidebar.TLabel',background=PANEL,foreground=MUTED,font=('Segoe UI',9))
    s.configure('Brand.TLabel',background=PANEL,foreground=TEXT,font=('Segoe UI',12,'bold'))
    s.configure('Small.TLabel',background=PANEL,foreground=TOKENS['subtle'],font=('Segoe UI',8))
    s.layout('Inspector.TNotebook.Tab',[]);s.configure('Inspector.TNotebook',background=PANEL,tabmargins=0,borderwidth=0,bordercolor=PANEL,lightcolor=PANEL,darkcolor=PANEL)
    app=ttk.Frame(root);app.pack(fill='both',expand=True)
    c.sidebar=ttk.Frame(app,style='Panel.TFrame',width=218);c.sidebar.pack(side='left',fill='y');c.sidebar.pack_propagate(False)
    c.main=ttk.Frame(app);c.main.pack(side='left',fill='both',expand=True)
    brand=ttk.Frame(c.sidebar,style='Panel.TFrame',padding=(18,17,10,19));brand.pack(fill='x')
    icon=Path(__file__).resolve().parent/'assets/live-icon.png'
    if icon.is_file():
        from PIL import Image,ImageTk
        with Image.open(icon) as image:c.brand_photo=ImageTk.PhotoImage(image.convert('RGBA').resize((38,38)),master=root)
        root.iconphoto(True,c.brand_photo);ttk.Label(brand,image=c.brand_photo).pack(side='left',padx=(0,11))
        ico=icon.with_suffix('.ico')
        if ico.is_file():root.iconbitmap(str(ico))
    c.brand_words=ttk.Frame(brand,style='Panel.TFrame');c.brand_words.pack(side='left')
    ttk.Label(c.brand_words,text='SMB',style='Brand.TLabel').pack(anchor='w')
    ttk.Label(c.brand_words,text='C A M E R A',style='Small.TLabel').pack(anchor='w',pady=(3,0))
    c.navigation_label=ttk.Label(c.sidebar,text='N A V E G A Ç Ã O',style='Small.TLabel',padding=(27,0,0,10));c.navigation_label.pack(fill='x')
    c.sidebar_bottom=ttk.Frame(c.sidebar,style='Panel.TFrame',padding=(14,7,14,10))
    c.sidebar_bottom.pack(side='bottom',fill='x')
    c.status=ttk.Label(c.sidebar_bottom,text='Preparando câmera…',style='Sidebar.TLabel',wraplength=190)
    c.status.pack(anchor='w')
    from . import __version__
    ttk.Label(c.sidebar_bottom,text=__version__+' · câmera local',style='Small.TLabel').pack(anchor='w',pady=(3,0))

    c.sidebar_collapsed=False
    c.record_panel=ttk.Frame(c.sidebar,style='Panel.TFrame',padding=(14,8))
    c.record_panel.pack(side='bottom',fill='x')
    c.record_button=ttk.Button(c.record_panel,text='●  Gravar original',command=c.toggle_recording,
                               state='disabled',style='RecordReady.TButton')
    c.record_button.pack(fill='x')
    c.record_state=ttk.Label(c.record_panel,text='Aguardando iPhone',style='RecordingState.TLabel',anchor='center')
    c.record_state.pack(fill='x',pady=(6,2))
    c.record_details=ttk.Frame(c.record_panel,style='Panel.TFrame')
    c.record_details.pack(fill='x')
    c.record_mic=tk.BooleanVar(value=False)
    c.mic_check=ttk.Checkbutton(c.record_details,text='Microfone do iPhone',variable=c.record_mic,state='disabled')
    c.mic_check.pack(anchor='w',pady=(0,4))
    c.record_format=ttk.Label(c.record_details,text='MOV · H.264 original',style='Sidebar.TLabel')
    c.record_format.pack(anchor='w')
    c.record_frames=ttk.Label(c.record_details,text='Quadros gravados  0',style='Sidebar.TLabel')
    c.record_frames.pack(anchor='w',pady=(4,0))
    c.record_gaps=ttk.Label(c.record_details,text='Saltos na origem  0',style='Sidebar.TLabel')
    c.record_gaps.pack(anchor='w')
    c.record_audio=ttk.Label(c.record_details,text='',style='Sidebar.TLabel')
    c.record_audio.pack(anchor='w',pady=(2,0))
    c.record_result=ttk.Label(c.record_details,text='',style='Sidebar.TLabel',wraplength=186,justify='left')
    c.record_folder=ttk.Button(c.record_details,text='Abrir pasta',command=c.open_recording_folder)

    nav_panel=ScrollPanel(c.sidebar)
    nav_panel.body.configure(padding=(10,0))
    nav_panel.pack(fill='both',expand=True)
    c.navigation=nav_panel.body
    c.nav_buttons=[]
    top=ttk.Frame(c.main,height=66,padding=(28,0));top.pack(fill='x');top.pack_propagate(False)
    topinner=ttk.Frame(top);topinner.pack(fill='both',expand=True)
    def toggle_sidebar():
        c.sidebar_collapsed=not c.sidebar_collapsed
        c.sidebar.configure(width=76 if c.sidebar_collapsed else 218)
        if c.sidebar_collapsed:
            c.brand_words.pack_forget()
            c.navigation_label.pack_forget()
            c.sidebar_bottom.pack_forget()
            c.record_details.pack_forget()
            c.record_panel.configure(padding=(8,8))
        else:
            c.brand_words.pack(side='left')
            c.navigation_label.pack(fill='x',before=nav_panel)
            c.sidebar_bottom.pack(side='bottom',fill='x',before=c.record_panel)
            c.record_details.pack(fill='x')
            c.record_panel.configure(padding=(14,8))
        c.refresh_recording()
    ttk.Button(topinner,text='☰',width=2,command=toggle_sidebar).pack(side='left',padx=(0,12))
    ttk.Label(topinner,text='Universal Camera   ›',style='Header.TLabel',font=('Segoe UI',9)).pack(side='left')
    c.breadcrumb=ttk.Label(topinner,text='Câmera',style='Header.TLabel',font=('Segoe UI',9,'bold'));c.breadcrumb.pack(side='left',padx=10)
    actions=ttk.Frame(topinner);actions.pack(side='right')
    c.pair_button=ttk.Button(actions,text='Parear iPhone',command=c.toggle_qr);c.pair_button.pack(side='left',padx=4)
    c.stop_button=ttk.Button(actions,text='Parar câmera',command=c.disconnect.set,state='disabled');c.stop_button.pack(side='left',padx=(8,0))
    ttk.Separator(c.main,orient='horizontal').pack(fill='x')
    content=ttk.Panedwindow(c.main,orient='horizontal');content.pack(fill='both',expand=True)
    preview=ttk.Frame(content,padding=(28,20,28,16));content.add(preview,weight=1)
    ttk.Label(preview,text='ESTÚDIO DE CÂMERA',style='Eyebrow.TLabel').pack(anchor='w',pady=(0,6))
    ttk.Label(preview,text='Câmera ao vivo',style='Title.TLabel').pack(anchor='w')
    ttk.Label(preview,text='Imagem, enquadramento e ajustes pelo computador.',style='Header.TLabel',foreground=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=(5,16))
    card=ttk.Frame(preview,style='Card.TFrame',borderwidth=1,relief='solid');card.pack(fill='both',expand=True)
    bar=ttk.Frame(card,style='Panel.TFrame',padding=(14,10));bar.pack(fill='x')
    c.video_status=ttk.Label(bar,text='●  AGUARDANDO IPHONE',foreground=TOKENS['accent'],font=('Segoe UI',8));c.video_status.pack(side='left')
    c.metrics=ttk.Label(bar,text='Aguardando conexão',style='Muted.TLabel',font=('Segoe UI',8));c.metrics.pack(side='right')
    ttk.Separator(card,orient='horizontal').pack(fill='x')
    c.preview_surface=PreviewSurface(card);c.preview_surface.pack(fill='both',expand=True)
    footer=ttk.Frame(card,style='Panel.TFrame',padding=(14,9));footer.pack(fill='x')
    ttk.Label(footer,text='SMB CAMERA',style='Small.TLabel').pack(side='left')
    ttk.Label(footer,text='Processamento local',style='Small.TLabel').pack(side='right')
    row=ttk.Frame(preview,padding=(0,14,0,0));row.pack(fill='x')
    ttk.Button(row,text='Abrir perfil',command=lambda:open_profile(c)).pack(side='left')
    ttk.Button(row,text='Salvar perfil',command=lambda:save_profile(c),style='Accent.TButton').pack(side='right')
    inspector=ttk.Frame(content,style='Panel.TFrame',width=328);content.add(inspector,weight=0)
    inspectorhead=ttk.Frame(inspector,style='Panel.TFrame',padding=(18,18,18,14));inspectorhead.pack(fill='x')
    ttk.Label(inspectorhead,text='PERSONALIZAR',foreground=TOKENS['accent'],font=('Segoe UI',8,'bold')).pack(anchor='w')
    c.inspector_title=ttk.Label(inspectorhead,text='Câmera',font=('Segoe UI',13,'bold'));c.inspector_title.pack(anchor='w',pady=(7,0))
    ttk.Separator(inspector,orient='horizontal').pack(fill='x')
    c.tabs=ttk.Notebook(inspector,style='Inspector.TNotebook',width=328);c.tabs.pack(fill='both',expand=True)
    camera=ScrollPanel(c.tabs);color=ScrollPanel(c.tabs);background=ScrollPanel(c.tabs);profiles=ScrollPanel(c.tabs);connection=ScrollPanel(c.tabs);native=ScrollPanel(c.tabs);obs_output=ScrollPanel(c.tabs)
    labels=('Câmera','Imagem e cor','Fundo e recorte','Perfis','Conexão','Webcam Windows','Saída para OBS')
    for panel,label in zip((camera,color,background,profiles,connection,native,obs_output),labels):c.tabs.add(panel,text=label)
    c.control_panels={str(panel):panel for panel in (camera,color,background,profiles,connection,native,obs_output)}
    def navigate(index):
        started=c.diagnostics.start_navigation();c.tabs.select(index)
        if started is not None:
            c.root.after_idle(lambda:c.root.after_idle(lambda:c.diagnostics.finish_navigation(started)))
    for index,(label,symbol) in enumerate(zip(labels,('◉','☷','✂','▣','⇄','▤','▸'))):
        button=NavButton(c.navigation,label,symbol,lambda index=index:navigate(index));button.pack(fill='x',pady=(0,5));c.nav_buttons.append(button)
    def selected(_=None):
        index=c.tabs.index(c.tabs.select());c.breadcrumb.configure(text=labels[index]);c.inspector_title.configure(text=labels[index])
        for i,button in enumerate(c.nav_buttons):button.active=i==index;button.draw()
    c.tabs.bind('<<NotebookTabChanged>>',selected)
    c.native_status=ttk.Label(native.body,text='Consultando componente Windows...',wraplength=275);c.native_status.pack(anchor='w',pady=(4,14))
    c.native_button=ttk.Button(native.body,text='Ativar webcam',command=c.toggle_native_camera,state='disabled');c.native_button.pack(fill='x')
    ttk.Label(native.body,text='Quando disponível, selecione SMB Camera no aplicativo que vai receber a webcam. A saída padrão é opaca; o fundo pode usar uma imagem escolhida no painel.',style='Muted.TLabel',wraplength=275).pack(anchor='w',pady=14)
    c.obs_output_status=ttk.Label(obs_output.body,text='Consultando saída...',wraplength=275);c.obs_output_status.pack(anchor='w',pady=(4,14))
    c.obs_output_mode=ttk.Label(obs_output.body,text='',style='Muted.TLabel',wraplength=275);c.obs_output_mode.pack(anchor='w',pady=(0,14))
    ttk.Label(obs_output.body,text='No OBS, adicione nosso módulo em Ferramentas > Scripts e escolha a fonte SMB Camera. Cores, enquadramento e transparência vêm do painel.',wraplength=275).pack(anchor='w',pady=(0,12))
    ttk.Button(obs_output.body,text='Abrir pasta do módulo',command=c.open_obs_module).pack(fill='x')
    ttk.Label(obs_output.body,text='A fonte para OBS é separada da webcam Windows. No modo GPU, ambos precisam usar a mesma placa de vídeo. Uma fonte pode ser reutilizada em várias cenas por referência.',style='Muted.TLabel',wraplength=275).pack(anchor='w',pady=14)
    c.connection_labels={}
    for name,title in (('transport','TRANSPORTE'),('rates','VÍDEO E DADOS'),('age','ÚLTIMO QUADRO RECEBIDO'),
                       ('timing','TEMPO ATÉ O PC'),('stages','ETAPAS: TEMPO P95'),('gaps','INTERVALOS: P95'),('omissions','CONTADORES')):
        box=section(connection.body,title)
        label=ttk.Label(box,text='Aguardando vídeo',style='Muted.TLabel',wraplength=270,justify='left');label.pack(anchor='w')
        c.connection_labels[name]=label
    ttk.Label(connection.body,text='Tempos até o PC são estimativas com relógios sincronizados, não a latência total da câmera até a tela. Saltos de sequência não medem perda de bytes no TCP. A prévia apaga imagens sem quadros recentes.',style='Muted.TLabel',wraplength=270,justify='left').pack(anchor='w',pady=8)
    profilebox=section(profiles.body,'SEUS PERFIS')
    ttk.Label(profilebox,text='Salve cor, LUT, enquadramento e fundo para usar novamente.',wraplength=265).pack(anchor='w',pady=(0,12))
    ttk.Button(profilebox,text='Abrir perfil salvo',command=lambda:open_profile(c)).pack(fill='x',pady=4)
    ttk.Button(profilebox,text='Salvar perfil atual',command=lambda:save_profile(c),style='Accent.TButton').pack(fill='x',pady=4)
    ttk.Label(profiles.body,text='Os últimos ajustes também são guardados ao fechar o aplicativo.',style='Muted.TLabel',wraplength=280).pack(anchor='w',pady=12)
    def wheel(event):
        if str(event.widget).startswith(str(nav_panel)+'.'):
            nav_panel.canvas.yview_scroll(-int(event.delta/120),'units')
            return
        panel=c.control_panels.get(c.tabs.select())
        if panel:panel.canvas.yview_scroll(-int(event.delta/120),'units')
    root.bind_all('<MouseWheel>',wheel)
    ttk.Separator(c.main,orient='horizontal').pack(fill='x')
    c.note=ttk.Label(c.main,text='Primeira conexão: clique em Parear iPhone.',style='Header.TLabel',foreground=TOKENS['subtle'],font=('Segoe UI',8),padding=(28,9),wraplength=900);c.note.pack(fill='x')
    cam=section(camera.body,'DISPOSITIVO')
    c.control_status=ttk.Label(cam,text='Conecte o iPhone para ajustar a câmera.',style='Muted.TLabel',wraplength=285);c.control_status.pack(anchor='w',pady=(0,10))
    c.lens=LensButtons(cam,lambda id:c.controls.enqueue('lens',id));c.lens.pack(fill='x')
    c.zoom_label=ttk.Label(cam,text='Zoom');c.zoom_label.pack(anchor='w',pady=(12,4))
    c.zoom=Slider(cam,from_=1,to=2,command=c.zoom_changed,state='disabled');c.zoom.pack(fill='x')
    c.auto_focus=tk.BooleanVar(value=True)
    c.focus_auto=ttk.Checkbutton(cam,text='Foco automático',variable=c.auto_focus,command=c.focus_mode_changed,state='disabled');c.focus_auto.pack(anchor='w',pady=(12,4))
    c.focus_label=ttk.Label(cam,text='Foco');c.focus_label.pack(anchor='w')
    c.focus=Slider(cam,from_=0,to=1,default=.5,command=c.focus_changed,state='disabled');c.focus.pack(fill='x',pady=(4,0))
    exposure=section(camera.body,'EXPOSIÇÃO NO IPHONE')
    c.exposure_label=ttk.Label(exposure,text='Conecte o iPhone para ajustar a exposição.',wraplength=270);c.exposure_label.pack(anchor='w')
    c.exposure_bias=Slider(exposure,from_=-1,to=1,default=0,command=c.exposure_bias_changed,state='disabled');c.exposure_bias.pack(fill='x',pady=(5,8))
    c.sensor_label=ttk.Label(exposure,text='',style='Muted.TLabel',wraplength=270);c.sensor_label.pack(anchor='w')
    ttk.Label(exposure,text='Compensa a exposição automática da câmera. ISO e tempo mostram a última leitura confirmada; podem variar automaticamente.',style='Muted.TLabel',wraplength=270).pack(anchor='w',pady=(6,0))
    view=section(camera.body,'ENQUADRAMENTO')
    c.output_format=tk.StringVar(value='Horizontal');c.angle=tk.StringVar(value='0');c.mirror=tk.BooleanVar(value=False)
    formats=ttk.Combobox(view,textvariable=c.output_format,values=('Horizontal','Vertical'),state='readonly');formats.pack(fill='x')
    def format_changed(_=None):
        portrait=c.output_format.get()=='Vertical';angle=int(c.angle.get())
        if portrait and angle not in (90,270):angle=90
        if not portrait and angle in (90,270):angle=0
        c.angle.set(str(angle));c.preview_transform.set(output_format='portrait' if portrait else 'landscape',angle=angle)
        c.preview_surface.set_format('portrait' if portrait else 'landscape')
    formats.bind('<<ComboboxSelected>>',format_changed)
    ttk.Label(view,text='Rotação').pack(anchor='w',pady=(10,4))
    rotation=ttk.Combobox(view,textvariable=c.angle,values=('0','90','180','270'),state='readonly');rotation.pack(fill='x')
    rotation.bind('<<ComboboxSelected>>',lambda _:c.preview_transform.set(angle=int(c.angle.get())))
    ttk.Checkbutton(view,text='Espelhar',variable=c.mirror,command=lambda:c.preview_transform.set(mirror=c.mirror.get())).pack(anchor='w',pady=8)
    c.pan_widgets={}
    for key,label in [('pan_x','Posição horizontal'),('pan_y','Posição vertical')]:
        ttk.Label(view,text=label).pack(anchor='w');scale=Slider(view,from_=-1,to=1,default=0,command=lambda value,key=key:c.preview_transform.set(**{key:float(value)}));scale.pack(fill='x',pady=(3,8));c.pan_widgets[key]=scale
    ttk.Label(camera.body,text='ISO, obturador e balanço de branco físicos serão adicionados conforme suporte do aparelho.',style='Muted.TLabel',wraplength=300).pack(anchor='w',pady=6)
    c.color_widgets={};c.color_labels={};c.syncing_colors=False
    colorbar=ttk.Frame(color.body,style='Panel.TFrame');colorbar.pack(fill='x',pady=(0,12))
    c.compare_button=ttk.Button(colorbar,text='Comparar sem cor',command=lambda:compare(c));c.compare_button.pack(side='left')
    ttk.Button(colorbar,text='Restaurar cores',command=lambda:reset_colors(c)).pack(side='right')
    groups=[('AJUSTES BÁSICOS',[('exposure','Exposição','EV'),('contrast','Contraste',''),('saturation','Saturação','%'),('vibrance','Vibrância',''),('gamma','Gama','')]),
            ('TONS',[('shadows','Sombras',''),('highlights','Realces',''),('blacks','Pretos',''),('whites','Brancos','')]),
            ('BALANÇO DE COR',[('temperature','Temperatura relativa',''),('tint','Tinta: verde / magenta',''),('red','Vermelho','EV'),('green','Verde','EV'),('blue','Azul','EV')])]
    for title,items in groups:
        group=section(color.body,title)
        for key,label,unit in items:add_color_slider(c,group,key,label,unit)
    lut=section(color.body,'LUT 3D')
    c.lut_label=ttk.Label(lut,text='Nenhuma LUT',style='Muted.TLabel',wraplength=285);c.lut_label.pack(anchor='w',pady=(0,6))
    row=ttk.Frame(lut,style='Panel.TFrame');row.pack(fill='x')
    ttk.Button(row,text='Importar .cube',command=lambda:import_lut(c)).pack(side='left')
    ttk.Button(row,text='Remover',command=lambda:clear_lut(c)).pack(side='right')
    add_color_slider(c,lut,'lut_strength','Intensidade','%')
    ttk.Label(color.body,text='Ajustes de processamento SDR. Temperatura relativa não altera o balanço de branco físico do iPhone.',style='Muted.TLabel',wraplength=300).pack(anchor='w',pady=6)
    matte=section(background.body,'RECORTE NVIDIA' if c.matting_backend=='nvidia' else 'RECORTE')
    if c.matting_backend == 'nvidia':
        c.recorte_dependency = ttk.Label(matte, text='', style='Muted.TLabel', wraplength=275)
        c.recorte_dependency.pack(anchor='w')
        ttk.Button(matte, text='Localizar runtime NVIDIA…', command=c.select_matting_runtime).pack(fill='x', pady=(4, 5))
        c.check_matting_runtime()
    c.background_mode=tk.StringVar(value='Original')
    modes=('Original','Transparente','Imagem')
    if c.renderer=='gl':modes+=('GIF ou vídeo',)
    mode=ttk.Combobox(matte,textvariable=c.background_mode,values=modes,state='readonly');mode.pack(fill='x');mode.bind('<<ComboboxSelected>>',c.change_background)
    c.background_button=ttk.Button(matte,text='Escolher imagem de fundo',command=c.choose_background);c.background_button.pack(fill='x',pady=10)
    c.background_file_label=ttk.Label(matte,text='',style='Muted.TLabel',wraplength=270)
    c.background_file_label.pack(anchor='w')
    c.matte_quality=tk.StringVar(value='Qualidade')
    if c.matting_backend=='nvidia':
        quality=ttk.Combobox(matte,textvariable=c.matte_quality,values=('Qualidade','Desempenho'),state='readonly');quality.pack(fill='x')
        quality.bind('<<ComboboxSelected>>',lambda _:c.background.set(quality='quality' if c.matte_quality.get()=='Qualidade' else 'performance'))
    row=ttk.Frame(matte,style='Panel.TFrame');row.pack(fill='x',pady=(14,0))
    ttk.Label(row,text='Solidez do sujeito').pack(side='left')
    c.solidity_value=tk.StringVar(value='0%');ttk.Label(row,textvariable=c.solidity_value,style='Muted.TLabel').pack(side='right')
    def solidity_changed(raw):
        number=float(raw);c.solidity_value.set(f'{number:.0f}%')
        if not c.syncing_colors:c.background.set(solidity=number)
    c.solidity_scale=Slider(matte,from_=0,to=100,default=0,command=solidity_changed)
    c.solidity_scale.pack(fill='x',pady=(5,6))
    if c.renderer!='gl':c.solidity_scale.configure(state='disabled')
    ttk.Label(matte,text='Reduz partes semitransparentes. Aumentar demais pode incluir mais fundo. Dois cliques restauram o padrão.',style='Muted.TLabel',wraplength=270).pack(anchor='w')
    c.matting_status=ttk.Label(matte,text='Recorte desligado.',style='Muted.TLabel',wraplength=285);c.matting_status.pack(anchor='w',pady=(10,0))
    ttk.Label(background.body,text='Transparente usa um quadriculado apenas para visualizar as áreas removidas.',style='Muted.TLabel',wraplength=300).pack(anchor='w',pady=6)
    if c.renderer!='gl':
        c.tabs.tab(color,state='disabled');c.preview_surface.waiting.configure(text='Prévia em janela separada')
    c.qr_window=None;c.qr_visible=False
    root.update_idletasks();c.preview_hwnd=c.preview_surface.frame.winfo_id()
    settings=c.settings_path
    if settings.is_file():
        try:warning=studio_state.restore(studio_state.read(settings),c.colors,c.preview_transform,c.background);c.note.configure(text=warning or 'Seu último perfil foi restaurado.')
        except Exception:c.note.configure(text='Não foi possível restaurar o perfil anterior. Os padrões foram mantidos.')
    sync_widgets(c)
    root.protocol('WM_DELETE_WINDOW',c.close)

def add_color_slider(c,parent,key,label,unit):
    row=ttk.Frame(parent,style='Panel.TFrame');row.pack(fill='x',pady=(8,0))
    name=ttk.Label(row,text=label);name.pack(side='left');value=tk.StringVar();ttk.Label(row,textvariable=value,style='Muted.TLabel').pack(side='right')
    def changed(raw):
        if c.syncing_colors:return
        number=float(raw);c.colors.set(**{key:number});value.set(format_value(key,number,unit))
    low,high=PARAMETERS[key][1:];scale=Slider(parent,from_=low,to=high,default=PARAMETERS[key][0],command=changed);scale.pack(fill='x',pady=(4,7))
    name.bind('<Double-1>',lambda _:scale.set(PARAMETERS[key][0]))
    c.color_widgets[key]=scale;c.color_labels[key]=(value,unit)

def format_value(key,value,unit):return f'{value:+.2f} {unit}' if unit=='EV' else f'{value:.2f}' if key=='gamma' else f'{value:.0f}{unit}'

def sync_widgets(c):
    c.syncing_colors=True
    try:
        state=c.colors.get()
        for key,scale in c.color_widgets.items():
            scale.set(state[key]);var,unit=c.color_labels[key];var.set(format_value(key,state[key],unit))
        c.compare_button.configure(text='Comparar sem cor' if state['enabled'] else 'Voltar aos ajustes')
        c.lut_label.configure(text=state['lut'].title if state['lut'] else 'Nenhuma LUT')
        view=c.preview_transform.get();c.angle.set(str(view['angle']));c.mirror.set(view['mirror']);c.output_format.set('Vertical' if view['output_format']=='portrait' else 'Horizontal')
        for key,widget in c.pan_widgets.items():widget.set(view[key])
        c.preview_surface.set_format(view['output_format'])
        c.refresh_background_picker()
        bg=c.background.get();c.matte_quality.set('Qualidade' if bg['quality']=='quality' else 'Desempenho')
        c.solidity_scale.set(bg['solidity']);c.solidity_value.set(f"{bg['solidity']:.0f}%")
    finally:c.syncing_colors=False

def compare(c):c.colors.enable(not c.colors.get()['enabled']);sync_widgets(c)
def reset_colors(c):c.colors.reset();sync_widgets(c)
def clear_lut(c):c.colors.set_lut(None);sync_widgets(c)
def import_lut(c):
    path=filedialog.askopenfilename(parent=c.root,title='Importar LUT 3D',filetypes=[('LUT 3D','*.cube')])
    if path:
        try:
            file=Path(path)
            if file.stat().st_size>MAX_PRESET_BYTES:raise ValueError('LUT muito grande.')
            c.colors.set_lut(file.read_text(encoding='utf-8-sig'));sync_widgets(c)
        except Exception as exc:messagebox.showerror('Não foi possível importar a LUT',str(exc),parent=c.root)
def save_profile(c):
    path=filedialog.asksaveasfilename(parent=c.root,title='Salvar perfil do estúdio',defaultextension='.json',filetypes=[('Perfil Universal Camera','*.json')])
    if path:
        try:studio_state.write(Path(path),studio_state.snapshot(c.colors,c.preview_transform,c.background));c.note.configure(text='Perfil salvo. Ajustes e LUT incluídos, sem dados de pareamento.')
        except Exception as exc:messagebox.showerror('Não foi possível salvar',str(exc),parent=c.root)
def open_profile(c):
    path=filedialog.askopenfilename(parent=c.root,title='Abrir perfil do estúdio',filetypes=[('Perfil Universal Camera','*.json')])
    if path:
        try:
            warning=studio_state.restore(studio_state.read(Path(path)),c.colors,c.preview_transform,c.background);sync_widgets(c);c.note.configure(text=warning or 'Perfil aplicado.')
        except Exception as exc:messagebox.showerror('Não foi possível abrir o perfil',str(exc),parent=c.root)

def toggle_qr(c):
    if c.qr_window is None:
        import qrcode
        from PIL import ImageTk
        window=tk.Toplevel(c.root);window.title('Parear iPhone');window.geometry('460x520');window.configure(bg=PANEL);window.resizable(False,False)
        frame=ttk.Frame(window,style='Panel.TFrame',padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Parear seu iPhone',font=('Segoe UI',18,'bold')).pack(anchor='w',pady=(0,12))
        ttk.Label(frame,text='No app do iPhone, toque em Ler QR do PC.',wraplength=400).pack(anchor='w',pady=(0,12))
        code=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=4,border=4);code.add_data(c.pairing.uri());code.make(fit=True)
        c.photo=ImageTk.PhotoImage(code.make_image(fill_color='black',back_color='white').convert('RGB'),master=window)
        ttk.Label(frame,image=c.photo).pack()
        ttk.Label(frame,text='Confirme este PC uma vez. Depois basta ativar a câmera.',wraplength=400).pack(anchor='w',pady=12)
        window.protocol('WM_DELETE_WINDOW',lambda:toggle_qr(c));c.qr_window=window;c.qr_visible=False
    c.qr_visible=not c.qr_visible
    if c.qr_visible:c.qr_window.deiconify();c.qr_window.lift()
    else:c.qr_window.withdraw()
