# Privacidade

A câmera do iPhone transmite ao PC pareado por TLS. O QR contém o token e a impressão digital do certificado da sessão local. Mostre o QR apenas para quem deve controlar o envio. No Windows, a identidade fica em `runtime/identity`, dentro da pasta do painel. Mantenha essa pasta sob controle da sua conta. No iPhone, o pareamento fica no Keychain.

A câmera é ativada por você no iPhone. O microfone do telefone é solicitado apenas quando você habilita o microfone no iPhone e inicia uma gravação no PC com a opção correspondente. O sistema controla as permissões. Para interromper a transmissão, use **Parar câmera**. Sair do app no iPhone também encerra a captura.

O painel salva mídia quando você inicia **Gravar original**. O MOV fica na pasta escolhida por você. Em caso de falha depois de começar a escrever, pode ficar um arquivo `.partial.mov` no mesmo local. A fonte OBS recebe a composição local por um canal de comunicação do Windows. A transmissão e a gravação próprias do OBS são controladas no OBS.

As preferências ficam em `runtime/studio-settings.json`. Relatórios locais de sessão trazem dados técnicos, a exemplo de dimensões, contadores de quadro e tempos de processamento. Confira o conteúdo antes de compartilhar um log ou perfil. O app funciona sem conta do SMB Camera e não envia telemetria à SIMBAproduz. A preparação do Windows consulta os fornecedores das dependências. A assinatura pessoal do iOS segue o fluxo Apple ou da ferramenta escolhida pelo usuário.
