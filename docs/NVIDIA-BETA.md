# Recorte NVIDIA opcional

A configuração de referência do recorte usa GeForce RTX 3060 Laptop e runtime Video Effects SDK 0.7.6 para Ampere. As DLLs e modelos do fornecedor ficam na instalação local. A beta do painel pode funcionar no modo **Original** com a gravação e o OBS sem o recorte.

1. Obtenha o pacote **Video Effects 0.7.6 para RTX 30** no [Download Center da NVIDIA](https://www.nvidia.com/en-us/geforce/broadcasting/broadcast-sdk/resources/) e consulte os termos do pacote.
2. Com o painel fechado, organize as DLLs e os modelos do pacote em `runtime/nvidia-vfx-0.7.6/`. As subpastas relativas e hashes esperados estão em [NVIDIA-VFX.lock.json](NVIDIA-VFX.lock.json). O painel verifica esses arquivos ao habilitar o recorte.
3. Abra o SMB Camera e escolha **Transparente** ou um fundo no painel. Se o runtime não estiver disponível, volte a **Original**.

Drivers, OBS e bibliotecas NVIDIA são administrados pelos seus fornecedores. O recorte foi validado na RTX 3060 Laptop. Outros modelos de GPU precisam de teste antes de serem anunciados como suportados.
