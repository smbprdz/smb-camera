# SMB Camera: fonte OBS autoral, experimental

Os quatro arquivos Lua deste diretorio implementam nossa fonte OBS e nosso receptor de frames. Nao usam Spout, VCam, pyvirtualcam ou um driver de webcam. Requerem OBS Windows x64 com LuaJIT; a prova integrada usou OBS32.2.2. O host OBS e suas APIs continuam dependencias da integracao. Nenhum binario do OBS acompanha este modulo.

O modo de compatibilidade copia RGBA8 premultiplicado da memória para uma textura OBS. A versão0.16 também pode receber uma texturaGPU pelo nosso broker, com identidade e sincronização verificadas. Ambos preservam transparência e evitam recodificar vídeo nesse trecho; o pipeline inteiro ainda não é zero-copy. O renderizador no app faz cor, recorte e geometria. [Contrato GPU e limites](../../docs/GPU-OUTPUT.md).

## Ensaio manual futuro

Esta receita altera a configuracao de scripts/fontes do OBS. Ela nao foi aplicada na instalacao do dono nesta entrega. Primeiro encerrar uma instancia antiga do painel, preservando seu perfil. Na raiz do aplicativo:

```powershell
.venv/Scripts/pythonw.exe -m ucs.desktop --decoder d3d11va --renderer gl --matting-backend nvidia --alpha-output
```

Ativar a camera no iPhone e escolher Transparente no painel. O endpoint runtime/alpha-output.json e publico local, sem credenciais, e so e publicado depois de o receptor conseguir abrir sua porta. O modo de laboratorio alpha e exclusivo da saida opaca --frame-output. Nao registra webcam Windows.

Para testar a ponte GPU integrada, substituir --alpha-output por --gpu-output na receita. Copiar também gpu_transport.lua e gpu_graphics.lua junto dos outros dois arquivos. O módulo identifica o transporte pelo endpoint. A fonte precisa estar na mesma GPU do app e este corte admite um leitor; pode ser reutilizada por referência entre cenas. A aba Saída para OBS informa estado e erros. O desenvolvimento não instala o módulo automaticamente na configuração do usuário.

No OBS, adicionar somente smb-camera.lua em Ferramentas > Scripts. Manter alpha_transport.lua ao lado dele. Adicionar a fonte SMB Camera a uma cena de teste. Quando o modulo permanece neste diretorio do app, a conexao padrao aponta para o endpoint acima. Se os arquivos forem colocados em outro diretorio, selecionar esse arquivo uma vez em Conexao com SMB Camera. O caminho e estavel entre reinicios; PID/epoch e formato sao revalidados. Nao digitar token ou fingerprint do pareamento do telefone no OBS.

Original e Imagem sao opacos; Transparente conserva alpha. Pacotes recebidos exigem idade de ate250ms. Entre chegadas, a fonte conserva a ultima imagem casada por ate1s desde a chegada aoPC, evitando piscar com uma entrada perto de3FPS. Depois disso, deixa de desenhar. Isso nao mede a idade total desde a captura no telefone. Ao ocultar a fonte, o receptor fecha sua conexao e para de pedir frames; a fonte libera as texturas ao ser ocultada ou removida. Remover a fonte e o script desfaz essa integracao, sem registrar COM/dispositivo ou alterar drivers.

Prova automatizada sem abrir OBSUI, perfis, cameras, audio ou gravacao:

```powershell
.venv/Scripts/python.exe tools/probe_obs_alpha.py --resolution 1080 --seconds 8
.venv/Scripts/python.exe tools/probe_obs_alpha.py --resolution 1080 --seconds 8 --generated-studio
```

O utilitario usa as bibliotecas oficiais ja instaladas em outro processo com contexto descartavel. A ABI do utilitario esta fixada emOBS32.2.2; nao aceitar outra versao silenciosamente. O teste publica apenas padroes gerados, verifica alpha/cor/queda/retomada e grava somente numeros. Isso nao homologa o iPhone, o OBS com jogo ou outras versoes.

Na revisão T40 da fonte GPU, um atraso transitório no pipe ou um descritor expirado permite reapresentar a última textura privada já copiada, apenas até o prazo original de um segundo. O receptor descarta o descritor expirado. Uma falha estrutural ou de identidade invalida o cache. O módulo de medição da bancada não integra os quatro arquivos do pacote.
