# iPhone 0.9

O código Swift fica em `apps/ios`. A beta usa a câmera do iPhone para enviar H.264 ao painel Windows. O modo de referência testado é USB em 1080p30 no iPhone 11 Pro Max com iOS 18.3.1.

## macOS com Xcode

Abra `apps/ios/UniversalCamera.xcodeproj`, escolha o iPhone conectado e selecione sua equipe em **Signing & Capabilities**. Se o identificador padrão estiver associado a outra equipe, use um identificador de bundle disponível para sua conta. Compile e rode no aparelho. A assinatura pessoal com Apple Account gratuita é temporária. A Apple documenta a expiração de sete dias dos perfis de uma Personal Team. [Apple Developer](https://developer.apple.com/help/account/basics/about-your-developer-account/)

## Windows com instalação pessoal

O IPA de build requer assinatura e provisionamento pessoal antes de ser instalado. No aparelho de referência, usamos o AltServer e o recurso **Sideload .ipa…**, acessado ao segurar Shift ao clicar no ícone do AltServer. Use a versão oficial e siga as orientações do fornecedor. Digite suas credenciais só na ferramenta de assinatura que você escolheu. A disponibilidade dessa rota depende da política de confiança do Windows e dos componentes do AltServer. Em caso de bloqueio, use uma máquina que aceite o instalador ou a rota Xcode. [Instalação oficial do AltServer para Windows](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows) · [Notas do AltServer](https://faq.altstore.io/release-notes/altserver)

## Windows passo a passo

1. Baixe e instale o AltServer e os pré-requisitos indicados pelo fornecedor. Conecte o iPhone por um cabo de dados, desbloqueie o aparelho e responda a **Confiar neste computador**, se o iOS perguntar.
2. Abra o AltServer. Na bandeja do Windows, pressione **Shift** enquanto clica no ícone. Escolha **Sideload .ipa…** e o iPhone conectado.
3. Selecione o IPA do SMB Camera. Faça a autenticação diretamente na ferramenta. Aguarde a notificação de instalação.
4. Abra **SMB Camera** no iPhone. Se o sistema pedir confiança de desenvolvedor ou modo de desenvolvedor, siga as telas oficiais para sua versão do iOS.
5. No PC, abra o SMB Camera e gere o QR de pareamento. Leia-o no app do iPhone. Escolha USB, 1080p30 e inicie a câmera.

Consulte o [tutorial oficial de instalação no Windows](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows) para as telas do AltServer. Use um exemplo no guia e o seu QR apenas durante o pareamento. O QR contém dados de acesso à câmera local.

## Primeiro uso

Pareie com o QR do painel e conecte um cabo USB de dados. Selecione USB e 1080p30. No iPhone, habilite **Permitir microfone ao gravar no PC** se quiser áudio no MOV. O microfone é solicitado quando a gravação com essa opção começa. A chave e o perfil de assinatura Apple ficam sob controle de quem instala.
