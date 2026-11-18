"""Locate an OBS installation and guide setup of the SMB Camera Lua source."""
import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk

ROOT = Path(__file__).resolve().parents[1]
OBS_BINARY = Path('bin/64bit/obs64.exe')
DISCOVER_WINDOWS = r"""
Get-CimInstance Win32_Process -Filter "Name='obs64.exe'" -ErrorAction SilentlyContinue |
  Where-Object ExecutablePath | ForEach-Object {
    @{path=$_.ExecutablePath; running=$true; portable=($_.CommandLine -match '(^|\s)--portable(\s|$)')} |
      ConvertTo-Json -Compress
  }
$keys=@('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
Get-ItemProperty -Path $keys -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -like 'OBS Studio*' -and $_.InstallLocation } |
  ForEach-Object { @{path=$_.InstallLocation} | ConvertTo-Json -Compress }
$desktop=[Environment]::GetFolderPath('Desktop')
$programs=@([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('CommonPrograms'))
$links=@()
if($desktop){
  $links+=@(Get-ChildItem -LiteralPath $desktop -Filter '*OBS*.lnk' -File -ErrorAction SilentlyContinue)
}
foreach($location in $programs){
  if($location){
    $links+=@(Get-ChildItem -LiteralPath $location -Filter '*OBS*.lnk' -File -Recurse -ErrorAction SilentlyContinue)
  }
}
$shortcuts=New-Object -ComObject WScript.Shell
$links | ForEach-Object {
      $entry=$shortcuts.CreateShortcut($_.FullName)
      if($entry.TargetPath -and $entry.TargetPath.EndsWith('obs64.exe',[StringComparison]::OrdinalIgnoreCase)){
        @{path=$entry.TargetPath; portable=($entry.Arguments -match '(^|\s)--portable(\s|$)')} |
          ConvertTo-Json -Compress
      }
    }
"""


@dataclass(frozen=True)
class ObsInstallation:
    executable: str
    settings: str
    portable: bool
    running: bool


def inspect_obs(path, *, portable=False, running=False, appdata=None):
    if not path or str(path).startswith(('\\\\', '//')):
        return None
    binary = Path(path)
    if binary.suffix.lower() != '.exe':
        binary = binary / OBS_BINARY
    if not binary.is_absolute() or not binary.is_file() or binary.name.lower() != 'obs64.exe':
        return None
    binary = binary.resolve()
    if binary.parent.name.lower() != '64bit' or binary.parent.parent.name.lower() != 'bin':
        return None
    install_root = binary.parents[2]
    portable = portable or any((install_root / marker).is_file()
                               for marker in ('portable_mode', 'portable_mode.txt'))
    standard_settings = appdata or os.environ.get('APPDATA') or Path.home() / 'AppData/Roaming'
    settings = install_root / 'config/obs-studio' if portable else Path(standard_settings) / 'obs-studio'
    return ObsInstallation(str(binary), str(settings), bool(portable), bool(running))


def discover_obs(near=None):
    parents = (Path(near), ROOT.parent) if near else (ROOT.parent,)
    paths = [{'path': folder / name} for folder in parents
             for name in ('OBS Portable', 'OBS-Portable', 'OBS', 'obs-studio')]
    paths += [{'path': Path(os.environ[key]) / 'obs-studio'}
              for key in ('ProgramFiles', 'ProgramW6432') if os.environ.get(key)]
    if os.name == 'nt':
        try:
            prefix = '[Console]::OutputEncoding = [Text.Encoding]::UTF8\n'
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                                     '-Command', prefix + DISCOVER_WINDOWS],
                                    capture_output=True, timeout=6,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            for line in result.stdout.decode('utf-8', errors='replace').splitlines():
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if isinstance(data, dict) and isinstance(data.get('path'), str):
                    paths.append(data)
        except (OSError, subprocess.TimeoutExpired):
            pass
    found = {}
    for item in paths:
        obs = inspect_obs(**item)
        if obs:
            # A live invocation describes the active OBS mode more accurately
            # than a shortcut with different arguments.
            key = os.path.normcase(obs.executable)
            old = found.get(key)
            if old is None or obs.running or (obs.portable and not old.running):
                found[key] = obs
    return list(found.values())


def show_setup(installations):
    root = tk.Tk()
    root.title('SMB Camera | Configurar OBS')
    root.geometry('745x450')
    root.minsize(660, 430)
    panel = ttk.Frame(root, padding=24)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='Configurar OBS', font=('Segoe UI', 21, 'bold')).pack(anchor='w')
    ttk.Label(panel, text='Escolha onde abrir o OBS e adicione a fonte SMB Camera.').pack(anchor='w', pady=(3, 19))

    ttk.Label(panel, text='Instalação do OBS x64').pack(anchor='w')
    selection = ttk.Combobox(panel, state='readonly')
    selection.pack(fill='x', pady=(4, 6))
    location = tk.StringVar()
    ttk.Label(panel, textvariable=location, wraplength=620, justify='left').pack(anchor='w')
    status = tk.StringVar()
    ttk.Label(panel, textvariable=status, wraplength=620, justify='left').pack(side='bottom', anchor='w')
    actions = ttk.Frame(panel)
    actions.pack(fill='x', pady=(10, 15))
    script = ROOT / 'integrations/obs/smb-camera.lua'
    endpoint = ROOT / 'runtime/alpha-output.json'

    def refresh(event=None, index=None):
        labels = [f'{"Portátil" if obs.portable else "Instalado"}  ·  {obs.executable}'
                  for obs in installations]
        selection.configure(values=labels)
        if index is not None:
            selection.current(index)
        selected = selection.current()
        if selected >= 0:
            obs = installations[selected]
            location.set(f'Configuração do OBS: {obs.settings}')
            open_obs.state(['!disabled'])
        else:
            selection.set('')
            location.set('Selecione o arquivo obs64.exe se o OBS estiver em outra pasta.')
            open_obs.state(['disabled'])

    def browse():
        path = filedialog.askopenfilename(parent=root, title='Localizar o OBS',
                                          filetypes=[('OBS x64', 'obs64.exe')])
        if not path:
            return
        obs = inspect_obs(path)
        if not obs:
            status.set('Escolha o executável obs64.exe em uma pasta local.')
            return
        for i, known in enumerate(installations):
            if os.path.normcase(known.executable) == os.path.normcase(obs.executable):
                refresh(index=i)
                return
        installations.append(obs)
        refresh(index=len(installations) - 1)
        status.set('Instalação selecionada.')

    opened_here = {}

    def launch():
        selected = selection.current()
        if selected < 0:
            return
        obs = installations[selected]
        existing = opened_here.get(obs.executable)
        if obs.running or (existing is not None and existing.poll() is None):
            status.set('O OBS selecionado já está aberto. Use Ferramentas → Scripts nessa janela.')
            return
        command = [obs.executable]
        if obs.portable:
            command.append('--portable')
        try:
            opened_here[obs.executable] = subprocess.Popen(command, cwd=Path(obs.executable).parent)
        except OSError:
            status.set('Não foi possível abrir o OBS. Confira o caminho selecionado.')
            return
        status.set('OBS aberto. Adicione o script em Ferramentas → Scripts.')

    def copy(path, name):
        if not path.is_file():
            status.set('Abra o SMB Camera para gerar o arquivo de conexão.')
            return
        root.clipboard_clear()
        root.clipboard_append(str(path))
        status.set(f'Caminho de {name} copiado.')

    ttk.Button(actions, text='Localizar obs64.exe', command=browse).pack(side='left', padx=(0, 8))
    open_obs = ttk.Button(actions, text='Abrir OBS selecionado', command=launch)
    open_obs.pack(side='left')
    ttk.Separator(panel).pack(fill='x')
    ttk.Label(panel, text='Adicionar a fonte', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(12, 5))
    ttk.Label(panel, text='1. No OBS, abra Ferramentas → Scripts. Clique em + e cole o caminho do script.',
              wraplength=620).pack(anchor='w')
    ttk.Label(panel, text='2. Em Fontes, clique em + e selecione SMB Camera.',
              wraplength=620).pack(anchor='w', pady=(4, 0))
    ttk.Label(panel, text='3. Se o OBS pedir a conexão, aponte para o arquivo do SMB Camera em execução.',
              wraplength=620).pack(anchor='w', pady=(4, 7))
    paths = ttk.Frame(panel)
    paths.pack(fill='x')
    ttk.Button(paths, text='Copiar caminho do script', command=lambda: copy(script, 'script')).pack(side='left', padx=(0, 8))
    ttk.Button(paths, text='Copiar caminho da conexão', command=lambda: copy(endpoint, 'conexão')).pack(side='left')
    selection.bind('<<ComboboxSelected>>', refresh)
    refresh(index=0 if installations else None)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--near', type=Path, help='Also look for OBS beside the installer.')
    parser.add_argument('--list', action='store_true', help='Print the inventory without opening OBS.')
    args = parser.parse_args()
    installations = discover_obs(args.near)
    if args.list:
        print(json.dumps([asdict(obs) for obs in installations], ensure_ascii=True))
    else:
        show_setup(installations)


if __name__ == '__main__':
    main()
