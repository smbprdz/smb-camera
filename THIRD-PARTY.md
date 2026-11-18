# Componentes de terceiros

A licença do projeto cobre o código autoral. Os componentes abaixo mantêm suas licenças. As dependências binárias do painel são baixadas de seus distribuidores, com versões e hashes registrados em `requirements-windows-beta.txt` e `docs/NATIVE.lock.json`.

| Componente | Uso | Origem |
| --- | --- | --- |
| CPython e Tcl/Tk | Runtime e interface Windows | [Python](https://www.python.org/about/legal/) |
| OpenSSL | Identidade e certificado de pareamento | [OpenSSL](https://openssl-library.org/source/license/) |
| PyAV e FFmpeg | Decodificação e escrita MOV | [PyAV](https://github.com/PyAV-Org/PyAV) · [FFmpeg](https://ffmpeg.org/legal.html) |
| NumPy, Pillow, OpenCV, qrcode, Zeroconf e dependências transitivas | Imagem, QR e descoberta local | Os pacotes instalados conservam metadados de licença e avisos nas pastas `*.dist-info`. |
| ModernGL e glcontext | Renderização OpenGL | [ModernGL](https://github.com/moderngl/moderngl) · [glcontext](https://github.com/moderngl/glcontext) |
| SDL2 | Janela e contexto gráfico | [SDL2](https://github.com/libsdl-org/SDL/tree/release-2.32.10) |
| NVIDIA Video Effects SDK | Recorte local opcional | [NVIDIA](https://www.nvidia.com/en-us/geforce/broadcasting/broadcast-sdk/resources/) |
| OBS Studio | Consumidor externo da fonte SMB Camera | [OBS Studio](https://github.com/obsproject/obs-studio) |

O código experimental da câmera virtual Windows contém adaptações do exemplo Windows Camera da Microsoft. Seus avisos MIT ficam em `docs/licenses/Microsoft-Windows-Camera-LICENSE.txt`. Os avisos associados ao WIL e a bibliotecas gráficas usadas no desenvolvimento estão em `docs/licenses/`. Os binários experimentais dessa câmera não fazem parte do ZIP da beta.

O nome, a marca e os ícones SMB identificam os builds do SIMBAproduz. A licença para copiar e modificar o código não concede direitos de marca.
