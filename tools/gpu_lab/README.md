# Laboratório autoral de compartilhamento GPU

Ferramentas experimentais, não importadas pelo aplicativo. Usam somente APIs públicas D3D11, DXGI e WGL; nenhum SDK Spout/VCam, driver novo, mudança de segurança ou executável C++ próprio. Os fixtures são gerados, sem câmera/microfone e sem gravação pessoal.

Requer Windows x64, GPU/driver com WGL_NV_DX_interop2, Python/dependências da bancada e, para a prova de importação OBS, as bibliotecas oficiais instaladas do OBS 32.2.2. Escolhe o adaptador D3D cujo nome corresponde ao renderer GL, registra seu LUID e recusa adaptador diferente no receptor. Isso não é suporte universal a todas as GPUs.

```powershell
.venv/Scripts/python.exe tools/gpu_lab/dev.py
.venv/Scripts/python.exe tools/gpu_lab/run_test.py
.venv/Scripts/python.exe tools/gpu_lab/obs_import.py
```

O primeiro comando confere 60 quadros pequenos gerados em dois dispositivos D3D. O segundo executa o holdout ABBA, 120 quadros medidos por fase após oito de aquecimento, primeiro em 1080p e depois em 4K. Cada fase tem prazo de 60 s em um JobObject com encerramento da árvore. Todos os resultados vão para output/gpu-lab, nunca para esta pasta. O terceiro prepara três texturas geradas e imutáveis e as importa na fonte Lua de laboratório dentro do motor OBS isolado, sem abrir a interface ou modificar seus perfis/cenas.

O receptor de validação faz staging/readback exclusivamente para comparar os bytes com a referência. Esses custos são excluídos igualmente do tempo de exportação medido. O emissor candidato renderiza diretamente na textura D3D compartilhada e não lê o frame de volta no trecho cronometrado. Isso não transforma o pipeline inteiro em zero-copy; captura, decode e máscara atuais ainda possuem cópias.

Na validação entre processos, o emissor espera o ACK do receptor antes de reutilizar a textura. Na prova OBS, as texturas são imutáveis enquanto ele as lê. Nenhum desses casos implementa ainda protocolo de GPU para câmera ao vivo, proteção contra reaproveitar uma textura em leitura, mudança de resolução/GPU, queda do produtor ou identidade do consumidor. Handles legados enviados por stdin a um filho de teste não constituem uma API pública segura do produto.

Resultado desta rodada: B_dev e quatro fases 1080p passaram com pixels/alpha idênticos, e a importação direta no motor OBS preservou cores e transparência. O primeiro teste monolítico foi interrompido após exceder o prazo; o runner foi dividido por fase com timeout explícito. No holdout delimitado, a primeira fase 4K excedeu 60 s. O gate completo continua reprovado/incompleto e o transporte do aplicativo não foi substituído. Não repetir ou afrouxar os critérios só para obter PASS.

Tempos são do trecho de exportação do emissor, não da latência total, da fonte OBS em movimento ou do desempenho durante jogo. O relógio de CPU do Windows é granular demais para afirmar custo zero em uma fase curta. Referência de contrato e limites: [GPU-SHARING-LAB.md](../../docs/GPU-SHARING-LAB.md).

## Textura mutável e falhas

`ownership_probe.py` verifica acesso exclusivo com mutex DXGI, receptor atrasado, abandono intencional e recriação. `keyed_obs_probe.py` usa a fonte própria `obs_keyed.lua` no motor OBS isolado, copia a imagem pela GPU sob propriedade exclusiva e verifica pausa/retomada e mudança de recurso. Aceitam ritmo solicitado de 30 ou 60 FPS; o resultado aprova propriedade/recuperação, não a cadência real do produto. Identidade e protocolo público de produção ainda precisam de integração. [Contrato e comandos](../../docs/GPU-OWNERSHIP.md).
