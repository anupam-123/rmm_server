# MCP-RMM Troubleshooting Guide

This guide helps you diagnose and resolve common issues with the MCP-RMM server.

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Installation Issues](#installation-issues)
3. [Authentication Problems](#authentication-problems)
4. [API Connection Issues](#api-connection-issues)
5. [Browser Automation Issues](#browser-automation-issues)
6. [Performance Problems](#performance-problems)
7. [Debugging Tools](#debugging-tools)
8. [Getting Help](#getting-help)

## Quick Diagnostics

### Health Check Script

Run this script to quickly diagnose common issues:

```powershell
# Windows PowerShell
Write-Host "🔍 MCP-RMM Health Check" -ForegroundColor Cyan

# Check Python version
Write-Host "`n1. Python Version:" -ForegroundColor Yellow
python --version

# Check dependencies
Write-Host "`n2. Key Dependencies:" -ForegroundColor Yellow
try { python -c "import fastmcp; print('✅ FastMCP installed')" } catch { Write-Host "❌ FastMCP missing" -ForegroundColor Red }
try { python -c "import playwright; print('✅ Playwright installed')" } catch { Write-Host "❌ Playwright missing" -ForegroundColor Red }
try { python -c "import requests; print('✅ Requests installed')" } catch { Write-Host "❌ Requests missing" -ForegroundColor Red }

# Check environment file
Write-Host "`n3. Configuration:" -ForegroundColor Yellow
if (Test-Path ".env") { Write-Host "✅ .env file exists" } else { Write-Host "❌ .env file missing" -ForegroundColor Red }

# Check token file
Write-Host "`n4. Authentication:" -ForegroundColor Yellow
if (Test-Path "auth_token.json") { Write-Host "✅ Token file exists" } else { Write-Host "⚠️  No token file (run authentication first)" -ForegroundColor Yellow }

# Test module import
Write-Host "`n5. Module Import:" -ForegroundColor Yellow
try { python -c "import auth_mcp_server; print('✅ Main module imports successfully')" } catch { Write-Host "❌ Module import failed" -ForegroundColor Red }
```

### Environment Validation

```powershell
# Check environment variables
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

required_vars = ['AUTH0_LOGIN_URL', 'USERNAME_1', 'PASSWORD_1', 'API_BASE_URL', 'OCP_APIM_SUBSCRIPTION_KEY']
missing = [var for var in required_vars if not os.getenv(var)]

if missing:
    print(f'❌ Missing environment variables: {missing}')
else:
    print('✅ All required environment variables are set')
"
```

## Installation Issues

### Issue: "Python not found"

**Problem:** System cannot find Python executable.

**Solutions:**

1. Install Python 3.11+ from [python.org](https://python.org)
2. Ensure Python is added to PATH during installation
3. Use Python Launcher: `py -3.11` instead of `python`
4. Restart command prompt/PowerShell after installation

**Verification:**

```powershell
python --version
# Should output: Python 3.11.x or higher
```

### Issue: "uv not found"

**Problem:** UV package manager not installed or not in PATH.

**Solutions:**

1. Install uv manually:
   ```powershell
   irm https://astral.sh/uv/install.ps1 | iex
   ```
2. Restart PowerShell to refresh PATH
3. Use pip as fallback:
   ```powershell
   pip install -e .
   ```

### Issue: "Permission denied" during installation

**Problem:** Insufficient permissions for package installation.

**Solutions:**

1. Run PowerShell as Administrator
2. Use user-local installation:
   ```powershell
   pip install --user -e .
   ```
3. Check antivirus software blocking installation

### Issue: "Playwright browsers not installed"

**Problem:** Browser automation fails due to missing browsers.

**Solutions:**

1. Install browsers manually:
   ```powershell
   playwright install firefox
   ```
2. Check available browsers:
   ```powershell
   playwright install --help
   ```
3. Install all browsers:
   ```powershell
   playwright install
   ```

## Authentication Problems

### Issue: "Auth0 login failed"

**Problem:** Cannot complete Auth0 authentication flow.

**Symptoms:**

- Browser hangs on login page
- "Email field not found" errors
- Timeout waiting for login

**Debugging Steps:**

1. **Run with visible browser:**

   ```powershell
   $env:HEADLESS="false"
   python -c "from auth_playwright import AuthTokenExtractor; import asyncio; asyncio.run(AuthTokenExtractor().run())"
   ```

2. **Check credentials:**

   ```powershell
   python -c "
   import os
   from dotenv import load_dotenv
   load_dotenv()
   print('Username:', os.getenv('USERNAME_1'))
   print('Password length:', len(os.getenv('PASSWORD_1', '')) if os.getenv('PASSWORD_1') else 0)
   print('Auth0 URL:', os.getenv('AUTH0_LOGIN_URL'))
   "
   ```

3. **Increase timeouts:**

   ```env
   DASHBOARD_TIMEOUT=60000
   ELEMENT_TIMEOUT=30000
   SLOW_MO=3000
   ```

4. **Check for CAPTCHA or MFA:**
   - Login manually to check for additional security measures
   - Contact administrator to temporarily disable MFA for automation

**Common Solutions:**

- Update selectors if Auth0 UI changed
- Clear browser cache and cookies
- Check network connectivity
- Verify Auth0 domain is correct

### Issue: "Sharp-Start selection failed"

**Problem:** Cannot find or click Sharp-Start SSO button.

**Debugging:**

1. **Manual verification:**

   - Login manually and note the exact button text
   - Check if button requires scrolling

2. **Update selectors:**

   - Modify `auth_playwright.py` selectors if UI changed
   - Add new fallback selectors

3. **Check page load timing:**
   ```env
   SLOW_MO=5000  # Increase delay between actions
   ```

### Issue: "JWT token not found"

**Problem:** Browser automation completes but no token extracted.

**Debugging Steps:**

1. **Check token sources:**

   ```javascript
   // Run in browser console after login
   console.log("LocalStorage:", Object.keys(localStorage));
   console.log("SessionStorage:", Object.keys(sessionStorage));
   console.log("Cookies:", document.cookie);
   ```

2. **Monitor network requests:**

   - Open browser DevTools
   - Look for requests containing Authorization headers
   - Note the API endpoints making authenticated calls

3. **Manual token extraction:**
   ```powershell
   # Run with debugging
   $env:HEADLESS="false"
   $env:SLOW_MO="5000"
   python -c "from auth_playwright import AuthTokenExtractor; import asyncio; asyncio.run(AuthTokenExtractor().run())"
   ```

**Solutions:**

- Update token extraction logic for new storage locations
- Add additional API endpoints to trigger token interception
- Implement fallback token extraction methods

### Issue: "Token expired" errors

**Problem:** JWT tokens expire too quickly.

**Solutions:**

1. **Check token expiration:**

   ```python
   import jwt
   import json

   with open('auth_token.json', 'r') as f:
       data = json.load(f)
       token = data['token_extraction']['token']

   # Decode without verification
   payload = jwt.decode(token, options={"verify_signature": False})
   print(f"Token expires at: {payload.get('exp')}")
   ```

2. **Implement automatic refresh:**

   - The system already checks token expiration
   - Ensure `extract_auth_token()` is called before API operations

3. **Extend token lifetime:**
   - Contact administrator to increase token expiration time
   - Implement refresh token mechanism if available

## API Connection Issues

### Issue: "API returned 401 Unauthorized"

**Problem:** API rejects requests with valid-looking tokens.

**Debugging:**

1. **Verify API endpoint:**

   ```python
   import os
   from dotenv import load_dotenv
   load_dotenv()
   print('API Base URL:', os.getenv('API_BASE_URL'))
   print('Subscription Key:', os.getenv('OCP_APIM_SUBSCRIPTION_KEY')[:10] + '...')
   ```

2. **Test API manually:**
   ```powershell
   # Using curl or Invoke-RestMethod
   $headers = @{
       'Authorization' = 'Bearer YOUR_TOKEN_HERE'
       'Ocp-Apim-Subscription-Key' = 'YOUR_KEY_HERE'
       'Content-Type' = 'application/json'
   }
   Invoke-RestMethod -Uri 'https://alt-rmm-api.sharpb2bcloud.com/api/endpoint' -Headers $headers
   ```

**Solutions:**

- Verify subscription key is correct and active
- Check API endpoint URLs
- Ensure token has required permissions/scopes
- Contact API administrator for access verification

### Issue: "Connection timeout" or "Network errors"

**Problem:** Cannot reach Sharp B2B Cloud APIs.

**Debugging:**

1. **Test connectivity:**

   ```powershell
   Test-NetConnection -ComputerName alt-rmm-api.sharpb2bcloud.com -Port 443
   ```

2. **Check proxy settings:**

   ```python
   import requests

   # Test with proxy if needed
   proxies = {
       'http': 'http://proxy.company.com:8080',
       'https': 'https://proxy.company.com:8080'
   }

   response = requests.get('https://alt-rmm-api.sharpb2bcloud.com', proxies=proxies)
   ```

**Solutions:**

- Configure corporate proxy settings
- Check firewall rules
- Verify DNS resolution
- Test from different network

### Issue: "Invalid device ID format" errors

**Problem:** Device IDs don't match expected format.

**Understanding Device IDs:**

```python
import base64

# Device ID format: mn=<base64_model>:sn=<base64_serial>
device_id = "mn=U2hhcnA=:sn=MTIzNDU2Nzg="

# Decode to verify
model_part = device_id.split(':')[0].replace('mn=', '')
serial_part = device_id.split(':')[1].replace('sn=', '')

model = base64.b64decode(model_part).decode('utf-8')
serial = base64.b64decode(serial_part).decode('utf-8')

print(f"Model: {model}, Serial: {serial}")
```

**Solutions:**

- Use device IDs exactly as returned by `list_devices()`
- Don't manually construct device IDs
- Verify base64 encoding if constructing manually

## Browser Automation Issues

### Issue: "Browser launch failed"

**Problem:** Playwright cannot start browser.

**Debugging:**

1. **Check browser installation:**

   ```powershell
   playwright install --help
   ls ~/.cache/ms-playwright  # Linux/Mac
   dir %USERPROFILE%\AppData\Local\ms-playwright  # Windows
   ```

2. **Test browser manually:**
   ```powershell
   playwright codegen google.com
   ```

**Solutions:**

- Reinstall browsers: `playwright install --force`
- Clear browser cache
- Run with different browser: modify `auth_playwright.py` to use `chromium`
- Check antivirus blocking browser execution

### Issue: "Page load timeout"

**Problem:** Web pages don't load within timeout periods.

**Solutions:**

1. **Increase timeouts:**

   ```env
   DASHBOARD_TIMEOUT=90000
   ELEMENT_TIMEOUT=60000
   ```

2. **Check network speed:**

   ```powershell
   # Test page load manually
   Measure-Command { Invoke-WebRequest https://your-auth0-domain.auth0.com }
   ```

3. **Run in slow motion:**
   ```env
   SLOW_MO=5000
   HEADLESS=false
   ```

### Issue: "Element not found" errors

**Problem:** Cannot find expected page elements.

**Debugging:**

1. **Take screenshots:**

   - Screenshots are automatically saved in error cases
   - Check `debug_auth0_form.png` and `debug_error.png`

2. **Update selectors:**

   ```python
   # In auth_playwright.py, update selectors if UI changed
   self.selectors = {
       'auth0_email': 'input[type="email"]',  # More generic selector
       # ... add more fallback selectors
   }
   ```

3. **Manual testing:**
   - Login manually and inspect element selectors
   - Use browser DevTools to find reliable selectors

## Performance Problems

### Issue: "Slow authentication"

**Problem:** Token extraction takes too long.

**Optimization:**

1. **Reduce browser startup time:**

   ```env
   HEADLESS=true  # Faster than visible browser
   SLOW_MO=500    # Reduce delays
   ```

2. **Optimize selectors:**

   - Use more specific CSS selectors
   - Avoid `wait_for_timeout()` when possible

3. **Cache tokens:**
   - System already validates existing tokens
   - Ensure token storage is working properly

### Issue: "High memory usage"

**Problem:** Browser automation uses too much memory.

**Solutions:**

1. **Browser configuration:**

   ```python
   # In auth_playwright.py, add browser args:
   browser = await p.firefox.launch(
       headless=self.headless,
       args=['--memory-pressure-off', '--max_old_space_size=512']
   )
   ```

2. **Close browsers properly:**
   - Ensure browser.close() is called in finally blocks
   - Monitor for zombie browser processes

### Issue: "API rate limiting"

**Problem:** Too many API requests cause rate limit errors.

**Solutions:**

1. **Implement backoff:**

   ```python
   import asyncio
   import random

   async def api_call_with_backoff(func, *args, **kwargs):
       for attempt in range(3):
           try:
               return await func(*args, **kwargs)
           except RateLimitError:
               wait_time = (2 ** attempt) + random.uniform(0, 1)
               await asyncio.sleep(wait_time)
       raise Exception("Max retries exceeded")
   ```

2. **Batch operations:**
   ```python
   # Group multiple devices in single API calls
   await configure_ota_mode(
       device_ids=all_device_ids,  # Instead of individual calls
       ota_mode="auto"
   )
   ```

## Debugging Tools

### Enable Debug Logging

```python
import logging

# Set debug level
logging.basicConfig(level=logging.DEBUG)

# Or for specific modules
logging.getLogger('auth_mcp_server').setLevel(logging.DEBUG)
logging.getLogger('auth_playwright').setLevel(logging.DEBUG)
```

### Browser DevTools

When running with `HEADLESS=false`:

1. Right-click → "Inspect Element"
2. Go to Network tab to monitor API calls
3. Check Console for JavaScript errors
4. Use Application tab to inspect storage

### Token Inspection

```python
import jwt
import json
from datetime import datetime

def inspect_token(token_file='auth_token.json'):
    with open(token_file, 'r') as f:
        data = json.load(f)

    token = data.get('token_extraction', {}).get('token')
    if not token:
        print("No token found")
        return

    # Decode payload
    payload = jwt.decode(token, options={"verify_signature": False})

    print("Token Information:")
    print(f"Issuer: {payload.get('iss')}")
    print(f"Subject: {payload.get('sub')}")
    print(f"Audience: {payload.get('aud')}")
    print(f"Expires: {datetime.fromtimestamp(payload.get('exp', 0))}")
    print(f"Group ID: {payload.get('sspTenantId')}")

inspect_token()
```

### API Testing Script

```python
import asyncio
from auth_mcp_server import token_manager

async def test_api_endpoints():
    """Test various API endpoints to identify issues."""

    # Test token extraction
    print("Testing token extraction...")
    token_result = await token_manager.extract_auth_token()
    print(f"Token extraction: {'✅' if token_result['success'] else '❌'}")

    if not token_result['success']:
        print(f"Error: {token_result.get('error')}")
        return

    # Test device listing
    print("Testing device listing...")
    from auth_mcp_server import list_devices
    devices_result = await list_devices(page_size=5)
    print(f"Device listing: {'✅' if devices_result['success'] else '❌'}")

    if devices_result['success']:
        print(f"Found {len(devices_result['devices'])} devices")
    else:
        print(f"Error: {devices_result.get('error')}")

# Run test
asyncio.run(test_api_endpoints())
```

## Getting Help

### Before Asking for Help

1. **Run diagnostics:**

   - Use the health check script above
   - Check logs for error messages
   - Try with visible browser (`HEADLESS=false`)

2. **Gather information:**
   - Python version: `python --version`
   - Operating system and version
   - Error messages (full stack traces)
   - Screenshots of browser automation issues

### Where to Get Help

1. **GitHub Issues:**

   - [Create an issue](https://github.com/anupam-123/AI--based-firmware-upgradation-system/issues)
   - Include diagnostic information
   - Attach relevant screenshots

2. **Documentation:**
   - README.md for setup instructions
   - API_DOCUMENTATION.md for API reference
   - This troubleshooting guide

### Creating Good Bug Reports

Include the following information:

```markdown
## Environment

- OS: Windows 11 / macOS 13 / Ubuntu 22.04
- Python version: 3.11.5
- Package manager: uv / pip
- Browser: Firefox (via Playwright)

## Issue Description

Brief description of the problem

## Steps to Reproduce

1. Step one
2. Step two
3. Error occurs

## Expected Behavior

What should happen

## Actual Behavior

What actually happens

## Error Messages
```

Paste full error messages and stack traces here

```

## Additional Context
- Screenshots
- Log files
- Configuration files (redacted)
```

### Emergency Recovery

If the system is completely broken:

1. **Clean reinstall:**

   ```powershell
   # Remove existing installation
   pip uninstall mcp-rmm

   # Clear cache
   Remove-Item -Recurse -Force __pycache__
   Remove-Item auth_token.json

   # Reinstall
   uv sync
   uv run playwright install firefox
   ```

2. **Reset configuration:**

   ```powershell
   # Backup current config
   Copy-Item .env .env.backup

   # Use template
   Copy-Item .env.example .env
   # Edit .env with correct values
   ```

3. **Manual token extraction:**
   - Login manually to Sharp B2B Cloud
   - Extract JWT token from browser DevTools
   - Create minimal auth_token.json file
   - Test API calls manually

---

For additional support, contact the development team or create an issue on GitHub with detailed diagnostic information.
