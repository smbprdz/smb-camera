# Recorte NVIDIA opcional

A configuração de referência do recorte usa GeForce RTX 3060 Laptop e runtime Video Effects SDK 0.7.6 para Ampere. As DLLs e modelos do fornecedor ficam na instalação local. A beta do painel pode funcionar no modo **Original** com a gravação e o OBS sem o recorte.

1. Obtenha o pacote **Video Effects 0.7.6 para RTX 30** no [Download Center da NVIDIA](https://www.nvidia.com/en-us/geforce/broadcasting/broadcast-sdk/resources/) e consulte os termos do pacote.
2. Em **Fundo e recorte**, clique em **Localizar runtime NVIDIA** e selecione a pasta que contém as DLLs e a subpasta `models`. O caminho fica salvo neste painel. Também é possível usar a pasta padrão `runtime/nvidia-vfx-0.7.6` dentro da instalação. As subpastas e hashes esperados estão em [NVIDIA-VFX.lock.json](NVIDIA-VFX.lock.json).
3. Selecione **Transparente** ou um fundo. O auxiliar verifica os hashes antes de carregar as DLLs. Se aparecer aviso de dependência ou arquivo alterado, escolha a pasta correta ou selecione **Original** para mostrar o vídeo completo.

Drivers, OBS e bibliotecas NVIDIA são administrados pelos seus fornecedores. O recorte foi validado na RTX 3060 Laptop. Outros modelos de GPU precisam de teste antes de serem anunciados como suportados.
