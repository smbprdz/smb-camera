# Desktop 0.16: ponte GPU integrada, experimental

O compositor do aplicativo agora pode fornecer sua imagem tratada diretamente em uma textura D3D11 compartilhada. Cor, enquadramento e alpha usam os mesmos shaders do exportador de referência. Não é um novo modelo de recorte nem uma webcam registrada no Windows. A saída RAM continua disponível explicitamente para compatibilidade.

## Executar e receber

```powershell
.venv/Scripts/pythonw.exe -m ucs.desktop --decoder d3d11va --renderer gl --matting-backend nvidia --gpu-output
```

Usar somente uma janela do painel. O endpoint runtime/alpha-output.json é publicado depois de abrir a porta de recepção, com transporte, canvas, PID, SID e época. Não contém pixels, credenciais do iPhone ou handles de textura. O módulo próprio integrations/obs/smb-camera.lua escolhe o protocolo correspondente ao endpoint. Todos os arquivos Lua desse diretório precisam acompanhar o módulo.

No painel, Saída para OBS mostra o estado real e oferece o acesso à pasta do módulo. O usuário pode adicionar smb-camera.lua em Ferramentas > Scripts no OBS e criar a fonte SMB Camera. Essa configuração não é aplicada automaticamente pelo desenvolvimento. O modo GPU inicial tem um leitor; reutilizar a mesma fonte por referência em outras cenas. A webcam Windows e aplicativos como WhatsApp continuam sendo outra integração.

Para manter a referência RAM, usar --alpha-output. Os modos GPU, alpha RAM e saída opaca são mutuamente exclusivos neste corte. Sem consumidor, não se cria a textura compartilhada nem se executa o passe de exportação. Ocultar/remover a fonte fecha o cliente e libera suas texturas; o produtor libera seu dispositivo de exportação após perder a demanda. Mudar formato ou reiniciar o stream cria outro recurso com outra época.

## Contrato de controle

| Mensagem | Tamanho | Campos principais |
| --- | --- | --- |
| Request | 24 bytes | UCSQ, versão2, formato4, width, height, operação |
| Reply | 32 bytes | UCSR, versão2, status, body_bytes, captured_tick_ms, publisher_epoch |
| Descritor GPU | 64 bytes | UCSG, ABI1, RGBA8, canvas, DXGI28, premultiplied, LUID, handle, frame_id, resource_epoch |

Resposta com recurso tem 96 bytes e nenhum payload de pixels. Operação0 pede recurso;1 informa GPU incompatível;2 informa falha do recurso. Operação desconhecida, limites inválidos e protocolo antigo são recusados. Resposta vazia tem somente32bytes. O frame_id conta publicações do produtor, não comprova sozinho quantas imagens novas chegaram ao consumidor.

O pipe aceita somente conexões locais, com ACL do usuário proprietário e SYSTEM. O receptor verifica PID real do servidor e proprietário do pipe, confere o SID também contra o usuário atual e valida época, tamanho, formato, flags e validade antes de abrir um handle. No contexto gráfico, confirma D3D11 antes de interpretar o objeto como COM e consulta o adapter LUID do próprio OBS. GPU diferente é recusada e o erro retorna ao painel. Não há fallback silencioso para uma rota mais cara.

O produtor desenha somente sob chave0 e publica1. O OBS adquire1 com prazo zero, copia para uma textura privada pela GPU e devolve0 antes de compor a cena. Busy é tratado como busy; abandono exige novo recurso. Operações de criação/destruição do produtor pertencem ao thread GL. Falha ao criar uma textura também libera o dispositivo parcialmente criado, sem deixar alocação órfã esperando o fim da sessão.

Descritores recebidos precisam ter idade de até250ms desde a chegada ao PC. A fonte pode conservar a última imagem casada por até1s entre chegadas; depois para de desenhar. O timestamp é conservador e pertence ao host, não mede a latência desde o sensor. Sincronização impede leituras rasgadas; cadência e latência final continuam exigindo medição.

## Provas desta entrega

A cadeia gerada H.264/TLS/D3D11VA/GL/cor/máscara/ponteGPU/fonteOBS passou em1920x1080, preservando alpha0/128/255, pausa e retomada. Também passaram troca para1080x1920 e retorno, ocultar/mostrar a fonte com liberação/reconexão e rejeição de LUID incorreto sem matar a captura. Testes de pixels comparam a saída compartilhada inteira à referência RGBA em16combinações de giro/espelho/canvas, sem readback no caminho do produtor.

Uma falha inicial revelou que funções Win32 possuem uma única assinatura FFI por estado Lua: os dois clientes precisavam compartilhar exatamente o tipo OVERLAPPED, independentemente do protocolo de frames. Corrigido sem casts entre tipos incompatíveis; testes reais de pipe carregam RAM e GPU no mesmo estado. Uma rodada RAM simultânea à suíte GPU excedeu o prazo de descoberta do harness; a repetição sequencial passou. Não usar essa rodada concorrente para afirmar desempenho.

Uma rodada combinada mostrou os dois canvases, mas não observou expiração da imagem no intervalo verificado. Os eventos gerados de pausa e giro antes usavam o relógio de inicialização da janela, sem garantir que o consumidor já estivesse conectado. O harness passou a usar uma barreira explícita de consumidor pronto antes de disparar esses eventos; a repetição comprovou as condições juntas. Os critérios de alpha, prazo e recuperação não foram afrouxados, e o código de expiração do produto não foi alterado para obter PASS.

```powershell
.venv/Scripts/python.exe tools/probe_obs_alpha.py --resolution 1080 --seconds 8 --generated-studio --gpu-studio
.venv/Scripts/python.exe tools/probe_obs_alpha.py --resolution 1080 --seconds 10 --generated-studio --gpu-studio --gpu-view-cycle
.venv/Scripts/python.exe tools/probe_obs_alpha.py --resolution 1080 --seconds 8 --generated-studio --gpu-studio --gpu-visibility-cycle
.venv/Scripts/python.exe tools/probe_obs_alpha.py --resolution 1080 --seconds 8 --generated-studio --gpu-studio --gpu-reject-adapter
```

Os ensaios usam bibliotecas oficiais existentes do OBS32.2.2 em processo descartável, sem abrir obs64.exe, perfis/cenas ou gravar áudio/vídeo pessoal. O verificador de câmera real aceita o endpoint RAM ou GPU e mantém somente contadores agregados. A rodada seguinte com o iPhone real por USB1080p30 passou na fonteOBS GPU, com conteúdo e transparência, formato correto e sem erros de callback. O emissor registrou zero readbacks de pixels nesse trecho. Contadores detalhados permanecem somente locais; estabilidade longa e jogo continuam pendentes.

## Limites

A ponte elimina readback e upload de pixels entre esses dois programas, mas o decoder atual e o preparo da máscara ainda possuem cópias. Não é zero-copy de todo o pipeline, nem homologação durante jogo. Apenas Windows x64/OBS32.2.2/RTX3060 foram exercitados nesta bancada. 60FPS do iPhone, 4K sustentado nessa saída, múltiplos leitores e estabilidade longa ainda não estão aprovados.

O código Python/Lua continua sendo uma referência executável de integração; não substitui a consolidação e homologação do motor distribuível. Nenhuma loja, compra, novo IPA, driver, certificado ou alteração de segurança foi necessária nesta fatia.

## Ensaio prolongado gerado em Windows

Com o Python do projeto e as dependências de diagnóstico, executar na raiz da fonte ou worktree. O primeiro comando verifica a recuperação oito vezes na mesma sessão. O segundo acrescenta três minutos de exportação contínua e 20 segundos com a fonte oculta.

```powershell
.venv/Scripts/python.exe tools/gpu_soak.py --cycles 8
.venv/Scripts/python.exe tools/gpu_soak.py --cycles 1 --steady-seconds 180
```

A entrada gerada percorre H.264, TLS local, decoder D3D11VA, compositor GL, máscara de teste e a fonte Lua no motor OBS 32.2.2. A textura compartilhada usa o canvas integral. Apenas a saída lida pelo verificador é reduzida a 160x90. A cada amostra o verificador compara uma linha com a anterior e acumula contadores. O observador Lua de bancada conta cópias GPU, IDs distintos dos descritores disponíveis no momento da cópia e mudanças de época. O ID do descritor é uma observação do canal de controle. A cadência visual vem da comparação das linhas geradas.

O supervisor inicia a árvore suspensa, associa um Job Object e aplica prazo de parede. A pasta impressa em output/gpu-soak-* contém o log do processo e o resultado. Nos subdiretórios, cycles.jsonl e steady.jsonl registram o progresso por ciclo ou janela, com memória privada, handles e tempo de CPU dos processos da bancada. O limite após aquecimento é de +128 MiB privados e +64 handles, comparados na mesma fase dos ciclos. O trecho contínuo exige pelo menos 120 mudanças com alpha 0/128/255 por janela de 10 segundos e zero linhas inteiramente transparentes. A fase oculta exige pelo menos 240 linhas transparentes por janela. Um resultado fora do limite permanece nos arquivos locais.

A opção `--pressure` acrescenta dez segundos com uma resposta atrasada em 180 ms e um descritor envelhecido em 300 ms. A entrega original apresentou quadros em branco nos dois casos. A revisão T40 revalida a idade no recebimento e permite desenhar somente a textura privada anterior em atrasos transitórios, até seu prazo original. Uma rejeição de identidade ou estrutura invalida essa textura. Na repetição com pressão e 180 s contínuos, as duas injeções tiveram zero amostras em branco e todas as 18 janelas passaram com movimento e alpha. A máscara do ensaio é gerada.
