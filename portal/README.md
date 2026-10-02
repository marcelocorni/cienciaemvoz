# Portal Ciência em Voz

Portal de leitura em **.NET 10 + Blazor Server**. Exibe o PDF original em um painel central, com uma lista de MP3 e reprodução sequencial no navegador. É independente do aplicativo Python que gera as transcrições e os áudios.

## Executar

Instale o [.NET SDK 10](https://dotnet.microsoft.com/download/dotnet/10.0). Na pasta do repositório:

```powershell
dotnet run --project portal
```

Abra **http://localhost:5080**. O primeiro comando restaura as dependências. Após a instalação, não é necessário Ollama, Kokoro ou internet para ler os PDFs e reproduzir os MP3 locais.

## Adicionar a primeira dissertação

Copie o PDF para `portal/transcricoes/pdf/` e os MP3 para `portal/transcricoes/audio/`. Com um único PDF na biblioteca, os MP3 diretamente na pasta `audio` pertencem a ele. O nome do PDF será usado como título. Clique em **Atualizar biblioteca** ou recarregue a página após adicionar ou remover arquivos.

```text
portal/
  transcricoes/
    pdf/
      dissertacao.pdf
    audio/
      001-resumo.mp3
      002-introducao.mp3
      003-metodologia.mp3
```

Não copie os arquivos temporários `part-xxxxx.mp3`: use os MP3 finais gerados pelo aplicativo Ciência em Voz. Os TXT e o manifesto da geração não são necessários ao portal. Os documentos e áudios ficam fora do Git por padrão; mantenha uma cópia de segurança independente.

## Adicionar outros documentos

Adicione cada PDF à pasta `pdf` e crie, dentro de `audio`, uma subpasta com **o mesmo nome do PDF sem a extensão**. Não é necessário editar o código ou reiniciar o servidor.

```text
transcricoes/
  pdf/
    dissertacao.pdf
    artigo-revisao.pdf
  audio/
    dissertacao/
      001-resumo.mp3
      002-introducao.mp3
    artigo-revisao/
      001-resumo.mp3
      002-resultados.mp3
```

Ao adicionar um segundo PDF, mova os MP3 da primeira dissertação para a subpasta correspondente. A pasta plana só é associada automaticamente quando existe **um único documento**. A biblioteca não mistura os áudios de diferentes PDFs.

Os MP3 são ordenados pelo nome em ordem natural: `1`, `2`, `10`. Recomenda-se prefixar os nomes com `001`, `002`, `003`, etc., para explicitar a sequência. Não há alinhamento automático entre seção de áudio e página do PDF.

## Personalizar títulos e o link do GitHub

Em `appsettings.json`, a seção `Portal` tem um espaço para o repositório. Preencha `GithubUrl` com a URL HTTPS real, por exemplo `https://github.com/SEU-USUARIO/ciencia-em-voz`. Enquanto estiver vazio, a Home mostra um espaço reservado.

Para títulos, descrições e agrupamentos personalizados, configure `Documents`. PDFs não cadastrados continuam aparecendo automaticamente:

```json
"Portal": {
  "GithubUrl": "",
  "LibraryPath": "transcricoes",
  "Documents": [
    {
      "Id": "dissertacao",
      "Title": "Minha dissertação",
      "Description": "Leitura do documento com narração por seção.",
      "Pdf": "dissertacao.pdf",
      "AudioFolder": "dissertacao"
    }
  ]
}
```

O `Id` usa letras minúsculas sem acento, números e hífens. `Pdf` é relativo à pasta `pdf`; `AudioFolder` é relativo à pasta `audio`. Para um cadastro que usa MP3 diretamente em `audio`, deixe `AudioFolder` vazio. `LibraryPath` é relativo à pasta do projeto do portal ou pode ser absoluto. Recarregue a página após alterar a configuração.

## Controles

- **Play:** começa do primeiro áudio; quando pausado, retoma o áudio atual no mesmo instante.
- **Pause:** mantém o áudio e a posição atuais.
- **Stop:** interrompe a reprodução e volta ao primeiro áudio, no início.
- **Fim do áudio:** inicia automaticamente o próximo. No fim da lista, Play recomeça a sequência.
- **Lista de seções:** clique para iniciar qualquer áudio diretamente.
- **Velocidade:** de 0,75× a 2×; mantida ao avançar para outro áudio.
- **Barra de posição:** permite avançar ou voltar dentro do áudio atual.

Ao sair da página de leitura ou recarregá-la, a reprodução é encerrada. A retomada de Pause vale durante a sessão atual da página; não há persistência do progresso após fechar o navegador.

O painel de PDF utiliza **PDF.js**, incluído localmente com os arquivos de fontes e decodificação necessários; não depende de CDN nem do visualizador nativo do navegador. Use os controles de página e zoom para ler o documento. **Abrir PDF** permite consultar o original em outra aba, inclusive para seleção de texto e impressão. Em telas pequenas, o player fica acima do documento. Caso o navegador bloqueie a reprodução automática, pressione Play para continuar.

## Verificação e publicação

```powershell
dotnet build portal
dotnet test portal.Tests
dotnet publish portal -c Release -o portal-publicado
```

Copie a pasta `transcricoes` com o conteúdo para junto dos arquivos publicados e execute o portal na pasta publicada. PDF e MP3 são servidos por rotas com suporte a requisições parciais, permitindo busca no áudio sem baixar o arquivo inteiro primeiro. Apenas arquivos pertencentes ao catálogo são servidos.

O portal é de leitura e não inclui upload pela interface, autenticação ou gerenciamento de usuários. Os arquivos da biblioteca são públicos para quem tem acesso ao servidor. A execução padrão usa localhost; publicação externa exige configuração de hospedagem e HTTPS.
