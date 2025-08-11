#!/usr/bin/env python3
"""
MCP-RMM Setup Script
Automates the installation and configuration of the MCP-RMM server.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_command(command, description, check=True):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=check, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
            return True
        else:
            print(f"❌ {description} failed: {result.stderr}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        return False


def check_python_version():
    """Check if Python version meets requirements."""
    print("🔍 Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 11:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} is compatible")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} is not compatible. Python 3.11+ required.")
        return False


def check_uv_installed():
    """Check if uv package manager is installed."""
    print("🔍 Checking for uv package manager...")
    if shutil.which("uv"):
        print("✅ uv package manager found")
        return True
    else:
        print("❌ uv package manager not found")
        print("📝 Installing uv package manager...")
        if os.name == 'nt':  # Windows
            return run_command("powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"", "Installing uv on Windows")
        else:  # Unix-like
            return run_command("curl -LsSf https://astral.sh/uv/install.sh | sh", "Installing uv on Unix")


def install_dependencies():
    """Install Python dependencies."""
    print("📦 Installing Python dependencies...")
    
    # Try uv first, fallback to pip
    if shutil.which("uv"):
        success = run_command("uv sync", "Installing dependencies with uv")
        if success:
            return True
        print("🔄 uv sync failed, trying pip...")
    
    # Fallback to pip
    return run_command("pip install -e .", "Installing dependencies with pip")


def install_playwright_browsers():
    """Install Playwright browsers."""
    print("🌐 Installing Playwright browsers...")
    
    if shutil.which("uv"):
        return run_command("uv run playwright install firefox", "Installing Firefox browser with uv")
    else:
        return run_command("playwright install firefox", "Installing Firefox browser with pip")


def setup_environment_file():
    """Set up environment configuration file."""
    print("⚙️  Setting up environment configuration...")
    
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if env_example.exists():
        if not env_file.exists():
            print("📝 Creating .env file from template...")
            shutil.copy(env_example, env_file)
            print("✅ .env file created")
            print("📝 Please edit .env file with your actual configuration values")
            return True
        else:
            print("ℹ️  .env file already exists")
            return True
    else:
        print("❌ .env.example template not found")
        return False


def verify_installation():
    """Verify the installation is working."""
    print("🧪 Verifying installation...")
    
    # Check if the main module can be imported
    try:
        if shutil.which("uv"):
            result = subprocess.run(
                "uv run python -c \"import auth_mcp_server; print('✅ MCP server module imported successfully')\"",
                shell=True, check=True, capture_output=True, text=True
            )
        else:
            result = subprocess.run(
                "python -c \"import auth_mcp_server; print('✅ MCP server module imported successfully')\"",
                shell=True, check=True, capture_output=True, text=True
            )
        
        print(result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Module import failed: {e}")
        return False


def print_next_steps():
    """Print next steps for the user."""
    print("\n" + "="*60)
    print("🎉 MCP-RMM Setup Complete!")
    print("="*60)
    
    print("\n📝 Next Steps:")
    print("1. Edit the .env file with your actual configuration:")
    print("   - Auth0 login URL and credentials")
    print("   - Sharp B2B Cloud API endpoints")
    print("   - API subscription keys")
    
    print("\n2. Test the authentication:")
    if shutil.which("uv"):
        print("   uv run python -c \"from auth_playwright import AuthTokenExtractor; import asyncio; asyncio.run(AuthTokenExtractor().run())\"")
    else:
        print("   python -c \"from auth_playwright import AuthTokenExtractor; import asyncio; asyncio.run(AuthTokenExtractor().run())\"")
    
    print("\n3. Start the MCP server:")
    if shutil.which("uv"):
        print("   uv run python server.py")
    else:
        print("   python server.py")
    
    print("\n📚 For more information, see README.md")
    print("🐛 For issues, visit: https://github.com/anupam-123/AI--based-firmware-upgradation-system/issues")


def main():
    """Main setup function."""
    print("🚀 MCP-RMM Setup Script")
    print("="*40)
    
    # Check prerequisites
    if not check_python_version():
        sys.exit(1)
    
    # Install uv if needed
    if not check_uv_installed():
        print("⚠️  Continuing without uv, using pip instead...")
    
    # Install dependencies
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        sys.exit(1)
    
    # Install Playwright browsers
    if not install_playwright_browsers():
        print("❌ Failed to install Playwright browsers")
        sys.exit(1)
    
    # Setup environment file
    if not setup_environment_file():
        print("❌ Failed to setup environment file")
        sys.exit(1)
    
    # Verify installation
    if not verify_installation():
        print("❌ Installation verification failed")
        sys.exit(1)
    
    # Print next steps
    print_next_steps()


if __name__ == "__main__":
    main()
