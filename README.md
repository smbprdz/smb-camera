<h1 align="center">
  <img src="ucs/assets/live-icon.png" alt="" width="36" height="36"> SMB Camera
</h1>

<p align="center">
  <a href="docs/INSTALL-WINDOWS.md"><strong>Começar no Windows</strong></a> ·
  <a href="docs/INSTALL-IOS.md">Preparar o iPhone</a> ·
  <a href="docs/INSTALL-WINDOWS.md#obs-e-gravação">OBS</a> ·
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="#beta"><img src="https://img.shields.io/badge/status-beta-b82f75?style=flat-square" alt="Candidata à beta"></a>
  <a href="docs/INSTALL-WINDOWS.md"><img src="https://img.shields.io/badge/Windows-11%20x64-27669e?style=flat-square" alt="Windows 11 x64"></a>
  <a href="#beta"><img src="https://img.shields.io/badge/USB-1080p30-30394c?style=flat-square" alt="USB 1080p30"></a>
  <a href="#beta"><img src="https://img.shields.io/badge/testes-164%20passaram-247056?style=flat-square" alt="164 testes passaram na seleção pública"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licen%C3%A7a-MIT-27669e?style=flat-square" alt="Licença MIT"></a>
</p>

<p align="center"><strong>Seu iPhone no OBS, com recorte de fundo e gravação original.</strong></p>

<p align="center">
  <img src="docs/media/smb-camera-desktop.jpg" alt="Painel real do SMB Camera com recorte transparente e controles de gravação na lateral" width="960">
</p>

<p align="center"><sub>Captura do app com sinal de demonstração e uma pessoa fictícia.</sub></p>

## O que o SMB Camera faz

- **Controle pelo PC.** Selecione lente, foco, zoom e exposição. Ajuste cor, enquadramento e LUTs no painel.
- **Fonte própria para OBS.** Use fundo transparente, imagem, GIF ou vídeo com o [recorte NVIDIA opcional](docs/NVIDIA-BETA.md).
- **Gravação original.** Salve o vídeo H.264 recebido em MOV, sem recompressão, com a opção de incluir o microfone do iPhone.

## Beta

| Componente | Referência testada |
| --- | --- |
| iPhone | SMB Camera 0.9 no iPhone 11 Pro Max com iOS 18.3.1 |
| PC | Desktop 0.19.1 no Windows 11 x64 com RTX 3060 Laptop |
| Vídeo | USB 1080p30 em H.264 SDR |
| OBS | Fonte SMB Camera em OBS x64 32.2.2 e 33.0.0 portátil |
| Gravação | MOV com H.264 original e áudio PCM opcional |

Na validação da seleção pública, 164 testes passaram. Um teste do runtime NVIDIA opcional ficou fora dessa rodada.

O app iOS usa [assinatura pessoal](docs/INSTALL-IOS.md). A fonte OBS usa uma conexão local e a beta foca em OBS e em gravação original. O componente de webcam do Windows está em desenvolvimento.

## Código e colaboração

O painel fica em `ucs/`, o app do iPhone em `apps/ios/` e a fonte do OBS em `integrations/obs/`. As instruções para reproduzir o ZIP, rodar testes e reportar um problema ficam em [Contribuir](CONTRIBUTING.md).

[Protocolo](docs/PROTOCOL.md) · [Privacidade](docs/PRIVACY.md) · [Licença](LICENSE) · [Componentes de terceiros](THIRD-PARTY.md)
