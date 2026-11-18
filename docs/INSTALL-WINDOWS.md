# SMB Camera Beta para Windows

## Instalação gráfica

Abra o instalador SMB Camera Beta, escolha uma pasta local vazia e clique em **Instalar SMB Camera**. Ele verifica Python 3.11 x64, launcher py e OpenSSL, prepara as dependências e oferece **Abrir SMB Camera**, **Configurar OBS** e **Guia do iPhone**. Se um pré-requisito estiver ausente, a tela oferece os links oficiais.

## Alternativa portátil por ZIP

1. Em Windows 11 x64, extraia o ZIP em uma pasta local gravável. Instale Python 3.11 x64 com o launcher `py` e Git for Windows com OpenSSL. O modo de prévia requer OpenGL 3.3.
2. Abra **Preparar.cmd**. Ele cria um ambiente Python dentro dessa pasta e baixa as dependências verificadas de PyPI e SDL. Leia o resultado antes de abrir a câmera.
3. Abra **Abrir SMB Camera.cmd**. Deixe a janela do console até fechar o painel. Se o Windows pedir acesso de rede, permita a rede privada somente quando for a sua.
4. Instale o app no seu iPhone pela rota descrita em [iPhone](INSTALL-IOS.md). Pareie pelo QR no PC. Conecte o cabo de dados e, no iPhone, selecione USB e 1080p30.

Pré-requisitos oficiais. [Python para Windows](https://www.python.org/downloads/windows/) · [Git for Windows](https://gitforwindows.org/)

## OBS e gravação

1. Na pasta extraída, abra **Configurar OBS.cmd**. O assistente mostra as instalações disponíveis e onde cada uma guarda a configuração. Se a cópia portátil estiver em outro local, escolha **Localizar obs64.exe**. Selecione e abra a instalação em que deseja usar a fonte.
2. No OBS x64, abra **Ferramentas → Scripts**, clique em **+** e cole o caminho obtido no botão **Copiar caminho do script**. Mantenha os quatro arquivos Lua juntos na pasta do SMB Camera.
3. Em **Fontes → +**, escolha **SMB Camera**. Caso a fonte peça o arquivo de conexão, use **Copiar caminho da conexão** com o SMB Camera aberto. O assistente apresenta as instruções sem alterar suas coleções de cenas. [Guias do OBS](https://docs.obsproject.com/scripting)

O launcher abre em modo de compatibilidade via memória. Para experimentar o compartilhamento de textura com app e OBS na mesma GPU, execute `"Abrir SMB Camera.cmd" gpu` no Prompt de Comando. Para diagnóstico de decodificação, `"Abrir SMB Camera.cmd" ram cpu` seleciona CPU.

O recorte NVIDIA exige a dependência opcional descrita em [Recorte NVIDIA](NVIDIA-BETA.md). Para gravar o original antes dos efeitos, escolha **Gravar original**. Para incluir voz, habilite o microfone ao iniciar a câmera no iPhone e marque **Microfone do iPhone** no PC antes de gravar. Antes de sair, finalize a gravação.

## Atualizar ou remover

Feche o painel e remova a fonte e o script de teste do OBS. Para atualizar, extraia a nova versão em outra pasta, rode a preparação e aponte o script do OBS para a nova pasta. Se quiser preservar o pareamento, copie `runtime/identity` do pacote antigo com o app fechado. Essa pasta contém a chave do pareamento e deve ficar no seu PC. Se quiser preservar os ajustes, copie também `runtime/studio-settings.json`. As gravações ficam na pasta escolhida no momento de gravar. Preserve os arquivos e a identidade que precisar antes de remover a pasta antiga.

[Privacidade](PRIVACY.md) · [Componentes de terceiros](../THIRD-PARTY.md)
