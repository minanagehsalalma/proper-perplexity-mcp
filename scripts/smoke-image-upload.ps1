param(
    [Parameter(Mandatory = $true)]
    [string]$ImagePath,

    [string]$Query = "Look only at the uploaded image and describe the key visible facts.",

    [ValidateSet("perplexity_ask", "perplexity_research")]
    [string]$Tool = "perplexity_ask",

    [ValidateSet("markdown", "json")]
    [string]$ResponseFormat = "markdown",

    [switch]$ShowStructured
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$script = Join-Path $repoRoot "scripts\mcp_stdio_smoke.py"

$args = @(
    $script,
    "--tool", $Tool,
    "--query", $Query,
    "--image-path", $ImagePath,
    "--response-format", $ResponseFormat
)

if ($ShowStructured) {
    $args += "--show-structured"
}

& $python @args
