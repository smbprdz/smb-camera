# Contribuir com o SMB Camera

Abra uma issue para descrever o problema e o resultado esperado. Português e inglês são bem-vindos. Informe versões do desktop e do iPhone, Windows, OBS, GPU e o tipo de conexão. Use um sinal gerado para reproduzir falhas de vídeo sempre que possível.

## Ambiente de desenvolvimento

Use Python 3.11 x64 no Windows. O arquivo de dependências da beta fixa os hashes dos pacotes Windows. Para testar a câmera e o OBS, leia o [guia Windows](docs/INSTALL-WINDOWS.md). FFmpeg no PATH permite executar as provas de gravação com mídia gerada.

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install --require-hashes -r requirements-windows-beta.txt
.venv/Scripts/python.exe -m pip install -r requirements-diagnostics.txt
.venv/Scripts/python.exe tools/install_sdl.py
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Os ensaios gráficos opcionais requerem uma sessão Windows com GPU. Os testes de recorte NVIDIA requerem também o runtime licenciado. O [guia iOS](docs/INSTALL-IOS.md) descreve a compilação e a assinatura pessoal por dispositivo.

Para gerar o ZIP Windows do código congelado em um commit:

```powershell
.venv/Scripts/python.exe tools/package_beta.py --ref HEAD
```

Em pull requests, explique o comportamento e indique como reproduziu e testou. Confira seus anexos e remova QR, chaves, tokens, mídia pessoal e caminhos de usuário antes de enviá-los. [Privacidade](docs/PRIVACY.md)
