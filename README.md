# SMB Camera

Use a câmera do iPhone no Windows e como fonte no OBS. Ajuste lentes, foco, zoom, exposição, cor e enquadramento pelo PC. Com recorte NVIDIA opcional, o painel compõe fundo transparente, imagem, GIF ou vídeo em loop. A gravação original guarda o H.264 recebido em MOV e pode incluir o microfone do iPhone.

## Beta

| Item | Referência testada |
| --- | --- |
| Dispositivo | iPhone 11 Pro Max, iOS 18.3.1, SMB Camera 0.9 |
| Conexão | USB, 1920×1080 a 30 fps, H.264 SDR |
| PC | SMB Camera 0.19.1, Windows 11 x64 e RTX 3060 Laptop |
| OBS | Fonte SMB Camera por memória ou textura GPU. Provas de bancada em 32.2.2 e composição real em 33.0.0 portátil |
| Arquivo | MOV com vídeo original. Áudio opcional PCM do iPhone |

Comece pela [preparação do Windows](docs/INSTALL-WINDOWS.md), depois siga a [instalação no iPhone](docs/INSTALL-IOS.md). O compartilhamento GPU usa um leitor e depende de OBS e painel na mesma placa. O [recorte NVIDIA](docs/NVIDIA-BETA.md) é opcional. O componente de webcam virtual Windows está em desenvolvimento. A primeira beta foca no OBS e na gravação original.

## Desenvolvimento

- `ucs/` contém o painel, receptor e compositor.
- `apps/ios/` contém o app Swift e o projeto Xcode.
- `integrations/obs/` contém a fonte Lua.
- `native/` contém o trabalho experimental do motor e da câmera Windows.
- `tools/package_beta.py` exporta o ZIP Windows a partir de um commit Git. O ZIP tem a preparação e os launchers na raiz.

```powershell
python tools/package_beta.py --ref HEAD
```

[Protocolo](docs/PROTOCOL.md) · [Privacidade](docs/PRIVACY.md) · [Licença MIT](LICENSE) · [Componentes de terceiros](THIRD-PARTY.md)
