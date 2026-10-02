using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Options;

namespace CienciaEmVoz.Portal.Services;

public sealed class PortalOptions
{
    public string GithubUrl { get; set; } = "";
    public string LibraryPath { get; set; } = "transcricoes";
    public List<DocumentOptions> Documents { get; set; } = [];
}
public sealed class DocumentOptions
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
    public string Description { get; set; } = "";
    public string Pdf { get; set; } = "";
    public string AudioFolder { get; set; } = "";
}
public sealed record AudioTrack(string FileName, string Title, string Url, string FilePath);
public sealed record LibraryDocument(string Id, string Title, string Description, string? PdfPath,
    IReadOnlyList<AudioTrack> Tracks)
{
    public string PdfUrl => $"/conteudo/{Uri.EscapeDataString(Id)}/pdf";
}
public sealed class LibraryCatalog(IWebHostEnvironment environment, IOptionsMonitor<PortalOptions> options,
    ILogger<LibraryCatalog> logger)
{
    public string Root => Path.GetFullPath(options.CurrentValue.LibraryPath, environment.ContentRootPath);
    public string? GithubUrl => Uri.TryCreate(options.CurrentValue.GithubUrl, UriKind.Absolute, out var uri)
        && uri.Scheme == "https" && uri.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase)
        ? uri.AbsoluteUri : null;
    public IReadOnlyList<LibraryDocument> GetDocuments()
    {
        var pdfRoot = Path.Combine(Root, "pdf");
        var audioRoot = Path.Combine(Root, "audio");
        var pdfs = Directory.Exists(pdfRoot)
            ? Directory.EnumerateFiles(pdfRoot).Where(p => Path.GetExtension(p).Equals(".pdf", StringComparison.OrdinalIgnoreCase))
                .OrderBy(p => p, NaturalComparer.Instance).ToList() : [];
        var result = new List<LibraryDocument>();
        var usedPdfs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var item in options.CurrentValue.Documents)
        {
            if (!Regex.IsMatch(item.Id, @"^[a-z0-9][a-z0-9-]*$") || result.Any(d => d.Id == item.Id)) continue;
            var path = SafeChild(pdfRoot, item.Pdf);
            if (path is not null && !Path.GetExtension(path).Equals(".pdf", StringComparison.OrdinalIgnoreCase)) path = null;
            if (path is not null) usedPdfs.Add(path);
            var folder = string.IsNullOrEmpty(item.AudioFolder) ? audioRoot : SafeChild(audioRoot, item.AudioFolder);
            result.Add(Create(item.Id, ReadTitle(path) ?? (string.IsNullOrWhiteSpace(item.Title) ? DisplayTitle(item.Id) : item.Title),
                item.Description, path, folder));
        }
        foreach (var pdf in pdfs.Where(p => !usedPdfs.Contains(p)))
        {
            var stem = Path.GetFileNameWithoutExtension(pdf);
            var slug = Slug(stem);
            var id = slug;
            for (var suffix = 2; result.Any(d => d.Id == id); suffix++) id = $"{slug}-{suffix}";
            var folder = SafeChild(audioRoot, stem);
            if (folder is null || !Directory.Exists(folder)) folder = SafeChild(audioRoot, slug);
            if ((folder is null || !Directory.Exists(folder)) && pdfs.Count == 1 && result.Count == 0) folder = audioRoot;
            result.Add(Create(id, ReadTitle(pdf) ?? DisplayTitle(stem), "Leitura acompanhada de narração científica.", pdf, folder));
        }
        return result.Count == 0
            ? [new("dissertacao", "Dissertação", "O documento e os áudios serão disponibilizados em breve.", null, [])]
            : result;
    }
    public LibraryDocument? Find(string id) => GetDocuments().FirstOrDefault(d => d.Id == id);
    public string? AudioPath(string id, string filename) => Find(id)?.Tracks.FirstOrDefault(t => t.FileName == filename)?.FilePath;
    private string? ReadTitle(string? pdf)
    {
        if (pdf is null) return null;
        var path = Path.ChangeExtension(pdf, ".txt");
        try
        {
            if (!File.Exists(path)) return null;
            // A title is metadata, not a full transcript. Accept UTF-8 and BOM-marked Unicode.
            if (new FileInfo(path).Length > 16 * 1024)
            {
                logger.LogWarning("Arquivo de título excede 16 KB: {Path}", path);
                return null;
            }
            var title = Regex.Replace(File.ReadAllText(path, new UTF8Encoding(false, true)), @"\s+", " ").Trim();
            return title.Length == 0 ? null : title;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or DecoderFallbackException)
        {
            logger.LogWarning(error, "Não foi possível ler o arquivo de título: {Path}", path);
            return null;
        }
    }
    private static LibraryDocument Create(string id, string title, string description, string? pdf, string? audioFolder)
    {
        var tracks = new List<AudioTrack>();
        if (audioFolder is not null && Directory.Exists(audioFolder))
            foreach (var file in Directory.EnumerateFiles(audioFolder)
                .Where(f => Path.GetExtension(f).Equals(".mp3", StringComparison.OrdinalIgnoreCase))
                .OrderBy(f => Path.GetFileName(f), NaturalComparer.Instance))
            {
                var filename = Path.GetFileName(file);
                var url = $"/conteudo/{Uri.EscapeDataString(id)}/audio/{Uri.EscapeDataString(filename)}";
                tracks.Add(new(filename, AudioTitle(Path.GetFileNameWithoutExtension(file)), url, file));
            }
        return new(id, title, description, pdf is not null && File.Exists(pdf) ? pdf : null, tracks);
    }
    public static string? SafeChild(string parent, string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative)) return null;
        var root = Path.GetFullPath(parent) + Path.DirectorySeparatorChar;
        var path = Path.GetFullPath(Path.Combine(parent, relative));
        return path.StartsWith(root, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal)
            ? path : null;
    }
    private static string DisplayTitle(string text)
    {
        var title = Regex.Replace(text.Replace('_', ' ').Replace('-', ' '), @"\s+", " ").Trim();
        return title.Length == 0 ? title : char.ToUpper(title[0], CultureInfo.GetCultureInfo("pt-BR")) + title[1..];
    }
    private static string AudioTitle(string stem)
    {
        // Export filenames can repeat a padded sequence number. Keep section numbers.
        var title = Regex.Replace(stem, @"^(?:\d{3}[-_])+(?:0[01][-_])?", "");
        var section = Regex.Match(title, @"^(\d+(?:-\d+)*)-(?=[a-zA-Z])");
        if (section.Success)
            return section.Groups[1].Value.Replace('-', '.') + " · " + DisplayTitle(title[section.Length..]);
        return DisplayTitle(title);
    }
    private static string Slug(string text)
    {
        var plain = new string(text.Normalize(NormalizationForm.FormD)
            .Where(c => CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark).ToArray());
        var slug = Regex.Replace(plain.ToLowerInvariant(), "[^a-z0-9]+", "-").Trim('-');
        return slug.Length == 0 ? "documento" : slug;
    }
}
public sealed class NaturalComparer : IComparer<string>
{
    public static NaturalComparer Instance { get; } = new();
    public int Compare(string? x, string? y)
    {
        if (x == y) return 0;
        if (x is null) return -1;
        if (y is null) return 1;
        var a = Regex.Split(x, @"(\d+)");
        var b = Regex.Split(y, @"(\d+)");
        for (var i = 0; i < Math.Min(a.Length, b.Length); i++)
        {
            int comparison;
            if (i % 2 == 1)
            {
                var n = a[i].TrimStart('0');
                var m = b[i].TrimStart('0');
                comparison = n.Length.CompareTo(m.Length);
                if (comparison == 0) comparison = string.CompareOrdinal(n, m);
            }
            else comparison = StringComparer.OrdinalIgnoreCase.Compare(a[i], b[i]);
            if (comparison != 0) return comparison;
        }
        var length = a.Length.CompareTo(b.Length);
        return length != 0 ? length : StringComparer.Ordinal.Compare(x, y);
    }
}
