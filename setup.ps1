# MCP-RMM Windows Setup Script
# PowerShell script to automate installation on Windows

param(
    [switch]$SkipUv,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

function Write-Status {
    param($Message, $Type = "Info")
    
    $timestamp = Get-Date -Format "HH:mm:ss"
    switch ($Type) {
        "Success" { Write-Host "[$timestamp] ✅ $Message" -ForegroundColor Green }
        "Error"   { Write-Host "[$timestamp] ❌ $Message" -ForegroundColor Red }
        "Warning" { Write-Host "[$timestamp] ⚠️  $Message" -ForegroundColor Yellow }
        "Info"    { Write-Host "[$timestamp] 🔄 $Message" -ForegroundColor Cyan }
        default   { Write-Host "[$timestamp] $Message" }
    }
}

function Test-Command {
    param($Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

function Invoke-SafeCommand {
    param($Command, $Description, $IgnoreError = $false)
    
    Write-Status $Description "Info"
    
    try {
        if ($Verbose) {
            Write-Host "Executing: $Command" -ForegroundColor Gray
        }
        
        $result = Invoke-Expression $Command
        Write-Status "$Description completed successfully" "Success"
        return $true
    }
    catch {
        if ($IgnoreError) {
            Write-Status "$Description failed (ignored): $($_.Exception.Message)" "Warning"
            return $false
        }
        else {
            Write-Status "$Description failed: $($_.Exception.Message)" "Error"
            throw
        }
    }
}

function Test-PythonVersion {
    Write-Status "Checking Python version..." "Info"
    
    if (-not (Test-Command "python")) {
        Write-Status "Python not found. Please install Python 3.11+ from https://python.org" "Error"
        return $false
    }
    
    $pythonVersion = python --version 2>&1
    Write-Host "Found: $pythonVersion"
    
    # Extract version numbers
    if ($pythonVersion -match "Python (\d+)\.(\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        
        if (($major -eq 3 -and $minor -ge 11) -or $major -gt 3) {
            Write-Status "Python version is compatible" "Success"
            return $true
        }
    }
    
    Write-Status "Python 3.11+ required. Found: $pythonVersion" "Error"
    return $false
}

function Install-Uv {
    if ($SkipUv) {
        Write-Status "Skipping uv installation as requested" "Warning"
        return $false
    }
    
    Write-Status "Checking for uv package manager..." "Info"
    
    if (Test-Command "uv") {
        Write-Status "uv package manager already installed" "Success"
        return $true
    }
    
    Write-Status "Installing uv package manager..." "Info"
    
    try {
        irm https://astral.sh/uv/install.ps1 | iex
        
        # Refresh PATH
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
        
        if (Test-Command "uv") {
            Write-Status "uv installed successfully" "Success"
            return $true
        }
        else {
            Write-Status "uv installation completed but command not found. Try restarting PowerShell." "Warning"
            return $false
        }
    }
    catch {
        Write-Status "Failed to install uv: $($_.Exception.Message)" "Error"
        return $false
    }
}

function Install-Dependencies {
    Write-Status "Installing Python dependencies..." "Info"
    
    # Try uv first
    if (Test-Command "uv") {
        if (Invoke-SafeCommand "uv sync" "Installing dependencies with uv" $true) {
            return $true
        }
        Write-Status "uv sync failed, falling back to pip..." "Warning"
    }
    
    # Fallback to pip
    return Invoke-SafeCommand "pip install -e ." "Installing dependencies with pip"
}

function Install-PlaywrightBrowsers {
    Write-Status "Installing Playwright browsers..." "Info"
    
    if (Test-Command "uv") {
        return Invoke-SafeCommand "uv run playwright install firefox" "Installing Firefox browser with uv"
    }
    else {
        return Invoke-SafeCommand "playwright install firefox" "Installing Firefox browser with pip"
    }
}

function Setup-EnvironmentFile {
    Write-Status "Setting up environment configuration..." "Info"
    
    if (Test-Path ".env.example") {
        if (-not (Test-Path ".env")) {
            Copy-Item ".env.example" ".env"
            Write-Status ".env file created from template" "Success"
            Write-Status "Please edit .env file with your actual configuration values" "Info"
        }
        else {
            Write-Status ".env file already exists" "Info"
        }
        return $true
    }
    else {
        Write-Status ".env.example template not found" "Error"
        return $false
    }
}

function Test-Installation {
    Write-Status "Verifying installation..." "Info"
    
    try {
        if (Test-Command "uv") {
            $command = 'uv run python -c "import auth_mcp_server; print(\"✅ MCP server module imported successfully\")"'
        }
        else {
            $command = 'python -c "import auth_mcp_server; print(\"✅ MCP server module imported successfully\")"'
        }
        
        $result = Invoke-Expression $command
        Write-Host $result
        Write-Status "Installation verification successful" "Success"
        return $true
    }
    catch {
        Write-Status "Module import failed: $($_.Exception.Message)" "Error"
        return $false
    }
}

function Show-NextSteps {
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host "🎉 MCP-RMM Setup Complete!" -ForegroundColor Green
    Write-Host "=" * 60 -ForegroundColor Green
    
    Write-Host ""
    Write-Host "📝 Next Steps:" -ForegroundColor Yellow
    Write-Host "1. Edit the .env file with your actual configuration:"
    Write-Host "   - Auth0 login URL and credentials"
    Write-Host "   - Sharp B2B Cloud API endpoints" 
    Write-Host "   - API subscription keys"
    
    Write-Host ""
    Write-Host "2. Test the authentication:" -ForegroundColor Yellow
    if (Test-Command "uv") {
        Write-Host "   uv run python -c `"from auth_playwright import AuthTokenExtractor; import asyncio; asyncio.run(AuthTokenExtractor().run())`""
    }
    else {
        Write-Host "   python -c `"from auth_playwright import AuthTokenExtractor; import asyncio; asyncio.run(AuthTokenExtractor().run())`""
    }
    
    Write-Host ""
    Write-Host "3. Start the MCP server:" -ForegroundColor Yellow
    if (Test-Command "uv") {
        Write-Host "   uv run python server.py"
    }
    else {
        Write-Host "   python server.py"
    }
    
    Write-Host ""
    Write-Host "📚 For more information, see README.md" -ForegroundColor Cyan
    Write-Host "🐛 For issues, visit: https://github.com/anupam-123/AI--based-firmware-upgradation-system/issues" -ForegroundColor Cyan
}

# Main execution
try {
    Write-Host "🚀 MCP-RMM Windows Setup Script" -ForegroundColor Magenta
    Write-Host "=" * 40 -ForegroundColor Magenta
    
    # Check Python version
    if (-not (Test-PythonVersion)) {
        exit 1
    }
    
    # Install uv if requested
    $uvAvailable = Install-Uv
    if (-not $uvAvailable -and -not $SkipUv) {
        Write-Status "Continuing without uv, using pip instead..." "Warning"
    }
    
    # Install dependencies
    if (-not (Install-Dependencies)) {
        Write-Status "Failed to install dependencies" "Error"
        exit 1
    }
    
    # Install Playwright browsers
    if (-not (Install-PlaywrightBrowsers)) {
        Write-Status "Failed to install Playwright browsers" "Error"
        exit 1
    }
    
    # Setup environment file
    if (-not (Setup-EnvironmentFile)) {
        Write-Status "Failed to setup environment file" "Error"
        exit 1
    }
    
    # Verify installation
    if (-not (Test-Installation)) {
        Write-Status "Installation verification failed" "Error"
        exit 1
    }
    
    # Show next steps
    Show-NextSteps
    
    Write-Host ""
    Write-Status "Setup completed successfully! 🎉" "Success"
}
catch {
    Write-Status "Setup failed: $($_.Exception.Message)" "Error"
    Write-Host ""
    Write-Host "For troubleshooting help, see README.md or create an issue at:" -ForegroundColor Yellow
    Write-Host "https://github.com/anupam-123/AI--based-firmware-upgradation-system/issues"
    exit 1
}
