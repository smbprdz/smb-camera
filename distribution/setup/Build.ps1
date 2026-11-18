[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
$packagePath = (Resolve-Path -LiteralPath $Package).Path
$destinationPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
if ((Test-Path -LiteralPath $destinationPath) -or [IO.Path]::GetExtension($destinationPath) -ne '.exe') {
    throw 'Choose a new .exe output path.'
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($packagePath)
try {
    $entry = $zip.Entries | Where-Object { $_.Name -eq 'MANIFEST.json' }
    if (@($entry).Count -ne 1) { throw 'Expected one package manifest.' }
    $reader = [IO.StreamReader]::new($entry.Open())
    try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json }
    finally { $reader.Dispose() }
    $root = $entry.FullName.Substring(0, $entry.FullName.LastIndexOf('/') + 1)
    $payload = @($zip.Entries | Where-Object { $_.Name -and $_.FullName -ne $entry.FullName })
    if ($payload.Count -ne @($manifest.files.PSObject.Properties).Count) { throw 'Unexpected package entries.' }
    foreach ($member in $manifest.files.PSObject.Properties) {
        $item = $zip.GetEntry($root + $member.Name)
        if (-not $item) { throw "Missing package member: $($member.Name)" }
        $stream = $item.Open()
        try { $actual = (Get-FileHash -InputStream $stream -Algorithm SHA256).Hash }
        finally { $stream.Dispose() }
        if ($actual -ne $member.Value) { throw "Package member changed: $($member.Name)" }
    }
}
finally { $zip.Dispose() }

$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw '.NET Framework compiler not found.' }
$icon = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../ucs/assets/live-icon.ico')).Path
New-Item -ItemType Directory -Path (Split-Path -Parent $destinationPath) -Force | Out-Null
$compilerArgs=@(
    '/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/codepage:65001',
    "/out:$destinationPath", "/win32icon:$icon", "/resource:$packagePath,SMB.Camera.Windows.Beta",
    '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
    '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
    (Join-Path $PSScriptRoot 'Setup.cs'), (Join-Path $PSScriptRoot 'SetupWindow.cs')
)
& $compiler @compilerArgs
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256
