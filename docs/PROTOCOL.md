# UCS1, referência independente v0.1

Estado: implementado em Python, emissor Swift escrito mas não compilado. Não é compatível com protocolos dos repositórios estudados. Futuras extensões exigem negociação e vetores comuns.

TCP/TLS >=1.2. Telefone cliente conecta ao PC:49200 em Wi-Fi. Desktop aceita um aparelho por vez nesta bancada. Pin SHA-256 de certificado DER verifica o servidor; token aleatório de 256 bits autoriza o cliente dentro de TLS. Transferência inicial manual fora da rede. Sem TOFU silencioso ou aceitação de qualquer certificado. Material fica em `runtime/identity`; rotação manual cria diretório novo, revoga o anterior e exige novo pareamento. Falta armazenamento seguro do SO/Keychain e UX de QR para produto. Token nunca vai a logs.

Header de 32 bytes, big-endian:

| Offset | Bytes | Campo |
| --- | --- | --- |
| 0 | 4 | ASCII UCS1 |
| 4 | 1 | versão 1 |
| 5 | 1 | tipo |
| 6 | 2 | flags: bit0 IDR em VIDEO; demais zero |
| 8 | 4 | tamanho do payload |
| 12 | 8 | sequência de captura, crescente, independente por sessão |
| 20 | 8 | PTS em microssegundos no relógio monotônico de origem |
| 28 | 4 | reservado zero |

Tipos: 1 HELLO JSON; 2 ACCEPT JSON; 3 VIDEO com um access unit H.264 Annex B; 4 PING; 5 PONG; 6 STOP. Máximo 4 MiB por access unit, 64 KiB por controle. São limites de alocação do protótipo, não promessa de suporte a toda resolução. Unknown magic/version/type/flags/reserved fecha a conexão. Truncamento e timeout fecham sem reaproveitar parser. Sem recuperar dados privados de sessão anterior.

HELLO contém token, codec=h264, width, height, fps inteiro, pixel_format=yuv420p, color=bt709-sdr. ACCEPT devolve versão e stream aceito. Receptor valida números/pares e formato; não há contraproposta automática. Primeiro VIDEO precisa IDR e SPS/PPS; SPS/PPS repetidos são permitidos. Sem B-frames nesta revisão. PTS e seq devem aumentar. START implícito após ACCEPT; STOP encerra. Cliente Swift exige clique novo após falha; reconexão automática do produto ainda pendente.

O emissor Swift limita a três frames entre encoder/envio e descarta antes do encoder quando cheio. Não descartar P-frames já codificados sem abandonar GOP e pedir IDR. O receptor tem fila de oito access units, máximo teórico 32 MiB de payload mais buffers do sistema/decoder. Saturação interrompe a sessão. **Não é um limite de RAM do processo nem garantia de baixa latência.**

Métricas: seq gaps são quadros omitidos na origem/fluxo, não perda de pacotes TCP; received_frames conta access units aceitos, decoded_frames vem do decoder, rendered_frames ainda não existe. source_fps deriva dos PTS, receive_fps dos tempos locais de chegada. PING/PONG mede ida e volta com o relógio do emissor; não rotular como atraso câmera-tela. Sincronização de relógios com incerteza, captura->encode->decode->present e A/V serão adicionadas antes do aceite real. No primeiro teste físico, usar cronômetro/LED filmado junto da tela.

## Extensão de controles planejada, não implementada

Antes de expor controles no PC: negociar versão que suporte CAPS, SET_CONTROL e CONTROL_RESULT. Cada comando terá request_id, session_id e capability_revision. Celular responde applied/rejected, valor real, limites atuais e erro específico. Descartar respostas de sessão/revisão antiga. Não repetir ações não idempotentes após reconexão.

CAPS por câmera: ID estável, orientação, lente física/virtual, formatos e intervalos FPS, subtipos NV12/P010, HDR/cores, encoder/codec, min/max zoom, foco auto/manual, ISO, exposição em segundos, WB/temperatura/tint, estabilização. Limites podem mudar ao trocar formato ou lente. Não inventar suporte a partir de rótulo comercial.

Troca de lente: validar -> pausar encoder -> selecionar entrada/formato -> confirmar configuração -> novo config/SPS/PPS/IDR -> continuar; mostrar interrupção medida. Zoom/foco/exposição/WB: lockForConfiguration/Camera2 controls, clamp explícito e confirmação. Pan/crop/rotação/espelho são transformações distintas e devem declarar onde são aplicadas. Próxima extensão vem com testes de valores inválidos, unsupported, concorrência, revision stale, disconnect e retorno do valor real.
