# Compartilhamento GPU autoral: prova parcial, fora do aplicativo

O caminho por RAM já recebeu vídeo real do iPhone com alpha na fonte OBS autoral. O próximo candidato elimina a transferência do frame completo pela CPU no trecho de exportação, usando APIs oficiais. Esta rodada apenas acrescenta ferramentas de laboratório em tools/gpu_lab; o motor e a versão em execução permanecem 0.15.1.

## Mecanismo e provas

WGL_NV_DX_interop2 está disponível na RTX 3060 da bancada. Um adaptador nosso por ctypes cria recursos D3D11/DXGI e os registra no contexto OpenGL. Lock/unlock da interoperabilidade envolve cada renderização. Outro dispositivo D3D, no mesmo adaptador, abre a textura compartilhada. Fonte e bindings foram escritos para APIs públicas, com os slots COM e layouts conferidos no Windows SDK 10.0.26100.

O teste B_dev renderizou 60 variações geradas em 64x36, com cor, espelho, giro e alpha, e o receptor confirmou bytes exatamente iguais aos do exportador de referência. Na prova entre processos, o produtor só reutiliza a textura depois do ACK de validação. No holdout 1080p, as quatro fases ABBA passaram, com 120 quadros medidos em cada fase. O envio candidato não executou readback de pixels.

A mediana dos dois p95 de exportação foi aproximadamente 10,16 ms no caminho RAM e 1,47 ms no candidato GPU nesse ensaio. A comparação cobre somente o trecho de exportação do emissor. Ambos os caminhos calculam e validam uma referência gerada fora da região medida; não é comparação ponta a ponta nem redução demonstrada do consumo total. Tempos de CPU curtos são quantizados no Windows e não permitem afirmar CPU zero.

Outra prova criou três texturas GPU imutáveis no nosso produtor e as importou diretamente no motor OBS 32.2.2 de um processo separado, através de uma fonte Lua nossa de laboratório. Foram 119 amostras, com três cores distintas, alpha zero, parcial e opaco corretos, sem erros de callback. Nenhum plugin foi instalado no OBS do dono. Esse teste demonstra compatibilidade da importação; não prova sincronização de uma câmera mutável ao vivo.

## Gate que não passou

O primeiro runner monolítico ultrapassou o prazo previsto e foi interrompido. A orquestração foi dividida por fase, sem alterar candidato, dados ou critérios do holdout, com limite explícito de 60 s e JobObject. A primeira fase 4K ainda excedeu esse prazo e foi encerrada. Não há resultado completo 4K, e o gate conjunto não foi aprovado. Isso não demonstra que 4K seja impossível nem define um limite artificial de produto; faltam diagnóstico e uma rodada apropriada de validação.

O candidato não foi promovido a transporte do app. H2 com PBO ficou não executada, já que a evidência parcial da rota direta não justifica trocar de mecanismo. Não se afinou código contra o holdout para forçar resultado positivo. Resultados e limitações em GPU-SHARING-LAB-PROOF.json.

## Trabalho necessário antes da integração

Compartilhamento em câmera ao vivo precisa de sincronização e propriedade da textura por consumidor, fila limitada, identidade SID/PID/epoch, verificação de adapter LUID, mudança de modo, perda e retomada e limpeza após crash. O receptor não pode ler uma textura enquanto o produtor a sobrescreve. O teste com ACK e as texturas imutáveis evitam a corrida somente no laboratório.

O renderer atual também usa upload de YUV e máscara; retirar um readback entre aplicativos não elimina todas essas cópias. Custo durante jogo, cadência de imagens novas e latência captura-tela precisam ser medidos quando o transporte estiver integrado. Nenhuma chamada ao SDK de IA foi usada no benchmark deste laboratório.

Fontes de contrato: [Khronos WGL_NV_DX_interop2](https://registry.khronos.org/OpenGL/extensions/NV/WGL_NV_DX_interop2.txt), [interoperabilidade e sincronização WGL](https://registry.khronos.org/OpenGL/extensions/NV/WGL_NV_DX_interop.txt), [Microsoft OpenSharedResource](https://learn.microsoft.com/en-us/windows/win32/api/d3d11/nf-d3d11-id3d11device-opensharedresource), [API gráfica OBS 32.2.2](https://github.com/obsproject/obs-studio/blob/32.2.2/libobs/graphics/graphics.h). Nenhum código Spout/VCam foi incorporado.
