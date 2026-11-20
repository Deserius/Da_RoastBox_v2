#requires -Version 5.1
<# Offline fixture tests. Never installs Python, calls a provider or downloads.
   Can run in Windows PowerShell 5.1, or PowerShell Core on Linux for logic checks.
   Linux results are NOT native Windows/UAC/browser certification. #>
[CmdletBinding()]
param([string]$SourceRoot = (Split-Path -Parent $PSScriptRoot))
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'bootstrap_python.ps1') -LibraryOnly -ProjectRoot $SourceRoot

$script:Passed = 0
$script:Failed = 0
$script:TestBase = Join-Path ([IO.Path]::GetTempPath()) ('roastbox-bootstrap-tests-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($script:TestBase) | Out-Null

# Defense in depth: unmocked networking/native installation always fails.
function Invoke-WebRequest { throw 'OFFLINE TEST GUARD: real networking is prohibited.' }
function Start-Process { throw 'OFFLINE TEST GUARD: real installer processes are prohibited.' }
function Start-Sleep { param([int]$Seconds) }

function Assert-True($Condition, [string]$Message = 'Assertion failed') {
    if (-not $Condition) { throw $Message }
}
function Assert-Equal($Actual, $Expected, [string]$Message = 'Values differ') {
    if ($Actual -cne $Expected) { throw "$Message. Expected [$Expected], received [$Actual]" }
}
function Expect-Failure([scriptblock]$Action, [string]$Pattern) {
    $caught = $null
    try { & $Action | Out-Null } catch { $caught = $_.Exception.Message }
    if (-not $caught -or $caught -notmatch $Pattern) { throw "Expected failure [$Pattern], received [$caught]" }
}
function New-Fixture([string]$Name) {
    $folder = Join-Path $script:TestBase ($Name + ' space &!%' + [char]0x2603 + [char]0x4e2d)
    [IO.Directory]::CreateDirectory($folder) | Out-Null
    foreach ($relative in @('backend/.env', 'frontend/.env', '.data/mongo/keep', 'backend/local_storage/keep')) {
        $file = Join-Path $folder $relative
        [IO.Directory]::CreateDirectory((Split-Path -Parent $file)) | Out-Null
        [IO.File]::WriteAllText($file, "KEEP=unchanged`r`n", (New-Object System.Text.UTF8Encoding($false)))
    }
    return $folder
}
function Assert-UserData([string]$Folder) {
    foreach ($relative in @('backend/.env', 'frontend/.env', '.data/mongo/keep', 'backend/local_storage/keep')) {
        Assert-Equal ([IO.File]::ReadAllText((Join-Path $Folder $relative))) "KEEP=unchanged`r`n" ('User data changed: ' + $relative)
    }
}
function New-Spec {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes('fixture installer only'))).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose() }
    return [PSCustomObject]@{python_version = '3.13.16'; python_windows_x64_sha256 = $digest}
}
function Write-FixtureInstaller([string]$Path) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, 'fixture installer only', (New-Object System.Text.UTF8Encoding($false)))
}
function Get-AuthenticodeSignature {
    param([string]$LiteralPath)
    return [PSCustomObject]@{Status = 'Valid'; SignerCertificate = [PSCustomObject]@{Subject = 'CN=Python Software Foundation, O=Python Software Foundation, C=US'}}
}
function Test-Case([string]$Name, [scriptblock]$Body) {
    try { & $Body; $script:Passed++; Write-Host ('PASS: ' + $Name) -ForegroundColor Green }
    catch { $script:Failed++; Write-Host ('FAIL: ' + $Name + ': ' + $_.Exception.Message) -ForegroundColor Red; Write-Host $_.ScriptStackTrace }
}

try {
    Test-Case 'PowerShell scripts parse and remain compatible with the 5.1 syntax baseline' {
        foreach ($name in @('bootstrap_python.ps1', 'test_windows_bootstrap.ps1')) {
            $tokens = $null; $errors = $null
            $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$errors)
            Assert-Equal $errors.Count 0 ('Parse failure in ' + $name)
            $unsupported = @($ast.FindAll({param($node) $node.GetType().Name -in @('TernaryExpressionAst', 'PipelineChainAst', 'NullConditionalExpressionAst')}, $true))
            Assert-Equal $unsupported.Count 0 'PowerShell 7-only syntax is not permitted'
        }
    }
    Test-Case 'Legacy launch flags survive PowerShell parameter binding as an argument array' {
        $root = New-Fixture 'parameter-binding'
        . (Join-Path $PSScriptRoot 'bootstrap_python.ps1') -LibraryOnly -ProjectRoot $root --start --repair --port 3211 --api-port 8001 --no-browser
        Assert-Equal ($InstallerArguments -join '|') '--start|--repair|--port|3211|--api-port|8001|--no-browser'
        Assert-UserData $root
    }
    Test-Case 'Manifest contains an official pinned Python version/hash' {
        $spec = Get-BootstrapSpec $SourceRoot
        Assert-Equal $spec.python_version '3.13.16'
        Assert-Equal $spec.python_windows_x64_sha256 'fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b'
    }
    Test-Case 'Malformed bootstrap manifest is rejected before download' {
        $root = New-Fixture 'invalid-spec'
        [IO.Directory]::CreateDirectory((Join-Path $root 'deploy')) | Out-Null
        [IO.File]::WriteAllText((Join-Path $root 'deploy/windows-bootstrap.json'), '{"python_version":"../bad","python_windows_x64_sha256":"no"}')
        Expect-Failure {Get-BootstrapSpec $root} 'manifest is invalid'
        Assert-UserData $root
    }
    Test-Case 'Cached hash-valid, signed installer is reused without network access' {
        $root = New-Fixture 'cached'
        $file = Join-Path $root '.cache/downloads/python-3.13.16-amd64.exe'
        Write-FixtureInstaller $file
        function Save-OfficialInstaller { throw 'Unexpected download' }
        Assert-Equal (Get-VerifiedInstaller $root (New-Spec)) $file
        Assert-UserData $root
    }
    Test-Case 'Interrupted and corrupt downloads retry then recover; partials are removed' {
        $root = New-Fixture 'retry'
        $script:Attempts = 0
        function Save-OfficialInstaller {
            param([string]$Uri, [string]$Destination, [int]$Attempt)
            $script:Attempts++
            Assert-Equal $Uri 'https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe'
            if ($Attempt -eq 1) { [IO.File]::WriteAllText($Destination, 'interrupted'); throw 'fixture connection interrupted' }
            if ($Attempt -eq 2) { [IO.File]::WriteAllText($Destination, 'wrong checksum'); return }
            Write-FixtureInstaller $Destination
        }
        $result = Get-VerifiedInstaller $root (New-Spec)
        Assert-Equal $script:Attempts 3
        Assert-True (Test-InstallerHash $result (New-Spec).python_windows_x64_sha256)
        Assert-True (-not (Test-Path -LiteralPath ($result + '.part')))
        Assert-UserData $root
    }
    Test-Case 'Network failures are bounded at three attempts and never execute an installer' {
        $root = New-Fixture 'network-failure'
        $script:Attempts = 0
        function Save-OfficialInstaller { $script:Attempts++; throw 'fixture offline' }
        Expect-Failure {Get-VerifiedInstaller $root (New-Spec)} 'after 3 attempts'
        Assert-Equal $script:Attempts 3
        Assert-UserData $root
    }
    Test-Case 'A valid checksum does not bypass an invalid signature or wrong publisher' {
        $root = New-Fixture 'signature'
        $file = Join-Path $root '.cache/downloads/python-3.13.16-amd64.exe'
        Write-FixtureInstaller $file
        function Get-AuthenticodeSignature {
            param([string]$LiteralPath)
            return [PSCustomObject]@{Status = 'Valid'; SignerCertificate = [PSCustomObject]@{Subject = 'CN=Other Publisher, O=Other Publisher, C=US'}}
        }
        Expect-Failure {Get-VerifiedInstaller $root (New-Spec)} 'signature verification failed'
        function Get-AuthenticodeSignature {
            param([string]$LiteralPath)
            return [PSCustomObject]@{Status = 'NotSigned'; SignerCertificate = $null}
        }
        Expect-Failure {Assert-InstallerSignature $file} 'signature verification failed'
        Assert-UserData $root
    }
    Test-Case 'Prepared Python is checked locally with its DLLs before execution; no system install' {
        $root = New-Fixture 'prepared-python'
        $files = @{}
        foreach ($name in @('python.exe', 'python313.dll', 'python3.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
            $relative = 'runtime/windows-x64/python/' + $name
            $path = Join-Path $root $relative
            Write-FixtureInstaller $path
            $files[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $manifest = @{schema = 1; platform = 'win_amd64'; files = $files} | ConvertTo-Json -Depth 5
        [IO.File]::WriteAllText((Join-Path $root 'runtime/windows-x64/bundle.json'), $manifest)
        Assert-Equal (Get-PreparedPython $root) (Join-Path $root 'runtime/windows-x64/python/python.exe')
        function Assert-BootstrapPlatform {}
        function Get-BootstrapSpec { New-Spec }
        function Get-UsablePython { throw 'Prepared Python should be preferred' }
        function Start-PythonInstaller { throw 'Prepared mode must not invoke an installer' }
        Assert-Equal (Ensure-BootstrapPython $root) (Join-Path $root 'runtime/windows-x64/python/python.exe')
        [IO.File]::WriteAllText((Join-Path $root 'runtime/windows-x64/python/python313.dll'), 'corrupt')
        Assert-True ($null -eq (Get-PreparedPython $root)) 'Corrupt prepared Python must not be executed'
        Assert-UserData $root
    }
    Test-Case 'Native discovery validates an existing interpreter without importing app code' {
        $root = New-Fixture 'discovery'
        $script:FixturePython = (Get-Command python, python3 -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
        function Get-RegisteredPythonPaths { return $script:FixturePython }
        $found = Get-UsablePython $root
        Assert-True ($null -ne $found) 'Supported interpreter was not discovered'
        Assert-True (Test-Path -LiteralPath $found -PathType Leaf)
        Assert-UserData $root
    }
    Test-Case 'Existing Python skips installer, lock and downloads' {
        $root = New-Fixture 'existing'
        function Assert-BootstrapPlatform {}
        function Get-BootstrapSpec { New-Spec }
        function Get-UsablePython { return 'existing supported python.exe' }
        function Enter-PythonBootstrapLock { throw 'Unnecessary lock' }
        function Get-VerifiedInstaller { throw 'Unexpected download' }
        function Start-PythonInstaller { throw 'Unexpected installation' }
        Assert-Equal (Ensure-BootstrapPython $root) 'existing supported python.exe'
        Assert-UserData $root
    }
    Test-Case 'A competing launch finishes Python setup, then this launch reuses it' {
        $root = New-Fixture 'competing'
        $script:Discovery = 0; $script:Released = 0
        function Assert-BootstrapPlatform {}
        function Get-BootstrapSpec { New-Spec }
        function Get-UsablePython { $script:Discovery++; if ($script:Discovery -gt 1) { return 'other launch python.exe' }; return $null }
        function Enter-PythonBootstrapLock { return 'fixture mutex' }
        function Exit-PythonBootstrapLock { param($Mutex) Assert-Equal $Mutex 'fixture mutex'; $script:Released++ }
        function Get-VerifiedInstaller { throw 'Unexpected download' }
        Assert-Equal (Ensure-BootstrapPython $root) 'other launch python.exe'
        Assert-Equal $script:Released 1
        Assert-UserData $root
    }
    Test-Case 'Successful installation is checked and the bootstrap lock is released' {
        $root = New-Fixture 'new-python'
        $script:Discovery = 0; $script:Installed = 0; $script:Released = 0
        function Assert-BootstrapPlatform {}
        function Get-BootstrapSpec { New-Spec }
        function Get-UsablePython { $script:Discovery++; if ($script:Discovery -gt 2) { return 'new python.exe' }; return $null }
        function Enter-PythonBootstrapLock { return 'fixture mutex' }
        function Exit-PythonBootstrapLock { $script:Released++ }
        function Get-VerifiedInstaller { return 'verified fixture.exe' }
        function Start-PythonInstaller {
            param([string]$Installer, [string]$Target)
            Assert-Equal $Installer 'verified fixture.exe'
            Assert-Equal $Target (Join-Path $root '.cache/local-tools/python-3.13.16')
            $script:Installed++; return 0
        }
        Assert-Equal (Ensure-BootstrapPython $root) 'new python.exe'
        Assert-Equal $script:Installed 1
        Assert-Equal $script:Released 1
        Assert-UserData $root
    }
    Test-Case 'Cancellation, concurrent MSI, failure and restart codes stop safely with no retry/elevation/reboot' {
        $root = New-Fixture 'installer-errors'
        function Assert-BootstrapPlatform {}
        function Get-BootstrapSpec { New-Spec }
        function Get-UsablePython { return $null }
        function Enter-PythonBootstrapLock { return 'fixture mutex' }
        function Exit-PythonBootstrapLock { $script:Released++ }
        function Get-VerifiedInstaller { return 'verified fixture.exe' }
        function Start-PythonInstaller { $script:Installed++; return $script:ExitCode }
        foreach ($row in @(@(1602, 'cancelled'), @(1223, 'cancelled'), @(1618, 'Another Windows installation'), @(1603, 'failed with Windows Installer code'), @(3010, 'requires a restart'), @(1641, 'requires a restart'))) {
            $script:ExitCode = $row[0]; $script:Installed = 0; $script:Released = 0
            Expect-Failure {Ensure-BootstrapPython $root} $row[1]
            Assert-Equal $script:Installed 1
            Assert-Equal $script:Released 1
        }
        Assert-UserData $root
    }
    Test-Case 'Python MSI flags, paths and child TEMP remain per-user and project-local' {
        $root = New-Fixture 'msi-flags'
        $target = Join-Path $root '.cache/local-tools/python-3.13.16'
        $oldTemp = $env:TEMP; $oldTmp = $env:TMP
        $script:ProcessArguments = @()
        function Start-Process {
            param([string]$FilePath, [string[]]$ArgumentList, [switch]$PassThru, [switch]$NoNewWindow)
            Assert-Equal $FilePath 'fixture installer.exe'
            Assert-True $PassThru
            Assert-True $NoNewWindow
            Assert-Equal $env:TEMP (Join-Path $root '.cache/tmp/python-bootstrap')
            Assert-Equal $env:TMP $env:TEMP
            $script:ProcessArguments = $ArgumentList
            $process = [PSCustomObject]@{ExitCode = 0}
            $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {param($Timeout) if ($Timeout -ne 900000) { throw 'Missing timeout' }; return $true}
            $process | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
            return $process
        }
        Assert-Equal (Start-PythonInstaller 'fixture installer.exe' $target) 0
        foreach ($flag in @('/quiet', '/norestart', 'InstallAllUsers=0', 'Include_launcher=0', 'PrependPath=0', 'AssociateFiles=0', 'Shortcuts=0')) {
            Assert-True ($script:ProcessArguments -contains $flag) ('Missing safe MSI flag: ' + $flag)
        }
        Assert-True ($script:ProcessArguments -contains ('TargetDir="' + $target + '"'))
        Assert-Equal $env:TEMP $oldTemp
        Assert-Equal $env:TMP $oldTmp
        Assert-UserData $root
    }
    Test-Case 'Missing extraction is reported before interpreter installation' {
        $root = New-Fixture 'incomplete'
        function Ensure-BootstrapPython { throw 'Python setup must not be reached' }
        Expect-Failure {Invoke-WindowsBootstrap $root @('--start')} 'Extract ALL files'
        Assert-UserData $root
    }
    Test-Case 'Native project handoff streams output, preserves CLI args and returns only an exit code' {
        $root = New-Fixture 'native-handoff'
        $python = Get-Command python, python3 -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        Assert-True ($null -ne $python) 'This offline test requires an existing Python for a harmless synthetic script'
        $code = "import json, pathlib, sys`npathlib.Path(__file__).with_name('arguments.json').write_text(json.dumps(sys.argv[1:]))`nprint('Fixture output, not an app install', flush=True)`nprint(pathlib.Path(__file__).parent, flush=True)`nprint('Fixture stderr warning', file=sys.stderr)`nsys.exit(7)`n"
        [IO.File]::WriteAllText((Join-Path $root 'install.py'), $code, (New-Object System.Text.UTF8Encoding($false)))
        [IO.Directory]::CreateDirectory((Join-Path $root 'scripts')) | Out-Null
        [IO.File]::WriteAllText((Join-Path $root 'scripts/local_start.py'), '# never executed synthetic fixture')
        function Ensure-BootstrapPython { return $python.Source }
        $oldUtf8 = $env:PYTHONUTF8; $oldIo = $env:PYTHONIOENCODING; $oldEncoding = [Console]::OutputEncoding
        $result = Invoke-WindowsBootstrap $root @('--start', '--port', '3211', '--no-browser')
        Assert-Equal $env:PYTHONUTF8 $oldUtf8
        Assert-Equal $env:PYTHONIOENCODING $oldIo
        Assert-Equal ([Console]::OutputEncoding.WebName) $oldEncoding.WebName
        Assert-True ($result -is [int]) 'Native stdout leaked into the exit-code return pipeline'
        Assert-Equal $result 7
        $arguments = Get-Content -LiteralPath (Join-Path $root 'arguments.json') -Raw | ConvertFrom-Json
        Assert-Equal ($arguments -join '|') '--start|--port|3211|--no-browser'
        Assert-UserData $root
    }
} finally {
    # Delete only this randomly named test-owned root, never the actual project.
    if (Test-Path -LiteralPath $script:TestBase) { Remove-Item -LiteralPath $script:TestBase -Recurse -Force }
}
Write-Host "`nBOOTSTRAP SUMMARY: $script:Passed passed; $script:Failed failed. No real installation/network/provider calls."
if ($script:Failed -gt 0) { exit 1 }
exit 0
