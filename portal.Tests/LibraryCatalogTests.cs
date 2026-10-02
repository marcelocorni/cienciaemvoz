using CienciaEmVoz.Portal.Services;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Options;

namespace CienciaEmVoz.Portal.Tests;

public sealed class LibraryCatalogTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "ciencia-portal-test-" + Guid.NewGuid().ToString("N"));
    private readonly PortalOptions settings = new();
    private LibraryCatalog Catalog => new(new TestEnvironment { ContentRootPath = root }, new TestOptions(settings));
    private void Add(string relative)
    {
        var path = Path.Combine(root, "transcricoes", relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "fixture");
    }
    [Fact]
    public void EmptyLibraryHasPlaceholderWithoutPlayback()
    {
        var document = Assert.Single(Catalog.GetDocuments());
        Assert.Equal("dissertacao", document.Id);
        Assert.Null(document.PdfPath);
        Assert.Empty(document.Tracks);
    }
    [Fact]
    public void SinglePdfUsesFlatAudioWithNaturalOrderAndEncodedUrls()
    {
        Add("pdf/Dissertação científica.PDF");
        Add("audio/10-conclusão.MP3"); Add("audio/2-análise.mp3"); Add("audio/1-resumo.mp3"); Add("audio/notas.txt");
        var document = Assert.Single(Catalog.GetDocuments());
        Assert.Equal("dissertacao-cientifica", document.Id);
        Assert.Equal(["1-resumo.mp3", "2-análise.mp3", "10-conclusão.MP3"], document.Tracks.Select(t => t.FileName));
        Assert.Contains("an%C3%A1lise", document.Tracks[1].Url);
        Assert.NotNull(Catalog.AudioPath(document.Id, "2-análise.mp3"));
        Assert.Null(Catalog.AudioPath(document.Id, "../notas.txt"));
    }
    [Fact]
    public void MultipleDocumentsNeverShareFlatAudioAndRefreshWithoutRestart()
    {
        Add("pdf/tese.pdf"); Add("audio/001.mp3");
        var catalog = Catalog;
        Assert.Single(Assert.Single(catalog.GetDocuments()).Tracks);
        Add("pdf/artigo.pdf"); Add("audio/artigo/002.mp3");
        var docs = catalog.GetDocuments();
        Assert.Equal(2, docs.Count);
        Assert.Empty(docs.Single(d => d.Id == "tese").Tracks);
        Assert.Single(docs.Single(d => d.Id == "artigo").Tracks);
        Add("audio/tese/001.mp3");
        Assert.Single(catalog.Find("tese")!.Tracks);
    }
    [Fact]
    public void ConfigurationCustomizesTitlesAndGroupsWithoutDuplicatePdf()
    {
        Add("pdf/tese.pdf"); Add("audio/capitulos/001.mp3");
        settings.Documents.Add(new() { Id = "minha-tese", Title = "Minha tese", Pdf = "tese.pdf", AudioFolder = "capitulos" });
        var document = Assert.Single(Catalog.GetDocuments());
        Assert.Equal("Minha tese", document.Title);
        Assert.Single(document.Tracks);
        Assert.Equal("/conteudo/minha-tese/pdf", document.PdfUrl);
    }
    [Fact]
    public void ExportCountersAreHiddenWhileSectionNumbersRemainReadable()
    {
        Add("pdf/tese.pdf");
        Add("audio/001-001-00-resumo.mp3");
        Add("audio/002-002-5-6-4-resultados.mp3");
        var tracks = Assert.Single(Catalog.GetDocuments()).Tracks;
        Assert.Equal("Resumo", tracks[0].Title);
        Assert.Equal("5.6.4 · Resultados", tracks[1].Title);
    }
    [Theory]
    [InlineData("../outside.pdf")]
    [InlineData("nested/../../outside.pdf")]
    public void PathsCannotEscapeLibrary(string path)
    {
        Assert.Null(LibraryCatalog.SafeChild(Path.Combine(root, "transcricoes/pdf"), path));
    }
    [Fact]
    public void GithubPlaceholderOnlyAcceptsRealHttpsGithubLinks()
    {
        Assert.Null(Catalog.GithubUrl);
        settings.GithubUrl = "javascript:alert(1)"; Assert.Null(Catalog.GithubUrl);
        settings.GithubUrl = "https://github.com.evil.example/user/repo"; Assert.Null(Catalog.GithubUrl);
        settings.GithubUrl = "https://github.com/user/repo";
        Assert.Equal(settings.GithubUrl, Catalog.GithubUrl);
    }
    public void Dispose() { if (Directory.Exists(root)) Directory.Delete(root, recursive: true); }

    private sealed class TestOptions(PortalOptions value) : IOptionsMonitor<PortalOptions>
    {
        public PortalOptions CurrentValue => value;
        public PortalOptions Get(string? name) => value;
        public IDisposable? OnChange(Action<PortalOptions, string?> listener) => null;
    }
    private sealed class TestEnvironment : IWebHostEnvironment
    {
        public string ApplicationName { get; set; } = "Test";
        public string EnvironmentName { get; set; } = "Test";
        public string ContentRootPath { get; set; } = "";
        public string WebRootPath { get; set; } = "";
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
        public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
    }
}
