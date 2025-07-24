"""
FastMCP 2.0 server for Auth0 JWT token management.
Provides tools for extracting and managing JWT tokens from Auth0 authentication.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from auth_playwright_optimized import AuthTokenExtractor, is_jwt_expired


from fastmcp import FastMCP
from fastmcp.client.auth import BearerAuth
# Import AuthTokenExtractor lazily to avoid initialization issues
# from .auth_playwright_optimized import AuthTokenExtractor


# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Auth0 JWT Token Manager")

class TokenManager:
    """Manages JWT token operations and storage"""
    
    def __init__(self):
        self.token_file = os.path.join(Path(__file__).parent, "auth_token.json")
        # Don't initialize extractor here to avoid event loop issues
        self.extractor = None
    
    def get_extractor(self):
        """Lazy initialization of the AuthTokenExtractor"""
        if self.extractor is None:
            self.extractor = AuthTokenExtractor()
        return self.extractor

    async def load_token_data(self) -> Optional[Dict[str, Any]]:
        """Load token data from JSON file"""
        if os.path.exists(self.token_file):
            if not is_jwt_expired(self.token_file):
                self.run_playwright_token_extraction()
            try:
                import aiofiles
                async with aiofiles.open(self.token_file, 'r') as f:
                    return json.loads(await f.read())
            except (json.JSONDecodeError, IOError) as e:
                return {"error": f"Failed to load token data: {e}"}
        return None
    
    def save_token_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save token data to JSON file"""
        try:
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=2)
            return {"success": True, "message": "Token data saved successfully"}
        except IOError as e:
            return {"success": False, "error": f"Failed to save token data: {e}"}

    async def run_playwright_token_extraction(
        self,
    ) -> Dict[str, Any]:
        """
        Run the Playwright token extraction script as a subprocess.

        Args:
            script_path: Path to the Playwright extraction script. If None, uses the default in the same directory.
            cwd: Working directory for the subprocess. If None, uses the current working directory.
            timeout: Timeout in seconds for the subprocess.

        Returns:
            Dict containing stdout, stderr, return code, and success status.
        """
        logger = logging.getLogger(__name__)
        # Auto-fetch script_path and cwd if not provided

        try:
            result = await self.get_extractor().run()
            logger.info(f"Playwright token extraction result: {result}")
            if result.get("success"):
                logger.info("Playwright token extraction completed successfully.")
            else:
                logger.warning("Playwright token extraction failed.")

            logger.info(f"Api test result: {result.get('api_test')}")

            return {
                "success": result.get("success"),
                "token": result.get("token"),
                "message": "Token extraction completed successfully.",
                "retrieved_at": datetime.now().isoformat()
            }
        except Exception as e:
            logger.exception("Unexpected error during Playwright token extraction")
            error_data = {
                "success": False,
                "error": str(e),
                "extracted_at": datetime.now().isoformat()
            }
            self.save_token_data(error_data)
            return error_data


# Initialize token manager
token_manager = TokenManager()

@mcp.tool
async def extract_auth_token() -> Dict[str, Any]:
    """
    Extract JWT token from Auth0 authentication using Playwright automation.
    Only runs extraction if token is missing or expired.
    """
    # 1. Try to load stored token
    token_data = await token_manager.load_token_data() or {}
    token = token_data.token_extraction.get("token") or {}

    # 2. Check if token exists and is not expired
    logger.debug(f"Loaded token data: {token_data}")
    if token and not is_jwt_expired(token):
        return {
            "success": True,
            "token": token,
            "message": "Valid JWT token found. Skipping extraction.",
            "retrieved_at": datetime.now().isoformat()
        }

    logger.info("No valid token found or token is expired. Running Playwright extraction...")
    result = await token_manager.run_playwright_token_extraction()
    logging.info(f"Playwright extraction result: {result}")
    return result

async def _get_valid_token() -> Optional[str]:
    """
    Retrieve a valid JWT token from storage, or extract a new one if missing/expired.
    """
    token_data = await token_manager.load_token_data() or {}
    extraction_result = token_data.get("token_extraction") or token_data.get("extraction_result") or {}
    token = extraction_result.get("token") if isinstance(extraction_result, dict) else None

    if token and not is_jwt_expired(token):
        return token

    # Token missing or expired, extract new token
    extraction = await token_manager.run_playwright_token_extraction()
    if extraction.get("success"):
        token_data = await token_manager.load_token_data() or {}
        extraction_result = token_data.get("token_extraction") or token_data.get("extraction_result") or {}
        token = extraction_result.get("token") if isinstance(extraction_result, dict) else None
        if token and not is_jwt_expired(token):
            return token
    return None

def _prepare_headers(token: str) -> Dict[str, str]:
    """
    Prepare headers for the API request using the JWT token.
    """
    return {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.6',
        'authorization': f'Bearer {token}',
        'content-type': 'application/json',
        'origin': 'https://dev7-smartoffice.sharpb2bcloud.com',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        'x-time-zone': '+05:30',
        "ocp-apim-subscription-key": os.getenv("OCP_APIM_SUBSCRIPTION_KEY")
    }

async def _handle_response(response, endpoint: str, method: str) -> Dict[str, Any]:
    """
    Handle the API response and log the call.
    """
    token_data = await token_manager.load_token_data()  or {}
    try:
        response_data = response.json()
    except Exception:
        response_data = response.text

    result = {
        "success": response.status_code in [200, 201, 204],
        "status_code": response.status_code,
        "response_data": response_data,
        "endpoint": endpoint,
        "method": method.upper(),
        "requested_at": datetime.now().isoformat()
    }

    api_log = token_data.get("api_calls", [])
    api_log.append(result)
    token_data["api_calls"] = api_log[-10:]
    token_manager.save_token_data(token_data)
    return result

@mcp.tool
async def make_api_request(endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Make a custom API request using the stored JWT token.
    If the token is missing or expired, automatically extract a new one.
    """
    token = await _get_valid_token()
    if not token:
        return {
            "success": False,
            "error": "No valid token found or failed to extract token."
        }
    URL = "https://dev7-cloudrmm-api.sharpb2bcloud.com"
    headers = _prepare_headers(token)
    logging.info("Making API request to %s with headers: %s", endpoint, headers)
    try:
        if method.upper() == "GET":
            response = requests.get(f"{URL}{endpoint}", headers=headers, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(f"{URL}{endpoint}", headers=headers, json=data, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(f"{URL}{endpoint}", headers=headers, json=data, timeout=30)
        elif method.upper() == "DELETE":
            response = requests.delete(f"{URL}{endpoint}", headers=headers, timeout=30)
        else:
            return {
                "success": False,
                "error": f"Unsupported HTTP method: {method}"
            }
        return await _handle_response(response, endpoint, method)
    except Exception as e:
        token_data = await token_manager.load_token_data()  or {}
        error_result = {
            "success": False,
            "error": str(e),
            "endpoint": endpoint,
            "method": method.upper(),
            "requested_at": datetime.now().isoformat()
        }
        api_log = token_data.get("api_calls", [])
        api_log.append(error_result)
        token_data["api_calls"] = api_log[-10:]
        # token_manager.save_token_data(token_data)
        return error_result

# Add a resource for the token file
@mcp.resource(uri="file://auth_token.json")
def get_token_file() -> str:
    """
    Resource providing access to the current token data file.
    
    Returns:
        String content of the auth_token.json file
    """

    token_data = token_manager.load_token_data()
    if token_data:
        return json.dumps(token_data, indent=2)
    return json.dumps({"message": "No token data available"}, indent=2)


# Export for importable MCP server
__all__ = [
    "mcp",
    "TokenManager",
    "token_manager",
    "extract_auth_token",
    "make_api_request",
    "get_token_file",
]


