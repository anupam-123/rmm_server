"""
Optimized Playwright script to extract JWT token from Auth0 login and store in JSON file.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from playwright.async_api import async_playwright, Page, BrowserContext
import requests
from dotenv import load_dotenv
import logging


# Configure root logger for this module
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def is_jwt_expired(token: str) -> bool:
    """Check if a JWT token is expired."""
    import base64
    import time
    try:
        payload = token.split('.')[1]
        # Pad base64 string
        padding = '=' * (-len(payload) % 4)
        payload += padding
        decoded = base64.urlsafe_b64decode(payload)
        import json
        payload_json = json.loads(decoded)
        exp = payload_json.get('exp')
        if exp is None:
            return True
        now = int(time.time())
        return now >= exp
    except Exception as e:
        return True

def get_stored_token(token_file: str) -> str:
    """Read the JWT token from the token file if it exists and is valid."""
    import os
    if not os.path.exists(token_file):
        return None
    try:
        with open(token_file, 'r') as f:
            data = json.load(f)
            token = data.get('token_extraction', {}).get('token')
            if token:
                return token
    except Exception:
        return None
    return None

class AuthTokenExtractor:
    """Handles Auth0 authentication flow and JWT token extraction."""
    
    def __init__(self):
        self.login_url = os.getenv('AUTH0_LOGIN_URL')
        self.username = os.getenv('USERNAME_1')
        logger.debug("Loaded username from .env: '%s'", self.username)
        # self.password = "$harp123"
        self.password = os.getenv('PASSWORD_1')
        logger.debug("Loaded password from .env: '%s'", self.password)
        self.api_base_url = os.getenv('API_BASE_URL')
        self.tenant_endpoint = os.getenv('TENANT_LIST_ENDPOINT')
        self.api_url = f"{self.api_base_url}{self.tenant_endpoint}"
        self.token_file = Path(os.getenv('TOKEN_FILE', 'auth_token.json'))
        
        # Debug: Print loaded credentials (removed emoji)
        logger.debug("Loaded username from .env: '%s'", self.username)
        logger.debug("Loaded password from .env: '%s'", self.password)
        
        # Timeouts
        print("DASHBOARD_TIMEOUT:", os.getenv('DASHBOARD_TIMEOUT', 40000))
        self.dashboard_timeout = int(os.getenv('DASHBOARD_TIMEOUT', 40000))
        self.element_timeout = int(os.getenv('ELEMENT_TIMEOUT', 40000))
        self.api_trigger_timeout = int(os.getenv('API_TRIGGER_TIMEOUT', 40000))
        
        # Browser config
        self.headless = os.getenv('HEADLESS').lower() == 'true'
        self.slow_mo = int(os.getenv('SLOW_MO', 1500))
        self.viewport_width = int(os.getenv('VIEWPORT_WIDTH', 1920))
        self.viewport_height = int(os.getenv('VIEWPORT_HEIGHT', 1080))
        
        # Selectors
        self._init_selectors()
        
        # Token storage
        self.intercepted_token: Optional[str] = None

    def _init_selectors(self):
        """Initialize all CSS selectors used in the authentication flow."""
        self.selectors = {
            'auth0_email': 'input[type="email"][id="1-email"][inputmode="email"][name="email"]',
            'auth0_email_fallback': [
                '.auth0-lock-input-email input',
                '.auth0-lock-input input[type="email"]',
                'input[type="email"]',
                '.auth0-lock-input input',
                'input[placeholder*="email"]',
                'input[name="email"]',
                'input[name="username"]'
            ],
            'auth0_continue': [
                '.auth0-lock-submit',
                'button[type="submit"]',
                '.auth0-lock-submit-button',
                'button:has-text("Continue")',
                'button:has-text("Log In")',
                '.auth0-lock .auth0-lock-widget button'
            ],
            'sharp_start_button': 'a.auth0-lock-social-button.auth0-lock-social-big-button[data-provider="oauth2"]',
            'sharp_start_fallback': [
                'button:has-text("Sharp-Start")',
                'button:has-text("Sign in with Sharp-Start")',
                '.auth0-lock-social-button',
                '.auth0-lock-social-buttons button',
                '[data-provider*="sharp"]',
                '[data-provider*="saml"]',
                'button[title*="Sharp"]',
                '.auth0-lock .auth0-lock-social-buttons .auth0-lock-social-button'
            ],
            'sharp_username': 'input[name="dnn$ctr752$CustomLogin_View$txtUsername"]',
            'sharp_password': 'input[name="dnn$ctr752$CustomLogin_View$txtPassword"]',
            'sharp_submit': 'input[type="submit"][name="dnn$ctr752$CustomLogin_View$cmdLogin"]',
            'api_triggers': [
                'button:has-text("Refresh")',
                'button:has-text("Reload")',
                '.refresh-button',
                '.reload-button',
                '[data-testid*="refresh"]',
                'a[href*="dashboard"]',
                'a[href*="tenant"]',
                '.nav-link',
                '.menu-item',
                '.dashboard-card',
                '.tenant-list',
                '.data-grid'
            ]
        }

    def _setup_network_interceptors(self, page: Page) -> None:
        """Set up network request/response interceptors for token capture."""
        def handle_request(request):
            if self.api_url in request.url:
                auth_header = request.headers.get('authorization', '')
                if auth_header.startswith('Bearer '):
                    self.intercepted_token = auth_header.replace('Bearer ', '')
                    logger.info(f"JWT TOKEN FOUND in request to {self.api_url}")
                    logger.debug(f"Authorization header: Bearer {self.intercepted_token[:50]}...")

        def handle_response(response):
            if self.api_url in response.url:
                logger.info(f"Response from {self.api_url}")
            
            # Capture Bearer tokens from any response
            auth_header = response.headers.get('authorization', '')
            if auth_header.startswith('Bearer ') and not self.intercepted_token:
                self.intercepted_token = auth_header.replace('Bearer ', '')
                logger.info(f"Token intercepted from response ({response.url}): {self.intercepted_token[:50]}...")
            
        page.on('request', handle_request)
        page.on('response', handle_response)

    async def _fill_element(self, page: Page, selector: str, value: str, field_name: str) -> bool:
        """Fill a form element with value."""
        try:
            await page.wait_for_selector(selector, state='visible', timeout=self.element_timeout)
            await page.fill(selector, value)
            
            # Verify the value was filled
            filled_value = await page.input_value(selector)
            if filled_value == value:
                logger.info(f"{field_name} filled successfully")
                return True
            else:
                logger.warning(f"Value verification failed for {field_name}")
                return False
        except Exception as e:
            logger.error(f"Failed to fill {field_name}: {e}")
            return False

    async def _click_element(self, page: Page, selector: str, description: str = "") -> bool:
        """Click an element with error handling."""
        try:
            await page.wait_for_selector(selector, state='visible', timeout=5000)
            await page.locator(selector).scroll_into_view_if_needed()
            await page.click(selector)
            logger.info(f"Successfully clicked {description or selector}")
            return True
        except Exception as e:
            logger.error(f"Failed to click {description or selector}: {e}")
            return False

    async def _try_selectors(self, page: Page, selectors: List[str], action: str, **kwargs) -> bool:
        """Try multiple selectors for the same action."""
        for selector in selectors:
            try:
                if action == "click":
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.click()
                        logger.info(f"Successfully clicked using selector: {selector}")
                        return True
                elif action == "fill":
                    await page.wait_for_selector(selector, state='visible', timeout=5000)
                    await page.fill(selector, kwargs['value'])
                    filled_value = await page.input_value(selector)
                    if filled_value == kwargs['value']:
                        logger.info(f"Successfully filled {kwargs.get('field_name', 'field')} using: {selector}")
                        return True
            except Exception as e:
                logger.warning(f"Failed with selector {selector}: {e}")
                continue
        return False

    async def _handle_auth0_login(self, page: Page) -> bool:
        """Handle Auth0 login form."""
        logger.info("Step 2: Handling Auth0 login form...")
        await page.wait_for_timeout(3000)
        logger.info("self.username: %s", self.username)
        # Fill email field
        if not await self._fill_element(page, self.selectors['auth0_email'], self.username, "Email"):
            if not await self._try_selectors(page, self.selectors['auth0_email_fallback'], 
                                        "fill", value=self.username, field_name="Email"):
                await page.screenshot(path='debug_auth0_form.png')
                return False
        
        # Click continue button
        await page.wait_for_timeout(1000)
        if not await self._try_selectors(page, self.selectors['auth0_continue'], "click"):
            logger.warning("No continue button found, proceeding...")
        else:
            await page.wait_for_timeout(3000)
        
        return True

    async def _handle_sharp_start_selection(self, page: Page) -> bool:
        """Handle Sharp-Start provider selection."""
        logger.info("Step 3: Looking for Sharp-Start button...")
        await page.wait_for_timeout(2000)
        
        # Try exact Sharp-Start selector
        try:
            await page.wait_for_selector(self.selectors['sharp_start_button'], state='visible', timeout=self.element_timeout)
            element = await page.query_selector(self.selectors['sharp_start_button'])
            if element:
                text_content = await element.text_content()
                if text_content and 'sharp-start' in text_content.lower():
                    await element.click()
                    logger.info(f"Clicked Sharp-Start button: {text_content}")
                    return True
        except Exception as e:
            logger.warning(f"Exact Sharp-Start selector failed: {e}")
        
        # Try fallback selectors
        for selector in self.selectors['sharp_start_fallback']:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    text_content = await element.text_content()
                    is_visible = await element.is_visible()
                    if is_visible and text_content and ('sharp' in text_content.lower() or 'start' in text_content.lower()):
                        await element.click()
                        logger.info(f"Clicked provider button: {text_content}")
                        return True
            except Exception:
                continue
        
        return False

    async def _handle_sharp_login(self, page: Page) -> bool:
        """Handle Sharp login form."""
        logger.info("Step 4: Handling Sharp login form...")
        await page.wait_for_timeout(5000)
        
        # Wait for form to appear
        try:
            await page.wait_for_selector(self.selectors['sharp_username'], timeout=15000)
        except:
            logger.error("Sharp login form timeout")
            return False
        
        # Fill credentials
        if not await self._fill_element(page, self.selectors['sharp_username'], self.username, "Username"):
            return False
        
        if not await self._fill_element(page, self.selectors['sharp_password'], self.password, "Password"):
            return False
        
        # Submit form
        if not await self._click_element(page, self.selectors['sharp_submit'], "Submit button"):
            return False
        
        return True

    async def _wait_for_dashboard(self, page: Page) -> bool:
        """Wait for successful login and dashboard redirect."""
        logger.info(f"Step 5: Waiting for dashboard redirect ({self.dashboard_timeout/1000} second timeout)...")
        try:
            await page.wait_for_url(['**/callback*', '**/dashboard*', '**/manage*', '*smartoffice*'], 
                                timeout=self.dashboard_timeout)
        except:
            await page.wait_for_timeout(50000)
            current_url = page.url
            logger.info(f"Current URL after timeout: {current_url}")
            if 'auth0.com' in current_url:
                return False
        
        logger.info(f"Login successful! Current URL: {page.url}")
        return True

    async def _extract_token_from_storage(self, page: Page) -> Optional[str]:
        """Extract JWT token from browser storage."""
        try:
            token = await page.evaluate("""
                () => {
                    const storages = [localStorage, sessionStorage];
                    for (let storage of storages) {
                        for (let i = 0; i < storage.length; i++) {
                            const key = storage.key(i);
                            const value = storage.getItem(key);
                            
                            if (value && value.startsWith('eyJ')) {
                                return value;
                            }
                            
                            try {
                                const parsed = JSON.parse(value);
                                if (parsed.access_token && parsed.access_token.startsWith('eyJ')) {
                                    return parsed.access_token;
                                }
                                if (parsed.token && parsed.token.startsWith('eyJ')) {
                                    return parsed.token;
                                }
                            } catch (e) {}
                            
                            if (value && value.includes('eyJ')) {
                                const match = value.match(/eyJ[A-Za-z0-9-_=]+\\.eyJ[A-Za-z0-9-_=]+\\.[A-Za-z0-9-_.+/=]*/);
                                if (match) return match[0];
                            }
                        }
                    }
                    return null;
                }
            """)
            if token:
                logger.info(f"JWT token found in browser storage: {token[:50]}...")
            return token
        except Exception as e:
            logger.error(f"Error accessing storage: {e}")
            return None

    async def _extract_token_from_cookies(self, context: BrowserContext) -> Optional[str]:
        """Extract JWT token from cookies."""
        try:
            cookies = await context.cookies()
            for cookie in cookies:
                if cookie['value'].startswith('eyJ'):
                    logger.info(f"JWT token found in cookie {cookie['name']}: {cookie['value'][:50]}...")
                    return cookie['value']
                elif 'eyJ' in cookie['value']:
                    jwt_match = re.search(r'eyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*', cookie['value'])
                    if jwt_match:
                        logger.info(f"JWT token extracted from cookie {cookie['name']}: {jwt_match.group(0)[:50]}...")
                        return jwt_match.group(0)
        except Exception as e:
            logger.error(f"Error accessing cookies: {e}")
        return None

    async def _trigger_api_calls(self, page: Page) -> bool:
        """Try to trigger API calls that contain JWT tokens."""
        logger.info("Trying to trigger API calls...")
        
        # Try clicking various elements
        for selector in self.selectors['api_triggers']:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        logger.info(f"Clicking element to trigger API calls: {selector}")
                        await element.click()
                        await page.wait_for_timeout(3000)
                        if self.intercepted_token:
                            return True
                        break
            except Exception as e:
                logger.warning(f"Error clicking {selector}: {e}")
        
        # Try navigation
        current_url = page.url
        navigation_urls = [
            current_url.replace('#/', '#/dashboard'),
            current_url.replace('#/', '#/tenants'),
            current_url.replace('#/', '#/manage')
        ]
        
        for nav_url in navigation_urls:
            try:
                logger.info(f"Navigating to {nav_url}...")
                await page.goto(nav_url, wait_until='networkidle', timeout=40000)
                await page.wait_for_timeout(5000)
                if self.intercepted_token:
                    return True
            except Exception as e:
                logger.warning(f"Error navigating to {nav_url}: {e}")
        
        # Try page reload
        try:
            logger.info("Reloading page to trigger initialization API calls...")
            await page.reload(wait_until='networkidle')
            await page.wait_for_timeout(self.api_trigger_timeout)
            if self.intercepted_token:
                return True
        except Exception as e:
            logger.warning(f"Error during page reload: {e}")
        
        return False

    async def login_and_extract_token(self) -> Dict:
        """Main login and token extraction method."""
        async with async_playwright() as p:
            browser = await p.firefox.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=['--disable-web-security']
            )
            
            try:
                context = await browser.new_context(
                    viewport={'width': self.viewport_width, 'height': self.viewport_height},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
                )
                
                page = await context.new_page()
                self._setup_network_interceptors(page)
                
                logger.info("Step 1: Navigating to Auth0 login page...")
                await page.goto(self.login_url, wait_until='networkidle')
                
                # Authentication flow
                if not await self._handle_auth0_login(page):
                    raise Exception("Auth0 login failed")
                
                if not await self._handle_sharp_start_selection(page):
                    raise Exception("Sharp-Start selection failed")
                
                if not await self._handle_sharp_login(page):
                    raise Exception("Sharp login failed")
                
                if not await self._wait_for_dashboard(page):
                    raise Exception("Dashboard redirect failed")
                
                # Token extraction
                logger.info("Step 6: Extracting authentication token...")
                await page.wait_for_timeout(5000)
                
                current_url = page.url
                logger.info(f"Current URL: {current_url}")
                
                # Check for authorization code
                code_match = re.search(r'code=([^&]+)', current_url)
                if code_match:
                    auth_code = code_match.group(1)
                    logger.info(f"Authorization code found: {auth_code[:20]}...")
                
                # Priority 1: Already intercepted token
                if self.intercepted_token:
                    logger.info(f"Token already intercepted: {self.intercepted_token[:50]}...")
                    return self._create_success_response(self.intercepted_token, 'api_request_interception', page)
                
                # Priority 2: Trigger API calls
                if await self._trigger_api_calls(page):
                    logger.info(f"Token intercepted after triggering API calls!")
                    return self._create_success_response(self.intercepted_token, 'api_call_triggered', page)
                
                # Priority 3: URL fragment
                if '#' in current_url:
                    fragment = current_url.split('#')[1]
                    token_match = re.search(r'access_token=([^&]+)', fragment)
                    if token_match:
                        token = token_match.group(1)
                        logger.info(f"Access token found in URL fragment: {token[:50]}...")
                        return self._create_success_response(token, 'url_fragment', page)
                
                # Priority 4: Browser storage
                token = await self._extract_token_from_storage(page)
                if token:
                    return self._create_success_response(token, 'browser_storage', page)
                
                # Priority 5: Cookies
                token = await self._extract_token_from_cookies(context)
                if token:
                    return self._create_success_response(token, 'cookies', page)
                
                # Fallback: Use intercepted token if available
                if self.intercepted_token:
                    return self._create_success_response(self.intercepted_token, 'intercepted_fallback', page)
                
                # No token found but have auth code
                if code_match:
                    return {
                        'success': False,
                        'token': None,
                        'authorization_code': auth_code,
                        'message': 'Login successful but JWT token not found. Authorization code available.',
                        'extracted_at': datetime.now().isoformat(),
                        'url': page.url,
                        'final_page_title': await page.title()
                    }
                
                return self._create_failure_response('No token found', page)
                
            except Exception as e:
                logger.error(f"Error during login process: {e}")
                try:
                    await page.screenshot(path='debug_error.png')
                except:
                    pass
                return {
                    'success': False,
                    'error': str(e),
                    'extracted_at': datetime.now().isoformat(),
                    'url': page.url if 'page' in locals() else 'unknown'
                }
            finally:
                await browser.close()

    def _create_success_response(self, token: str, source: str, page: Page) -> Dict:
        """Create a standardized success response."""
        return {
            'success': True,
            'token': token,
            'source': source,
            'extracted_at': datetime.now().isoformat(),
            'url': page.url,
            'final_page_title': 'Synappx Admin'  # Avoid async call in sync method
        }

    def _create_failure_response(self, error: str, page: Page) -> Dict:
        """Create a standardized failure response."""
        return {
            'success': False,
            'token': None,
            'error': error,
            'extracted_at': datetime.now().isoformat(),
            'url': page.url,
        }

    def test_api_with_token(self, token: str) -> Dict:
        """Test the API endpoint with the extracted token."""
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.6',
            'authorization': f'Bearer {token}',
            'content-type': 'application/json',
            'origin': 'https://dev7-smartoffice.sharpb2bcloud.com',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'x-app-version': '4.16.0-SNAPSHOT-20250717-110003',
            'x-time-zone': '+05:30'
        }
        
        try:
            response = requests.get(self.api_url, headers=headers, timeout=30)
            logger.info(f"API response status code: {response.status_code}")
            return {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'response_data': response.json() if response.status_code == 200 else response.text,
                'tested_at': datetime.now().isoformat()
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'tested_at': datetime.now().isoformat()
            }

    def save_token_to_file(self, token_data: Dict, api_test_result: Dict = None) -> None:
        """Save token and API test results to JSON file."""
        data = {
            'token_extraction': token_data,
            'api_test': api_test_result,
            'saved_at': datetime.now().isoformat()
        }
        
        with open(self.token_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info("Token data saved to %s", self.token_file)

    async def run(self) -> Dict:
        """Main method to run the complete token extraction process."""
        logger.info("Starting Auth0 token extraction process")
        
        # Extract token
        token_result = await self.login_and_extract_token()
        
        if token_result['success']:
            logger.info("Token extracted successfully: %s...", token_result['token'][:50])
            
            # Test API with token
            logger.info("Testing API with extracted token")
            api_result = self.test_api_with_token(token_result['token'])
            
            if api_result['success']:
                logger.info("API test successful")
            else:
                logger.warning("API test failed: %s", api_result)
            
            # Save to file
            self.save_token_to_file(token_result, api_result)
            
            return {
                'success': True,
                'token': token_result['token'],
                'api_test': api_result
            }
        else:
            logger.error("Token extraction failed: %s", token_result)
            self.save_token_to_file(token_result)
            return token_result


async def main():
    """Main entry point."""
    extractor = AuthTokenExtractor()
    result = await extractor.run()
    return result

if __name__ == "__main__":
    token_file = os.getenv('TOKEN_FILE', 'auth_token.json')
    token = get_stored_token(token_file)
    if token and not is_jwt_expired(token):
        print("Valid JWT token found. Skipping extraction.")
        print(f"Token: {token[:40]}... (truncated)")
    else:
        asyncio.run(main())