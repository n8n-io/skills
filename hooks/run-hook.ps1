param(
  [Parameter(Mandatory = $true)]
  [string]$Action
)

$nodeExecutable = $env:N8N_SKILLS_NODE_EXE

if ([string]::IsNullOrWhiteSpace($nodeExecutable)) {
  $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
  if ($null -ne $nodeCommand) {
    $nodeExecutable = $nodeCommand.Source
  }
}

if ([string]::IsNullOrWhiteSpace($nodeExecutable) -and $env:USERPROFILE) {
  $bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
  if (Test-Path -LiteralPath $bundledNode) {
    $nodeExecutable = $bundledNode
  }
}

if ([string]::IsNullOrWhiteSpace($nodeExecutable) -or -not (Test-Path -LiteralPath $nodeExecutable)) {
  exit 0
}

& $nodeExecutable (Join-Path $PSScriptRoot "n8n-hooks.mjs") $Action
exit $LASTEXITCODE
