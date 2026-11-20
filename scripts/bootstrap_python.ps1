#requires -Version 5.1
<#
  Windows-only Python fallback for install.bat. No winget, Store account,
  machine-wide PATH, service, provider account or administrator elevation.
  The existing Python installer continues with the original CLI arguments.
  Dot-source with -LibraryOnly for offline tests; that never runs setup.
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$LibraryOnly,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$InstallerArguments = @()
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Assert-BootstrapPlatform {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
        throw 'Automatic Windows setup requires 64-bit x64 Windows with PowerShell 5.1. Use start.sh on macOS/Linux.'
    }
    $nativeArchitecture = $env:PROCESSOR_ARCHITEW6432
    if (-not $nativeArchitecture) { $nativeArchitecture = $env:PROCESSOR_ARCHITECTURE }
    if ($nativeArchitecture -ne 'AMD64') {
        throw 'This automatic Windows package supports x64 PCs, not ARM64 or 32-bit Windows.'
    }
}

function Get-BootstrapSpec([string]$Root) {
    $spec = Get-Content -LiteralPath (Join-Path $Root 'deploy/windows-bootstrap.json') -Raw | ConvertFrom-Json
    if ($spec.python_version -notmatch '^3\.13\.\d{1,2}$' -or
        $spec.python_windows_x64_sha256 -notmatch '^[a-fA-F0-9]{64}$') {
        throw 'The Windows bootstrap manifest is invalid. Extract a complete, trusted app download.'
    }
    return $spec
}

function Get-PreparedPython([string]$Root) {
    $manifestFile = Join-Path $Root 'runtime/windows-x64/bundle.json'
    if (-not (Test-Path -LiteralPath $manifestFile -PathType Leaf)) { return $null }
    $manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.platform -ne 'win_amd64') { throw 'Invalid prepared runtime manifest.' }
    # Validate native executable and its DLLs before loading the interpreter.
    foreach ($name in @('python.exe', 'python313.dll', 'python3.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
        $relative = 'runtime/windows-x64/python/' + $name
        $property = $manifest.files.PSObject.Properties[$relative]
        if (-not $property -or $property.Value -notmatch '^[a-f0-9]{64}$') { throw 'Prepared Python manifest is incomplete.' }
        $file = Join-Path $Root $relative
        if (-not (Test-InstallerHash $file $property.Value)) {
            Write-Warning 'Prepared Python is incomplete/corrupt and will NOT be executed. Discovering a compatible interpreter or downloading the verified official installer instead; no app data is changed.'
            return $null
        }
    }
    $python = Join-Path $Root 'runtime/windows-x64/python/python.exe'
    Assert-InstallerSignature $python
    return $python
}

function Get-RegisteredPythonPaths {
    foreach ($hive in @('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE')) {
        foreach ($version in @('3.13', '3.12', '3.11')) {
            $key = "$hive\Software\Python\PythonCore\$version\InstallPath"
            try {
                $exe = [Microsoft.Win32.Registry]::GetValue($key, 'ExecutablePath', $null)
                if ($exe) { [string]$exe }
                $folder = [Microsoft.Win32.Registry]::GetValue($key, '', $null)
                if ($folder) { Join-Path ([string]$folder) 'python.exe' }
            } catch { continue }
        }
    }
}

function Get-UsablePython([string]$Root) {
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    if ($env:ROASTBOX_PYTHON_EXE) { $candidates.Add($env:ROASTBOX_PYTHON_EXE) }
    $candidates.Add((Join-Path $Root '.venv/Scripts/python.exe'))
    $tools = Join-Path $Root '.cache/local-tools'
    if (Test-Path -LiteralPath $tools -PathType Container) {
        Get-ChildItem -LiteralPath $tools -Directory -Filter 'python-*' | ForEach-Object {
            $candidates.Add((Join-Path $_.FullName 'python.exe'))
        }
    }
    foreach ($exe in @(Get-RegisteredPythonPaths)) { $candidates.Add($exe) }
    foreach ($version in @('313', '312', '311')) {
        if ($env:LOCALAPPDATA) { $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs/Python/Python$version/python.exe")) }
        if ($env:ProgramFiles) { $candidates.Add((Join-Path $env:ProgramFiles "Python$version/python.exe")) }
    }
    foreach ($drive in @([IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'Fixed' -and $_.IsReady })) {
        foreach ($folder in @('Python313', 'Python312', 'Python311', 'Tools/Python313')) {
            $candidates.Add((Join-Path $drive.RootDirectory.FullName ($folder + '/python.exe')))
        }
    }
    foreach ($command in @(Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue)) {
        if ($command.Source -match '(?i)[\\/]WindowsApps[\\/]') { continue }
        try {
            foreach ($line in @(& $command.Source -0p 2>$null)) {
                if ($line -match '^\s*-(?:V:)?3\.(?:11|12|13)[\w.-]*\s+\*?\s*(.+?python\.exe)\s*$') {
                    $candidates.Add($Matches[1].Trim())
                }
            }
        } catch { continue }
    }
    foreach ($command in @(Get-Command python.exe, python3.exe -CommandType Application -ErrorAction SilentlyContinue)) {
        $candidates.Add($command.Source)
    }
    foreach ($exe in ($candidates | Select-Object -Unique)) {
        if ($exe -match '(?i)[\\/]WindowsApps[\\/]' -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) { continue }
        try {
            $result = @(& $exe -I -c 'import base64,sys; assert (3,11)<=sys.version_info[:2]<(3,14) and sys.maxsize>2**32; print(base64.b64encode(sys.executable.encode()).decode())' 2>$null)
            if ($LASTEXITCODE -eq 0 -and $result.Count -eq 1) {
                $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$result[0]))
                if (Test-Path -LiteralPath $decoded -PathType Leaf) { return $decoded }
            }
        } catch { continue }
    }
    return $null
}

function Test-InstallerHash([string]$Path, [string]$Sha256) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Sha256
}

function Assert-InstallerSignature([string]$Path) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(?i)(?:^|,\s*)O=\"?Python Software Foundation\"?(?:,|$)') {
        throw 'Python publisher signature verification failed. Nothing was executed. Check Windows certificate updates, date and network, then retry.'
    }
}

function Save-OfficialInstaller([string]$Uri, [string]$Destination, [int]$Attempt) {
    # Keep certificate validation enabled. Windows/enterprise proxy settings apply.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing -TimeoutSec 180 -MaximumRedirection 3
}

function Get-VerifiedInstaller([string]$Root, $Spec) {
    $version = [string]$Spec.python_version
    $cache = Join-Path $Root '.cache/downloads'
    [IO.Directory]::CreateDirectory($cache) | Out-Null
    $installer = Join-Path $cache "python-$version-amd64.exe"
    $sha256 = [string]$Spec.python_windows_x64_sha256
    if (Test-InstallerHash $installer $sha256) {
        Assert-InstallerSignature $installer
        return $installer
    }
    # Replace only this known, invalid installer cache, never general caches/data.
    if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force }
    $partial = "$installer.part"
    $uri = "https://www.python.org/ftp/python/$version/python-$version-amd64.exe"
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
            Write-Host "Downloading official Python $version (attempt $attempt of 3)..."
            Save-OfficialInstaller $uri $partial $attempt
            if (-not (Test-InstallerHash $partial $sha256)) {
                throw 'The Python download checksum did not match the pinned release.'
            }
            Move-Item -LiteralPath $partial -Destination $installer -Force
            # Bad publisher signatures fail closed rather than running/retrying.
        } catch {
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
            if ($attempt -ge 3) {
                throw "Python could not be downloaded safely after 3 attempts. Check internet, proxy, free disk space and Windows security; then double-click the launcher again. Last error: $($_.Exception.Message)"
            }
            Write-Warning 'Download interrupted or checksum mismatch; retrying safely.'
            Start-Sleep -Seconds (2 * $attempt)
            continue
        }
        Assert-InstallerSignature $installer
        return $installer
    }
    throw 'No verified Python installer is available.'
}

function Start-PythonInstaller([string]$Installer, [string]$Target) {
    # These settings are per-user. Never request RunAs, alter the system PATH,
    # register file associations or replace the global Python launcher.
    $arguments = @('/quiet', '/norestart', 'InstallAllUsers=0', "TargetDir=`"$Target`"", 'Include_pip=1',
        'Include_launcher=0', 'InstallLauncherAllUsers=0', 'PrependPath=0',
        'AssociateFiles=0', 'Shortcuts=0', 'Include_test=0', 'Include_doc=0',
        'Include_tcltk=0', 'Include_dev=0', 'Include_symbols=0', 'Include_debug=0', 'CompileAll=0')
    $temporary = Join-Path (Split-Path -Parent (Split-Path -Parent $Target)) 'tmp/python-bootstrap'
    [IO.Directory]::CreateDirectory($temporary) | Out-Null
    $oldTemp = $env:TEMP; $oldTmp = $env:TMP
    try {
        $env:TEMP = $temporary; $env:TMP = $temporary
        $process = Start-Process -FilePath $Installer -ArgumentList $arguments -PassThru -NoNewWindow
        if (-not $process.WaitForExit(900000)) {
            throw 'Python setup is still running after 15 minutes. Do not start another installer. Check Windows Installer or restart Windows after saving your work; then relaunch.'
        }
        $process.Refresh()
        return [int]$process.ExitCode
    } finally { $env:TEMP = $oldTemp; $env:TMP = $oldTmp }
}

function Enter-PythonBootstrapLock {
    # Serializes missing-Python setup across copies of the app in this session.
    # It is an OS handle, not a persistent lock that can strand the next launch.
    $name = 'Local\DaRoastBox-Python313-' + [Environment]::UserName
    $mutex = New-Object System.Threading.Mutex($false, $name)
    try {
        Write-Host 'Checking Python setup; waiting if another launch is preparing it...'
        try { $acquired = $mutex.WaitOne(900000) }
        catch [System.Threading.AbandonedMutexException] { $acquired = $true }
        if (-not $acquired) { throw 'Another Python setup is still active. Let it finish, then double-click the launcher again.' }
        return $mutex
    } catch { $mutex.Dispose(); throw }
}

function Exit-PythonBootstrapLock($Mutex) {
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}

function Ensure-BootstrapPython([string]$Root) {
    Assert-BootstrapPlatform
    $spec = Get-BootstrapSpec $Root
    $prepared = Get-PreparedPython $Root
    if ($prepared) { Write-Host 'Using the already-installed, project-local Windows Python runtime.'; return $prepared }
    $python = Get-UsablePython $Root
    if ($python) { Write-Host 'Reusing an existing supported 64-bit Python.'; return $python }
    $mutex = Enter-PythonBootstrapLock
    try {
        $python = Get-UsablePython $Root
        if ($python) { Write-Host 'Reusing an existing supported 64-bit Python.'; return $python }
        $target = Join-Path $Root ('.cache/local-tools/python-' + $spec.python_version)
        $installer = Get-VerifiedInstaller $Root $spec
        Write-Host 'Installing Python for this Windows user. No administrator installation or PATH changes...'
        $code = Start-PythonInstaller $installer $target
        if ($code -eq 1602 -or $code -eq 1223) { throw 'Python installation was cancelled. No automatic elevation or retry will bypass your decision.' }
        if ($code -eq 1618) { throw 'Another Windows installation is active. Let it finish, then double-click the launcher again.' }
        if ($code -eq 1641 -or $code -eq 3010) { throw 'Windows requires a restart to finish Python setup. Save your work, restart Windows yourself, then relaunch. The app will not reboot your computer.' }
        if ($code -ne 0) { throw "Python installation failed with Windows Installer code $code. Your settings and data were not changed by the bootstrap." }
        $python = Get-UsablePython $Root
        if (-not $python) { throw 'Python setup finished, but no working supported x64 interpreter was found. Relaunch after checking Windows security and permissions.' }
        return $python
    } finally { Exit-PythonBootstrapLock $mutex }
}

function Invoke-ProjectInstaller([string]$Python, [string]$Root, [string[]]$Arguments) {
    # Native argument arrays preserve spaces/Unicode without writing an executable
    # path into an OEM-encoded CMD result file. Never eval a command string.
    $oldUtf8 = $env:PYTHONUTF8; $oldIo = $env:PYTHONIOENCODING
    $oldEncoding = [Console]::OutputEncoding
    $oldAction = $ErrorActionPreference
    try {
        $env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        # Windows PowerShell 5.1 may wrap ordinary native stderr as ErrorRecords.
        # Show those messages but let the real process exit code decide success.
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = 1
        $entry = 'install.py'
        if ($Arguments -contains '--start' -and (Test-Path -LiteralPath (Join-Path $Root 'start.py') -PathType Leaf)) { $entry = 'start.py' }
        & $Python (Join-Path $Root $entry) @Arguments | Out-Host
        return [int]$global:LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldAction
        $env:PYTHONUTF8 = $oldUtf8; $env:PYTHONIOENCODING = $oldIo
        [Console]::OutputEncoding = $oldEncoding
    }
}

function Invoke-WindowsBootstrap([string]$Root, [string[]]$Arguments) {
    $Root = [IO.Path]::GetFullPath($Root)
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'install.py') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $Root 'scripts/local_start.py') -PathType Leaf)) {
        throw 'Extract ALL files from the download first. Do not run the launcher inside the ZIP viewer.'
    }
    $python = Ensure-BootstrapPython $Root
    return Invoke-ProjectInstaller $python $Root $Arguments
}

if (-not $LibraryOnly) {
    try { exit (Invoke-WindowsBootstrap $ProjectRoot $InstallerArguments) }
    catch { Write-Host ''; Write-Host ('SETUP STOPPED: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
}
