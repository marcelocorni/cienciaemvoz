using CienciaEmVoz.Portal.Components;
using CienciaEmVoz.Portal.Services;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.
builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();
builder.Services.Configure<PortalOptions>(builder.Configuration.GetSection("Portal"));
builder.Services.AddSingleton<LibraryCatalog>();

var app = builder.Build();

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
}
app.UseStatusCodePagesWithReExecute("/not-found", createScopeForStatusCodePages: true);
app.UseAntiforgery();

app.MapGet("/conteudo/{id}/pdf", (string id, LibraryCatalog catalog) =>
    catalog.Find(id)?.PdfPath is { } path && File.Exists(path)
        ? Results.File(path, "application/pdf", enableRangeProcessing: true) : Results.NotFound());
app.MapGet("/conteudo/{id}/audio/{filename}", (string id, string filename, LibraryCatalog catalog) =>
    catalog.AudioPath(id, filename) is { } path && File.Exists(path)
        ? Results.File(path, "audio/mpeg", enableRangeProcessing: true) : Results.NotFound());

app.MapStaticAssets();
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
