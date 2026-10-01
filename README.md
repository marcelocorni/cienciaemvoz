# Ciência em Voz — versão local

Aplicação Streamlit em português para selecionar capítulos, seções e subseções de PDFs científicos, preparar sua leitura e gerar MP3 individuais ou um pacote ZIP. **Sem chave de API paga.**

O fluxo usa:

1. **PyMuPDF** para identificação rápida de marcadores/títulos e visualização.
2. **Docling local** para OCR, ordem de leitura, tabelas e reconhecimento de fórmulas em LaTeX.
3. **Ollama** para converter o texto científico e as fórmulas em narração revisável.
4. **Kokoro ONNX** para sintetizar a voz localmente; FFmpeg para gerar e juntar os MP3.

## Seu ambiente atual

Foi verificado neste computador:

- Ollama acessível em `http://localhost:11434`.
- Container Ollama: `dissertacao-rag-ollama-1`.
- Modelo de texto já instalado: `gpt-oss:20b`.
- Container Docling existente: `dissertacao-rag-docling-1`.
- A aplicação foi configurada para aproveitar esse container Docling, sem alterar sua rede ou seus serviços.

## Adicionar o modelo recomendado ao Ollama

No PowerShell:

```powershell
docker exec -it dissertacao-rag-ollama-1 ollama pull qwen3:8b
docker exec -it dissertacao-rag-ollama-1 ollama list
```

O `qwen3:8b` é uma opção inicial mais compacta, com aproximadamente 5,2 GB de arquivos. A memória necessária durante o uso é maior que o tamanho do download e depende do contexto. O programa envia `think=false` para esse modelo e trabalha com pequenos trechos para limitar a expansão do texto.

O download é necessário apenas uma vez. Não há cobrança de API ao executar o modelo local. Para testar imediatamente sem outro download, informe **gpt-oss:20b** no campo **Modelo do Ollama**; a integração com ele foi testada de verdade. Nesse caso o programa usa `think="low"`, conforme o suporte desse modelo.

**O modelo do Ollama é de texto.** O OCR e a extração das fórmulas são feitos pelo Docling; a voz é feita pelo Kokoro. Não é necessário instalar Kokoro como modelo do Ollama.

## Testar a API do Ollama

```powershell
$pedido = @{
    model = "qwen3:8b"
    stream = $false
    think = $false
    messages = @(
        @{ role = "system"; content = "Escreva fórmulas em palavras para narração científica. Retorne somente a narração." }
        @{ role = "user"; content = "Leia em português: E = m c^2." }
    )
} | ConvertTo-Json -Depth 5

$resposta = Invoke-RestMethod `
    -Uri "http://localhost:11434/api/chat" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($pedido))

$resposta.message.content
```

Um resultado esperado é uma leitura equivalente a “E é igual a m vezes c ao quadrado”; a redação pode variar. A API local do Ollama não requer chave na configuração utilizada.

## Iniciar a aplicação

Extraia o ZIP e abra **iniciar.bat**. Tenha Python 3.11 ou superior, ou `uv`, instalado. O iniciador instala as dependências e abre a aplicação em [http://localhost:8501](http://localhost:8501).

Alternativa com `uv`, na pasta extraída:

```powershell
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements-lock.txt
.venv/Scripts/python.exe configurar_local.py --baixar-voz --verificar-ollama
.venv/Scripts/python.exe -m streamlit run app.py
```

Sem `uv`:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe configurar_local.py --baixar-voz --verificar-ollama
.venv\Scripts\python.exe -m streamlit run app.py
```

O modelo e as vozes Kokoro são baixados separadamente, aproximadamente 354 MB no total, em `models/`. Também é possível usar o botão **Baixar arquivos de voz Kokoro** na barra lateral. Depois do download, a síntese funciona localmente. Neste computador os arquivos já foram baixados e testados, mas o ZIP contém apenas código e instruções.

O pacote `kokoro-onnx` inclui carregamento de eSpeak; o FFmpeg é disponibilizado por `imageio-ffmpeg`. Não é necessária uma instalação manual desses programas nas plataformas com binários disponíveis.

## Configuração

Copie `.env.example` para `.env`, ou ajuste os campos da barra lateral:

```dotenv
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
DOCLING_CONTAINER=dissertacao-rag-docling-1
KOKORO_MODELS_DIR=models
AUDIO_OUTPUT_DIR=audios
```

O nome do container Docling deve existir no Docker da máquina que executa a aplicação. O programa invoca seu Python com `docker exec -i`, transmite apenas o PDF para esse processo e recebe a estrutura convertida. Não publica novas portas, não reinicia containers e não altera configurações existentes. O primeiro uso pode baixar modelos gratuitos do Docling para o cache do container.

Se preferir Docling no Python da própria aplicação, instale as dependências opcionais e deixe o campo **Container Docling** vazio:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-docling.txt
```

Essa opção instala dependências maiores, como PyTorch, e não é necessária no ambiente atual com Docling em Docker.

Se a aplicação também for executada dentro de Docker, `localhost` apontará para o container da aplicação. Nesse caso configure `OLLAMA_URL=http://host.docker.internal:11434` no Docker Desktop ou o endereço/nome do serviço Ollama na rede compartilhada. A execução por `docker exec` exige acesso ao Docker; alternativamente use Docling no Python do container da aplicação. O pacote fornecido usa execução no Windows host por padrão.

## Uso com textos científicos

1. Envie o PDF e clique em **Identificar estrutura**. A análise rápida é local e não usa Ollama.
2. Para PDFs digitalizados, com várias colunas ou equações, abra **Qualidade da extração e leitura visual** e clique em **Reconstruir texto e fórmulas com Docling**.
3. Confira a hierarquia. Marque os capítulos/subseções ou adicione uma seleção manual por páginas. Um capítulo inclui suas subseções; seleções contidas em outra seleção não duplicam áudio.
4. Informe pronúncias especiais, uma por linha: `ATP = a tê pê`.
5. Use **Leitura científica com Ollama** e clique em **Preparar textos da seleção**. O modelo recebe somente o texto selecionado, incluindo fórmulas reconhecidas pelo Docling.
6. Revise cada transcrição. Corrija fórmulas e termos; marcadores `[CONFERIR: ...]` e `[ilegível]` bloqueiam a geração até serem resolvidos.
7. Escolha uma voz/idioma Kokoro correspondente ao texto e marque que revisou a narração. O sintetizador não traduz documentos.
8. Gere os MP3. Ouça no aplicativo e baixe individualmente ou em ZIP.

O modelo de linguagem pode modificar ou omitir conteúdo mesmo com instruções de preservação. O reconhecimento de fórmulas depende da qualidade da página e da detecção do Docling. A revisão científica continua necessária. A opção manual permite preparar o texto sem Ollama, mas exige escrever as fórmulas por extenso.

## Arquivos gerados

Cada geração cria uma pasta própria em `audios/`, com um MP3 e uma transcrição TXT por seleção, `manifesto.json` e `LEIA-ME.txt`. O manifesto identifica voz, velocidade, modelo de preparação, backend local, páginas físicas e hashes das transcrições/PDF. O ZIP inclui esses arquivos.

Trechos de voz têm até 700 caracteres. O FFmpeg junta os trechos em um MP3 por seleção. Uma falha remove somente os arquivos incompletos dessa tentativa. Gerações anteriores permanecem. A pasta fica no computador que executa a aplicação; visitantes baixam os arquivos pelo navegador.

Os áudios são processados em uma pasta temporária do sistema. Só depois de todos ficarem prontos a aplicação cria a pasta final e copia os arquivos fechados, gravando o manifesto por último. Esse processo evita o erro de permissão do Windows ao renomear uma pasta observada pelo Streamlit. Falhas de geração agora exibem uma mensagem específica e um painel com detalhes para diagnóstico.

## Limites e privacidade

- Até 50 MB e 500 páginas. Divida documentos maiores para reduzir tempo e uso de memória.
- Com Ollama local, Docling local e Kokoro instalado, o processamento não precisa enviar documentos a APIs externas. A instalação inicial baixa pacotes e modelos pela internet.
- O endereço Ollama é configurável: se apontar para outro servidor, os trechos selecionados serão enviados a ele.
- Processamento síncrono; mantenha a sessão aberta até terminar. Não há fila nem retomada automática de tarefas.
- As transcrições e os áudios persistem na pasta de saída; a limpeza é manual.
- A versão padrão é local, vinculada a `127.0.0.1`. Publicação na internet exige autenticação, isolamento de usuários e política de retenção.

## Validação desta versão

**31 testes automatizados passaram**, cobrindo o fluxo da interface, seleção hierárquica, limites na mesma página, glossário, divisão de trechos sem cortar fórmulas em LaTeX, protocolo Ollama/Docling, recusa de respostas incompletas, geração local, manifesto/ZIP, limpeza após falhas e publicação de arquivos sem renomear diretórios no Windows.

Também foram executados testes reais no ambiente: Docling no container existente reconheceu capítulos e subseções e recuperou uma equação com expoente e uma fração em um PDF digitalizado; uma solicitação de narração ao `gpt-oss:20b` via `http://localhost:11434` retornou a equação por extenso; Kokoro gerou MP3 em português. A página digitalizada também apresentou palavras unidas no OCR, reforçando a necessidade de revisão. O `qwen3:8b` ainda precisa ser baixado para ser validado neste computador. Esses testes não constituem uma avaliação científica de precisão em um acervo real.

```powershell
.venv\Scripts\python.exe -m pytest -q
```

`requirements-lock.txt` registra as versões usadas na validação. Os modelos binários não estão no ZIP.

## Referências

- [Qwen3:8b no Ollama](https://ollama.com/library/qwen3:8b)
- [API Chat do Ollama](https://docs.ollama.com/api/chat)
- [Modos de raciocínio do Ollama](https://docs.ollama.com/capabilities/thinking)
- [Fórmulas no Docling](https://docling-project.github.io/docling/usage/enrichments/)
- [Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx)
- [Vozes Kokoro](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
