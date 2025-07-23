"""
FastMCP 2.0 server for Auth0 JWT token management.
Provides tools for extracting and managing JWT tokens from Auth0 authentication.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from auth_playwright_optimized import AuthTokenExtractor, is_jwt_expired


from fastmcp import FastMCP
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
    
    def load_token_data(self) -> Optional[Dict[str, Any]]:
        """Load token data from JSON file"""
        if os.path.exists(self.token_file):
            if not is_jwt_expired(self.token_file):
                result = self.run_playwright_token_extraction()
            try:
                with open(self.token_file, 'r') as f:
                    return json.load(f)
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
    
    import sys
    
    def run_playwright_token_extraction(
        self,
        script_path: str = "D:\\AI\\rmm_mcp_server\\auth_playwright_optimized.py",
        cwd: str = "D:\\AI\\rmm_mcp_server",
        timeout = 20
        ) -> Dict[str, Any]:
        """
        Run the Playwright token extraction script as a subprocess.

        Args:
            script_path: Path to the Playwright extraction script.
            cwd: Working directory for the subprocess.
            timeout: Timeout in seconds for the subprocess.

        Returns:
            Dict containing stdout, stderr, return code, and success status.
        """
        logger = logging.getLogger(__name__)
        logger.debug(f"Running Playwright script: {script_path}")

        try:
            result = subprocess.run(
                ["uv", "run", "python", script_path],
                shell=True,
                cwd=cwd,
                text=True,
                timeout=timeout,
                capture_output=True
            )

            if result.stdout:
                print(result.stdout)
                logger.debug(f"Subprocess stdout: {result.stdout.strip()}")
            if result.stderr:
                print(result.stderr)
                logger.warning(f"Subprocess stderr: {result.stderr.strip()}")

            logger.info(f"Subprocess exit code: {result.returncode}")

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
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
def extract_auth_token() -> Dict[str, Any]:
    """
    Extract JWT token from Auth0 authentication using Playwright automation.
    Only runs extraction if token is missing or expired.
    """
    # 1. Try to load stored token
    token_data = token_manager.load_token_data() or {}
    extraction_result = token_data.get("token_extraction") \
                     or token_data.get("extraction_result") \
                     or {}
    token = extraction_result.get("token") if isinstance(extraction_result, dict) else None

    # 2. Check if token exists and is not expired
    logger.debug(f"Loaded token data: {token}")
    if token and not is_jwt_expired(token):
        return {
            "success": True,
            "token": token,
            "message": "Valid JWT token found. Skipping extraction.",
            "retrieved_at": datetime.now().isoformat()
        }

    logger.info("No valid token found or token is expired. Running Playwright extraction...")
    # 3. If missing or expired, run Playwright extraction as before
    result = token_manager.run_playwright_token_extraction()

    if result.get("success"):
        token_data = token_manager.load_token_data()
        if token_data and "extraction_result" in token_data:
            extraction_result = token_data["extraction_result"]
            return {
                "success": extraction_result.get("success", False),
                "token": extraction_result.get("token"),
                "api_test": extraction_result.get("api_test"),
                "message": "Token extraction completed via subprocess",
                "subprocess_output": result.get("stdout")
            }
        else:
            return {
                "success": "Token extracted successfully" in result.get("stdout", ""),
                "message": "Token extraction completed via subprocess",
                "subprocess_output": result.get("stdout"),
                "subprocess_error": result.get("stderr")
            }
    else:
        return {
            "success": False,
            "error": f"Subprocess failed with return code {result.get('returncode')}",
            "subprocess_output": result.get("stdout"),
            "subprocess_error": result.get("stderr"),
            "extracted_at": datetime.now().isoformat()
        }

@mcp.tool
def get_or_extract_token() -> Dict[str, Any]:
    """
    Returns a valid JWT token if available, otherwise extracts a new token using Playwright.
    """
    # Try to load stored token data
    token_data = token_manager.load_token_data() or {}
    extraction_result = token_data.get("token_extraction") \
                     or token_data.get("extraction_result") \
                     or {}
    token = extraction_result.get("token") if isinstance(extraction_result, dict) else None

    # Check if token exists and is not expired
    if token and not is_jwt_expired(token):
        return {
            "success": True,
            "token": token,
            "message": "Valid JWT token found. Skipping extraction.",
            "retrieved_at": datetime.now().isoformat()
        }

    # If missing or expired, run Playwright extraction
    result = token_manager.run_playwright_token_extraction()
    if result.get("success"):
        # Reload token data after extraction
        token_data = token_manager.load_token_data() or {}
        extraction_result = token_data.get("token_extraction") \
                         or token_data.get("extraction_result") \
                         or {}
        token = extraction_result.get("token") if isinstance(extraction_result, dict) else None
        return {
            "success": bool(token),
            "token": token,
            "message": "Token extracted via Playwright.",
            "subprocess_output": result.get("stdout"),
            "retrieved_at": datetime.now().isoformat()
        }
    else:
        return {
            "success": False,
            "error": "Failed to extract token via Playwright.",
            "subprocess_output": result.get("stdout"),
            "subprocess_error": result.get("stderr"),
            "retrieved_at": datetime.now().isoformat()
        }
        
@mcp.tool
def test_api_with_stored_token() -> Dict[str, Any]:
    """
    Test the Sharp B2B Cloud API using the stored JWT token.
    
    Makes a request to the tenantList API endpoint using the stored token
    and returns the response data.
    
    Returns:
        Dict containing API response data and status
    """
    # Get stored token
    token_data = token_manager.load_token_data()
    
    if not token_data:
        return {
            "success": False,
            "error": "No token data found. Run extract_auth_token first."
        }
    
    # Extract token from stored data
    extraction_result = token_data.get("extraction_result", {})
    token = extraction_result.get("token")
    
    if not token:
        return {
            "success": False,
            "error": "No valid token found in stored data."
        }
    
    # Test API with token
    api_result = token_manager.extractor.test_api_with_token(token)
    
    # Update stored data with new API test result
    token_data["latest_api_test"] = api_result
    token_manager.save_token_data(token_data)
    
    return api_result

def _get_valid_token() -> Optional[str]:
    """
    Retrieve a valid JWT token from storage, or extract a new one if missing/expired.
    """
    token_data = token_manager.load_token_data() or {}
    extraction_result = token_data.get("token_extraction") or token_data.get("extraction_result") or {}
    token = extraction_result.get("token") if isinstance(extraction_result, dict) else None

    if token and not is_jwt_expired(token):
        return token

    # Token missing or expired, extract new token
    extraction = token_manager.run_playwright_token_extraction()
    if extraction.get("success"):
        token_data = token_manager.load_token_data() or {}
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
        "ocp-apim-subscription-key":"2c2f0a40f9fc4ceb957a12a3856160f2" 
    }

def _handle_response(response, endpoint: str, method: str) -> Dict[str, Any]:
    """
    Handle the API response and log the call.
    """
    token_data = token_manager.load_token_data()  or {}
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
def make_api_request(endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Make a custom API request using the stored JWT token.
    If the token is missing or expired, automatically extract a new one.
    """
    token = _get_valid_token()
    if not token:
        return {
            "success": False,
            "error": "No valid token found or failed to extract token."
        }

    headers = _prepare_headers(token)

    try:
        if method.upper() == "GET":
            response = requests.get(endpoint, headers=headers, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(endpoint, headers=headers, json=data, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(endpoint, headers=headers, json=data, timeout=30)
        elif method.upper() == "DELETE":
            response = requests.delete(endpoint, headers=headers, timeout=30)
        else:
            return {
                "success": False,
                "error": f"Unsupported HTTP method: {method}"
            }
        return _handle_response(response, endpoint, method)
    except Exception as e:
        token_data = token_manager.load_token_data()  or {}
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
        token_manager.save_token_data(token_data)
        return error_result
@mcp.tool
def get_api_call_history() -> Dict[str, Any]:
    """
    Retrieve the history of API calls made using the stored token.
    
    Returns:
        Dict containing the last 10 API calls and their results
    """
    token_data = token_manager.load_token_data() 
    
    if not token_data:
        return {
            "success": False,
            "error": "No token data found."
        }
    
    api_calls = token_data.get("api_calls", [])
    
    return {
        "success": True,
        "total_calls": len(api_calls),
        "recent_calls": api_calls,
        "retrieved_at": datetime.now().isoformat()
    }

@mcp.tool
def clear_token_data() -> Dict[str, Any]:
    """
    Clear all stored token data and API call history.
    
    Returns:
        Dict containing success status
    """
    try:
        if token_manager.token_file.exists():
            token_manager.token_file.unlink()
        
        return {
            "success": True,
            "message": "Token data cleared successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to clear token data: {e}"
        }

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
    "test_api_with_stored_token",
    "make_api_request",
    "get_api_call_history",
    "clear_token_data",
    "get_token_file",
    "get_or_extract_token"
]


