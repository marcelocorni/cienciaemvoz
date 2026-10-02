# Ciência em Voz

O repositório também contém o [portal de leitura em .NET/Blazor](portal/README.md), na pasta `portal/`, para ler PDFs e ouvir os MP3 em sequência. Para executar: `dotnet run --project portal` e abra `http://localhost:5080`.

Aplicação local para transformar seleções de PDFs científicos em arquivos MP3. Identifica capítulos, seções e subseções, permite revisar a narração e oferece downloads individuais ou um pacote ZIP.

## Como funciona

- **PyMuPDF:** leitura rápida do PDF e identificação inicial dos títulos.
- **Docling (opcional):** OCR, reconstrução da ordem de leitura, tabelas e reconhecimento de fórmulas.
- **Ollama (opcional):** preparação de fórmulas e símbolos por extenso usando um modelo de texto local.
- **Kokoro:** síntese de voz local, com escolha de voz, velocidade, pausas e prévia.
- **FFmpeg:** conversão para MP3, união dos trechos e ajustes de pitch e volume.

É possível gerar áudio sem Ollama e sem Docling quando o PDF já contém texto extraível: use a preparação manual e escreva as fórmulas por extenso. O Kokoro é necessário para gerar voz. Nenhuma chave de serviço pago é necessária no fluxo local.

## Requisitos

- Python **3.12**, recomendado para as dependências deste projeto.
- Internet para instalar pacotes e baixar modelos na primeira configuração.
- Espaço para os modelos, PDFs e áudios. O Qwen3 8B ocupa aproximadamente 5,2 GB em disco; Kokoro e vozes, aproximadamente 354 MB. Docling também baixa modelos e pode ocupar vários GB, especialmente em Docker.
- Memória disponível para os modelos: 16 GB de RAM é um ponto de partida para experimentar com Qwen3 8B e documentos menores, sem garantia para todos os PDFs. Executar OCR, reconhecimento de fórmulas e modelos de linguagem simultaneamente aumenta o consumo.
- GPU é opcional; CPU funciona, mas pode levar mais tempo.
- Docker Desktop com containers Linux no Windows, ou Docker Engine no Linux, **somente se optar pelos serviços em Docker**.

Instale Python em [python.org](https://www.python.org/downloads/). Para Docker, consulte a [instalação oficial](https://docs.docker.com/get-started/get-docker/).

## 1. Instalar a aplicação

Baixe ou clone este repositório e abra um terminal na pasta do projeto. Os comandos abaixo pressupõem que o diretório se chama `ciencia-em-voz`.

### Windows / PowerShell

```powershell
cd ciencia-em-voz
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
```

### Linux / macOS

```bash
cd ciencia-em-voz
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-lock.txt
cp .env.example .env
```

Os comandos usam o Python do ambiente diretamente; não é necessário ativá-lo. Se já existir `.env`, preserve sua configuração em vez de copiar por cima.

`requirements-lock.txt` fixa as versões da aplicação. Docling possui dependências opcionais separadas. Em plataformas sem binários compatíveis, pode ser necessário instalar FFmpeg/eSpeak ou ajustar as dependências conforme a documentação dessas bibliotecas.

## 2. Instalar Ollama e baixar o modelo de texto

Escolha **uma** das alternativas abaixo. Não execute duas instâncias na mesma porta 11434.

### Alternativa A: instalação nativa

No Windows ou macOS, baixe e instale o [Ollama](https://ollama.com/download). No Linux, siga as [instruções oficiais](https://docs.ollama.com/linux).

Com o serviço em execução:

```bash
ollama pull qwen3:8b
ollama list
```

Se o serviço não estiver iniciado pela instalação, execute `ollama serve` em outro terminal. O aplicativo usa, por padrão, `http://localhost:11434`.

### Alternativa B: Docker

O nome `ollama` abaixo é apenas um exemplo genérico. Pode ser substituído pelo nome escolhido para sua instalação.

```bash
docker pull ollama/ollama:latest
docker run -d --name ollama --restart unless-stopped -p 127.0.0.1:11434:11434 -v ollama-data:/root/.ollama ollama/ollama:latest
docker exec -it ollama ollama pull qwen3:8b
docker exec ollama ollama list
```

A configuração acima usa CPU. Para uma GPU NVIDIA compatível, use `--gpus all` no comando `docker run`, com os drivers e a integração de GPU do Docker configurados. Consulte o [guia de Docker do Ollama](https://docs.ollama.com/docker).

O volume `ollama-data` preserva os modelos ao recriar o container. Se já usa Ollama em Docker, basta executar o `pull` no seu container existente, sem criar outro.

### Qual modelo baixar?

O padrão é **`qwen3:8b`**, utilizado para converter fórmulas e símbolos em uma narração revisável. O projeto desativa seu modo de raciocínio na solicitação para obter a resposta diretamente. O tamanho informado pode variar conforme a versão/distribuição do modelo.

É possível selecionar outro modelo de texto compatível com `/api/chat`, mas sua qualidade deve ser avaliada com o documento. Modelos de embeddings não servem para preparar a narração.

**Kokoro e os modelos do Docling não são modelos do Ollama.** Eles têm downloads próprios, descritos a seguir.

### Testar a conexão

Na barra lateral, use **Verificar conexão e modelos**. Ou, no PowerShell:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

O modelo configurado em `OLLAMA_MODEL` deve aparecer na lista.

## 3. Instalar Docling e baixar seus modelos

Docling é recomendado para documentos digitalizados, várias colunas e fórmulas. Escolha uma alternativa.

### Alternativa A: Docling no Python da aplicação

No Windows:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-docling.txt
.venv\Scripts\docling-tools.exe models download
```

No Linux/macOS:

```bash
.venv/bin/python -m pip install -r requirements-docling.txt
.venv/bin/docling-tools models download
```

Deixe `DOCLING_CONTAINER=` vazio no `.env`. O download padrão inclui os modelos usados para layout, tabelas, OCR e código/fórmulas; se algum componente não estiver em cache, ele poderá ser baixado no primeiro uso. Consulte o [guia de downloads e uso offline do Docling](https://docling-project.github.io/docling/usage/advanced_options/).

A instalação de Docling pode atualizar dependências compartilhadas, como PyTorch. Para manter o ambiente da aplicação separado dessas dependências, use a alternativa Docker.

### Alternativa B: Docling em Docker

Exemplo genérico com a imagem CPU oficial:

```bash
docker pull quay.io/docling-project/docling-serve-cpu:latest
docker run -d --name docling --restart unless-stopped quay.io/docling-project/docling-serve-cpu:latest
docker exec docling docling-tools models download
docker exec docling python -c "import docling; print('Docling disponível')"
```

Configure no `.env`:

```dotenv
DOCLING_CONTAINER=docling
```

O programa executa seu conversor com `docker exec` dentro do container indicado. **Não usa a API HTTP do Docling Serve**, portanto não é necessário publicar a porta 5001. O terminal que executa o Streamlit precisa ter acesso ao Docker, e o container deve estar em execução.

O nome `docling` pode ser substituído pelo nome escolhido na instalação. Se já existir um container com o pacote Docling e Python disponíveis, informe seu nome no `.env` ou na barra lateral.

Os modelos/cache permanecem no container enquanto ele existir; ao removê-lo, downloads adicionais podem precisar ser refeitos. A imagem CPU é indicada para começar; variantes CUDA exigem GPU e configuração compatíveis. Para reproduzir uma instalação, prefira fixar uma versão da imagem já validada em vez de depender continuamente de `latest`. Veja as [imagens oficiais do Docling Serve](https://github.com/docling-project/docling-serve).

## 4. Baixar Kokoro e vozes

No Windows:

```powershell
.venv\Scripts\python.exe configurar_local.py --baixar-voz --verificar-ollama
```

No Linux/macOS:

```bash
.venv/bin/python configurar_local.py --baixar-voz --verificar-ollama
```

Esse comando baixa os arquivos oficiais:

- `models/kokoro-v1.0.onnx`: modelo de síntese.
- `models/voices-v1.0.bin`: vozes disponíveis.

Também é possível clicar em **Baixar arquivos de voz Kokoro** na aplicação. Não existe comando `ollama pull kokoro` neste projeto. O downloader reutiliza os arquivos já baixados.

O pacote `imageio-ffmpeg` fornece FFmpeg nas plataformas suportadas; `espeakng-loader`, usado pelo Kokoro ONNX, fornece a biblioteca de pronúncia. Normalmente não é necessário instalar esses componentes manualmente.

## 5. Configuração

Exemplo de `.env` para Ollama local e Docling instalado no Python:

```dotenv
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
DOCLING_CONTAINER=
KOKORO_MODELS_DIR=models
AUDIO_OUTPUT_DIR=audios
```

Para o exemplo Docker do Docling, altere apenas `DOCLING_CONTAINER=docling`. Os nomes nos exemplos são genéricos e não precisam coincidir com outros projetos do computador.

| Variável | Uso |
|---|---|
| `OLLAMA_URL` | Endereço do servidor Ollama. |
| `OLLAMA_MODEL` | Nome exato do modelo de texto instalado. |
| `DOCLING_CONTAINER` | Nome do container; vazio usa o Python local. |
| `KOKORO_MODELS_DIR` | Pasta do modelo e das vozes Kokoro. |
| `AUDIO_OUTPUT_DIR` | Pasta de saída dos áudios e transcrições. |

Pastas relativas são resolvidas a partir da pasta da aplicação. `.env`, modelos e áudios são ignorados pelo Git.

Se o Streamlit também rodar em Docker, `localhost` aponta para seu próprio container. Use `http://host.docker.internal:11434` no Docker Desktop ou o nome do serviço Ollama em uma rede compartilhada. O modo Docling via `docker exec` requer acesso ao Docker; alternativamente instale Docling no Python do container da aplicação. Este guia executa o Streamlit no computador anfitrião.

## 6. Executar

Windows:

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Linux/macOS:

```bash
.venv/bin/python -m streamlit run app.py
```

Abra [http://localhost:8501](http://localhost:8501). No Windows, `iniciar.bat` também inicia a aplicação e instala as dependências principais. Para Docling nativo, prefira o comando do ambiente `.venv` acima: quando `uv` está disponível, o iniciador usa um ambiente separado que não inclui automaticamente as dependências opcionais.

Para encerrar, pressione **Ctrl+C** no terminal do Streamlit. Isso não encerra Ollama ou Docling em outros processos/containers.

## Uso

1. Envie um PDF e clique em **Identificar estrutura**.
2. Para OCR, múltiplas colunas ou equações, use **Reconstruir texto e fórmulas com Docling** no painel de qualidade.
3. Confira os títulos e selecione capítulos/seções, ou crie intervalos por páginas. Os botões **Marcar todos** e **Desmarcar todos** controlam a seleção em lote. Selecionar um capítulo inclui suas subseções; seleções contidas em outra não duplicam áudio.
4. Informe pronúncias no formato `termo = leitura`, uma por linha.
5. Prepare com Ollama ou escolha **Texto local, com revisão manual**.
6. Revise as transcrições: cole um texto pronto no campo de narração ou abra **Importar uma transcrição TXT para esta seleção**, escolha o arquivo e clique em **Usar TXT nesta seleção**. O arquivo substitui somente o texto da seção correspondente. Escreva fórmulas por extenso quando necessário. Resolva marcadores de conteúdo ilegível ou a conferir antes de gerar áudio.
7. Escolha idioma, voz e ajustes. Use **Gerar prévia da voz** para ouvir até 500 caracteres sem precisar enviar um PDF.
8. Marque que revisou a narração e gere os MP3. Ouça e baixe cada seleção ou o ZIP completo.

O glossário ignora maiúsculas/minúsculas e prioriza termos mais longos. Por isso, uma entrada `IF` também alcança a palavra inglesa “if”: utilize glossários adequados ao idioma do trecho. A voz não traduz o conteúdo.

## Reutilizar transcrições ou começar por textos prontos

Escolha **Textos e arquivos TXT** em **Origem do conteúdo**. Esse caminho não exige PDF, Docling ou Ollama:

1. Abra **Colar um texto**, informe título e transcrição e clique em **Adicionar texto**; repita para outros áudios.
2. Ou selecione vários arquivos em **Importar arquivos TXT** e clique em **Adicionar arquivos TXT**. Cada arquivo vira um item; seu nome, sem a extensão, vira o título inicial.
3. Use **Marcar todos**, **Desmarcar todos** ou **Incluir no áudio** para escolher os itens da geração.
4. Edite os títulos e textos, ou remova um item. Se necessário, use **Aplicar pronúncias do glossário** em cada texto. O glossário não é aplicado automaticamente às transcrições prontas.
5. Confirme a revisão e gere os MP3. Cada item selecionado terá um áudio e uma transcrição no pacote.

Arquivos TXT podem ter até **5 MB cada** e devem estar em UTF-8 (com ou sem BOM), UTF-16 com BOM ou Windows-1252. A importação preserva os parágrafos e as palavras, sem resumir ou reinterpretar o conteúdo. Arquivos vazios/binários são recusados; se um arquivo da importação em lote for inválido, nenhum dos itens desse lote é adicionado.

Para recuperar sete transcrições anteriormente preparadas, importe os sete TXT nesse modo. Não é necessário preparar novamente pelo Ollama. Os textos podem ser ajustados antes da geração, e não têm páginas de PDF associadas no manifesto.

As listas de textos e a preparação do PDF ficam separadas na sessão. Alternar a origem preserva os textos editados, mas fechar/recarregar a sessão pode perder esses dados: baixe as transcrições para guardá-las. Os pacotes de áudio já publicados permanecem na pasta de saída.

## Importar e salvar pronúncias

Na barra lateral, abra **Importar configuração de pronúncias**, selecione um arquivo `.txt` ou `.conf` e clique em **Importar pronúncias**. O arquivo usa o mesmo formato do campo:

```text
# Pronúncias para leitura científica
Ethereum = Etéreum
ROC-AUC = róqui áuqui
Autoencoder = auto encôuder
```

Escolha **Mesclar com as atuais** para preservar os demais termos, ou **Substituir todas** para carregar somente a configuração do arquivo. Na mesclagem, os termos são comparados sem distinguir maiúsculas/minúsculas e a pronúncia importada prevalece. Linhas vazias e comentários iniciados com `#` são ignorados. A importação valida o arquivo inteiro antes de alterar o campo; se houver uma linha inválida, a configuração atual é preservada.

São aceitas as mesmas codificações dos arquivos de transcrição e até 5 MB. Depois da importação, as entradas continuam editáveis. Use **Baixar configuração de pronúncias** para exportar a lista válida em UTF-8 e reutilizá-la em outro documento ou sessão. No modo de textos prontos, clique em **Aplicar pronúncias do glossário** no texto desejado; a importação da configuração não substitui automaticamente transcrições revisadas.

## Ajustes da voz

O **Idioma da voz** e a **Voz Kokoro** na sidebar são os padrões da geração. Na revisão de cada texto ou seleção do PDF, use **Idioma deste áudio** para escolher um idioma específico, como inglês para o Abstract e português para os capítulos. **Voz deste áudio** oferece somente vozes compatíveis com o idioma escolhido.

Com **Usar padrão da sidebar**, o áudio acompanha as alterações do padrão. Se o idioma do áudio for diferente do padrão, a voz automática será a primeira disponível nesse idioma; também é possível escolher outra voz da lista. Essas escolhas são preservadas ao alternar entre PDF e textos durante a sessão e registradas individualmente no `manifesto.json`. Velocidade, altura, volume e pausas continuam seguindo os ajustes gerais. O idioma da voz não traduz o texto nem altera a preparação de fórmulas ou o glossário.

| Controle | Intervalo / comportamento |
|---|---|
| Velocidade | 0,5 a 2,0; padrão 1,0. |
| Altura da voz | -6 a +6 semitons; negativo torna mais grave e positivo, mais aguda. |
| Volume | -12 a +6 dB; padrão 0. Ganho positivo passa por um limitador. |
| Pausa entre frases | 0 a 2 segundos; padrão 0,25. |
| Pausa entre orações | 0 a 1 segundo; padrão 0,1. |
| Prévia | Usa o glossário e os mesmos ajustes da geração final. |

O pitch é aplicado **depois da síntese** pelo FFmpeg, preservando aproximadamente a duração. Usa `rubberband` quando disponível; nas demais instalações, compensa a mudança de duração com `asetrate`, `aresample` e `atempo`. Ajustes extremos podem gerar artefatos. A velocidade controla o Kokoro separadamente.

As pausas dependem da pontuação reconhecida pelo sintetizador. A divisão em trechos pode acrescentar intervalos. Os controles não garantem uma entonação específica em cada palavra. O projeto gera fala; canto e acompanhamento musical exigem um mecanismo próprio e não fazem parte deste fluxo.

## Arquivos gerados

Cada geração cria uma pasta própria em `audios/`, contendo:

- Um MP3 e uma transcrição TXT por seleção do PDF ou texto avulso.
- `manifesto.json`, com páginas físicas, hashes, voz, velocidade, ajustes de áudio e configuração da preparação.
- `LEIA-ME.txt`, com orientações de revisão.

O MP3 usa 128 kbps. Trechos de até 700 caracteres são sintetizados e unidos em um arquivo por seleção. A aplicação processa arquivos temporários antes de publicar a pasta final; uma falha remove somente a tentativa incompleta. Prévias são temporárias e não criam pacotes na pasta de saída. A limpeza de gerações concluídas é manual.

Quando qualquer ajuste de voz muda, o aplicativo informa que os arquivos exibidos pertencem à geração anterior. Gere novamente para incorporar os ajustes.

## Problemas comuns

| Problema | O que conferir |
|---|---|
| Ollama não conecta | Serviço ativo, endereço correto e porta 11434. |
| Modelo não instalado | Execute `ollama pull qwen3:8b` nativamente ou dentro do container usado; confira `OLLAMA_MODEL`. |
| Docling não converte | Instalação no Python correto ou container ativo, nome configurado, modelos e memória. |
| Primeira conversão demora | Modelos podem estar sendo baixados/carregados; documentos extensos exigem mais recursos. |
| Não é possível gerar MP3/prévia | Baixe os arquivos Kokoro, confira permissões e FFmpeg. |
| Voz ficou artificial | Reduza o pitch e a velocidade; compare com a prévia padrão. |
| Fórmula ou palavra incorreta | Confira o PDF original e corrija a transcrição/glossário antes de gerar. |

Os painéis de detalhes de erro ajudam a identificar falhas. Se o Docling exceder 30 minutos, divida o PDF em documentos menores.

## Limites e privacidade

- PDFs de até 50 MB e 500 páginas.
- Os modelos podem errar, omitir ou alterar conteúdo; a revisão científica é necessária.
- Com serviços locais e modelos instalados, os documentos não precisam ser enviados a APIs externas. Se configurar Ollama remoto, o texto selecionado será enviado a esse endereço.
- O download inicial de pacotes e modelos requer internet.
- Processamento síncrono: mantenha a sessão aberta durante a geração.
- A pasta de saída fica no computador que executa o Streamlit; visitantes baixam pelo navegador.
- A configuração padrão é local. Publicação para múltiplos usuários requer autenticação, isolamento e retenção de arquivos.

## Testes

Windows:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS:

```bash
.venv/bin/python -m pytest -q
```

Os testes cobrem extração/seleção, glossário, preparação local, protocolos dos serviços, exportação/ZIP, limpeza após falhas, ajustes de áudio, seleção em lote e importação de transcrições. Os testes dos serviços usam respostas simuladas; testes acústicos usam FFmpeg real, sem baixar modelos adicionais. Não constituem uma avaliação científica de precisão do OCR ou da narração.

## Referências

- [Instalação do Ollama](https://ollama.com/download)
- [Ollama em Docker](https://docs.ollama.com/docker)
- [Modelo Qwen3 8B](https://ollama.com/library/qwen3:8b)
- [Instalação do Docling](https://docling-project.github.io/docling/getting_started/installation/)
- [Downloads de modelos Docling](https://docling-project.github.io/docling/usage/advanced_options/)
- [Docling Serve e imagens Docker](https://github.com/docling-project/docling-serve)
- [Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx)
- [Vozes Kokoro](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
- [Filtros de áudio FFmpeg](https://ffmpeg.org/ffmpeg-filters.html)
