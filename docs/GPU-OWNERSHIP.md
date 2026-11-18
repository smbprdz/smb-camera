# Sincronização GPU: estabilidade antes de 60 FPS

O aplicativo em uso continua 0.15.1 com a ponte RAM já comprovada. Os novos testes tratam exclusivamente de um transporte GPU autoral em laboratório. Não instalam plugin, alteram o OBS do usuário ou habilitam um modo novo no iPhone.

## Propriedade e recuperação

O recurso D3D11 é criado com a flag pública SHARED_KEYEDMUTEX. O produtor adquire a chave 0 antes de escrever, publica a chave 1 ao terminar e o consumidor adquire 1 antes de ler. Ao concluir, devolve 0. A aquisição usa prazo zero no caminho de renderização: ocupado significa pular aquela oportunidade, nunca escrever em paralelo ou esperar indefinidamente.

O resultado de AcquireSync exige comparação exata. WAIT_TIMEOUT e WAIT_ABANDONED são valores positivos; tratá-los como sucesso por não serem HRESULT negativo seria um defeito. Timeout não concede propriedade. Recurso abandonado é descartado e substituído por outra textura e época.

Os testes gerados em dois processos verificaram chave errada, receptor deliberadamente parado enquanto mantém a propriedade, igualdade dos pixels e morte intencional do receptor com o mutex adquirido. O produtor recebeu WAIT_ABANDONED, criou uma textura nova e retomou com outra época. Não liberou acesso concorrente para esconder um problema.

Uma fonte Lua própria de laboratório também recebeu uma textura mutável no motor oficial OBS 32.2.2. Ela adquire o recurso, copia a imagem somente pela GPU para uma textura privada, devolve a propriedade e desenha a cópia privada. O teste pausou o produtor até a imagem expirar, retomou e substituiu o recurso por outra época. Cor, alpha e recuperação passaram. O arquivo de controle entre esses processos descartáveis não é ainda o endpoint público do produto: identidade SID/PID, adapter LUID, controle de múltiplos consumidores e negociação de modo precisam ser integrados antes de uso real.

## Cadência não se confunde com estabilidade do acesso

As provas foram solicitadas em ritmos de 30 e 60 FPS. Isso não demonstra 30 ou 60 imagens novas por segundo. A checagem exata lê cada frame para a CPU e calcula hashes apenas sobre dados gerados; esse validador limita a cadência. O teste com OBS também contou oportunidades de escrita recusadas enquanto o receptor estava ocupado. Portanto o gate de propriedade/recuperação passou, mas cadência final, estabilidade longa e orçamento durante jogo não foram aprovados.

O primeiro piloto usou incorretamente o valor 0x10 de uma flag diferente; o driver recusou CreateTexture2D. A declaração foi conferida no SDK Windows: SHARED_KEYEDMUTEX é 0x100. A correção ganhou teste específico; não afrouxou validação, não alterou drivers e não foi aplicada ao aplicativo em uso.

Uma repetição no motor OBS também falhou: o wrapper gráfico normaliza WAIT_TIMEOUT para o errno ETIMEDOUT, que vale 138 no CRT Windows. O receptor estava comparando esse retorno com o 258 da API DXGI direta e tratava uma espera normal como erro. A diferença foi conferida no código oficial OBS 32.2.2 e no header errno.h do SDK, corrigida em uma classificação separada e coberta por teste executado em Lua. Códigos desconhecidos continuam exigindo descarte/recriação, não acesso presumido. A falha anterior fica preservada; um PASS inicial não bastava para certificar esse comportamento.

## 60 FPS no produto

O iPhone 11 Pro Max tem suporte de gravação anunciado para 1080p60 e 4K60, mas o VideoMode do nosso app ainda oferece apenas 1080p30 e 4K30. Cada combinação real de câmera, lente, formato e encoder será consultada antes de oferecer um modo. [Especificações Apple](https://support.apple.com/en-us/111878).

| Configuração | Prazo por quadro | Pixels por segundo, sem contar efeitos | Estado desta fatia |
| --- | --- | --- | --- |
| 1080p30 | 33,3 ms | 62,2 milhões | Referência funcional atual; estabilidade longa ainda pendente |
| 1080p60 | 16,7 ms | 124,4 milhões | Objetivo a implementar e medir, não homologado no iPhone |
| 4K30 | 33,3 ms | 248,8 milhões | Captura teve prova curta anterior; transporte GPU completo não aprovado |
| 4K60 | 16,7 ms | 497,7 milhões | Sem implementação/validação ponta a ponta |

Essa contagem compara somente volume de pixels. Não prevê linearmente consumo de CPU/GPU, bitrate, bateria ou qualidade. Remover fundo pode ser o estágio dominante; dobrar FPS aumenta a demanda de inferência se for executada a cada frame. Repetir quadros, reutilizar máscara sem controle de alinhamento ou reduzir qualidade silenciosamente não constitui suporte a 60 FPS.

A sequência de liberação exige primeiro integração e recuperação da ponte GPU, depois 1080p60 Original e, por fim, recorte com o jogo e a live em condições representativas. Medir cadência de imagens novas, latência com incerteza, temperatura, fila/memória e reconexão. Escolha de 60 FPS será opcional; estabilidade é condição de aceite.

## Reprodução de laboratório

```powershell
.venv/Scripts/python.exe tools/gpu_lab/ownership_probe.py --size small --fps 30 --frames 60
.venv/Scripts/python.exe tools/gpu_lab/ownership_probe.py --size 1080 --fps 30 --frames 120
.venv/Scripts/python.exe tools/gpu_lab/ownership_probe.py --size 1080 --fps 60 --frames 120
.venv/Scripts/python.exe tools/gpu_lab/keyed_obs_probe.py --fps 30
.venv/Scripts/python.exe tools/gpu_lab/keyed_obs_probe.py --fps 60
```

Workers são descartáveis e ficam em JobObject com prazo de 20/60 s para propriedade e 30 s para OBS. Resultados são locais em output. A fonte OBS de laboratório usa um arquivo próprio por execução, sem reaproveitar resultado de outra rodada. Não executa um novo binário C++ nem hospeda a DLL de webcam bloqueada. Bindings de bancada e protótipos Lua não equivalem ao motor distribuível final homologado.

Contrato oficial: [AcquireSync e seus estados](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/nf-dxgi-idxgikeyedmutex-acquiresync), [ReleaseSync](https://learn.microsoft.com/en-us/windows/win32/api/dxgi/nf-dxgi-idxgikeyedmutex-releasesync), [interoperabilidade GL/D3D](https://registry.khronos.org/OpenGL/extensions/NV/WGL_NV_DX_interop2.txt). Não há código Spout/VCam ou mecanismo de desativar proteções.
