# SMB Camera Beta para Windows

## Primeira abertura

1. Em Windows 11 x64, extraia o ZIP em uma pasta local gravável. Instale Python 3.11 x64 com o launcher `py` e Git for Windows com OpenSSL. O modo de prévia requer OpenGL 3.3.
2. Abra **Preparar.cmd**. Ele cria um ambiente Python dentro dessa pasta e baixa as dependências verificadas de PyPI e SDL. Leia o resultado antes de abrir a câmera.
3. Abra **Abrir SMB Camera.cmd**. Deixe a janela do console até fechar o painel. Se o Windows pedir acesso de rede, permita a rede privada somente quando for a sua.
4. Instale o app no seu iPhone pela rota descrita em [iPhone](INSTALL-IOS.md). Pareie pelo QR no PC. Conecte o cabo de dados e, no iPhone, selecione USB e 1080p30.

Pré-requisitos oficiais. [Python para Windows](https://www.python.org/downloads/windows/) · [Git for Windows](https://gitforwindows.org/)

## OBS e gravação

No OBS x64, abra **Ferramentas → Scripts** e adicione `integrations/obs/smb-camera.lua` de dentro desta pasta. Na cena, crie uma fonte **SMB Camera**. Caso o OBS peça o arquivo de conexão, use `runtime/alpha-output.json` desta mesma pasta. O launcher abre em modo de compatibilidade via memória. Para experimentar o compartilhamento de textura com app e OBS na mesma GPU, execute `"Abrir SMB Camera.cmd" gpu` no Prompt de Comando. Para diagnóstico de decodificação, `"Abrir SMB Camera.cmd" ram cpu` seleciona CPU.

O recorte NVIDIA exige a dependência opcional descrita em [Recorte NVIDIA](NVIDIA-BETA.md). Para gravar o original antes dos efeitos, escolha **Gravar original**. Para incluir voz, habilite o microfone ao iniciar a câmera no iPhone e marque **Microfone do iPhone** no PC antes de gravar. Antes de sair, finalize a gravação.

## Atualizar ou remover

Feche o painel e remova a fonte e o script de teste do OBS. Para atualizar, extraia a nova versão em outra pasta, rode a preparação e aponte o script do OBS para a nova pasta. Se quiser preservar o pareamento, copie `runtime/identity` do pacote antigo com o app fechado. Essa pasta contém a chave do pareamento e deve ficar no seu PC. Se quiser preservar os ajustes, copie também `runtime/studio-settings.json`. As gravações ficam na pasta escolhida no momento de gravar. Preserve os arquivos e a identidade que precisar antes de remover a pasta antiga.

[Privacidade](PRIVACY.md) · [Componentes de terceiros](../THIRD-PARTY.md)
