"""
FastMCP 2.0 server for Auth0 JWT token management.
Provides tools for extracting and managing JWT tokens from Auth0 authentication.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from auth_playwright_optimized import AuthTokenExtractor, is_jwt_expired
import jwt

from pydantic import BaseModel

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
            try:
                with open(self.token_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load token data: {e}")
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
            # logger.info(f"Playwright token extraction result: {result}")
            if result.get("success"):
                logger.info("Playwright token extraction completed successfully.")
            else:
                logger.warning("Playwright token extraction failed.")

            # logger.info(f"Api test result: {result.get('api_test')}")

            # Prepare the response in the expected format
            extraction_result = {
                "success": result.get("success"),
                "token": result.get("token"),
                "message": "Token extraction completed successfully.",
                "retrieved_at": datetime.now().isoformat()
            }
            
            # Save the full result to file (including token_extraction structure)
            if result.get("success") and result.get("token"):
                file_data = {
                    "token_extraction": {
                        "success": True,
                        "token": result.get("token"),
                        "source": "playwright_extraction",
                        "extracted_at": datetime.now().isoformat()
                    },
                    "api_test": result.get("api_test"),
                    "saved_at": datetime.now().isoformat()
                }
                self.save_token_data(file_data)
            
            return extraction_result
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

@mcp.tool(
    name="extract_auth_token",
    description="Extracts JWT token from Auth0 authentication using Playwright automation.",
)
async def extract_auth_token() -> Dict[str, Any]:
    """
    Extract JWT token from Auth0 authentication using Playwright automation.
    Only runs extraction if token is missing or expired.
    """
    # 1. Try to load stored token
    token_data = await token_manager.load_token_data() or {}
    # logger.debug(f"Loaded token data: {token_data}")
    extraction_result = token_data.get("token_extraction", {})
    token = extraction_result.get("token") if isinstance(extraction_result, dict) else None

    # 2. Check if token exists, is not empty, and is not expired
    logger.debug(f"Token found: {bool(token)}, Token empty: {not token if token else 'N/A'}")
    if token and token.strip() and not is_jwt_expired(token):
        return {
            "success": True,
            "token": token,
            "message": "Valid JWT token found. Skipping extraction.",
            "retrieved_at": datetime.now().isoformat()
        }

    logger.info("No valid token found, token is empty, or token is expired. Running Playwright extraction...")
    result = await token_manager.run_playwright_token_extraction()
    logging.info(f"Playwright extraction result: {result}")
    return result

async def _get_valid_token() -> Optional[List]:
    """
    Retrieve a valid JWT token from storage, or extract a new one if missing/expired.
    """
    token_data = await token_manager.load_token_data() or {}
    extraction_result = token_data.get("token_extraction", {})
    token = extraction_result.get("token") if isinstance(extraction_result, dict) else None

    # Check if token exists, is not empty, and is not expired
    if token and token.strip() and not is_jwt_expired(token):
        return [token, token_data]
    
    # Token missing, empty, or expired, extract new token
    logger.info("No valid token found, token is empty, or token is expired. Running Playwright extraction...")
    extraction = await token_manager.run_playwright_token_extraction()
    if extraction.get("success") and extraction.get("token"):
        # Reload token data after extraction
        token_data = await token_manager.load_token_data() or {}
        extraction_result = token_data.get("token_extraction", {})
        token = extraction_result.get("token") if isinstance(extraction_result, dict) else None
        if token and token.strip() and not is_jwt_expired(token):
            return [token, token_data]
    
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
        'origin': 'https://alt-synappxadminportal.sharpb2bcloud.com',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        'x-time-zone': '+05:30',
        "ocp-apim-subscription-key": os.getenv("OCP_APIM_SUBSCRIPTION_KEY")
    }

async def _handle_response(response , endpoint: str, method: str) -> Dict[str, Any]:
    """
    Handle the API response and log the call.
    """
    token_data = await token_manager.load_token_data()  or {}
    try:
        response_data = response.json()
    except Exception as e:
        response_data = response.text
        logger.error(f"Failed to parse response JSON: {e}")

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

async def _make_api_call(
    endpoint: str,
    method: str = "GET",
    payload: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Internal helper function to make API calls.
    This is the core logic extracted from make_api_request tool.
    """
    token = await _get_valid_token()
    URL = f"https://alt-rmm-api.sharpb2bcloud.com{endpoint}"
    data = payload or {
        "startIndex": 0,
        "count": 25,
        "groupId": "6d167a66-9c03-b981-6e37-8770c76676be",
        "simpleFilters": [],
        "orderBy": [
            {
                "key": "otaMode",
                "order": "ascending"
            }
        ]
    }
    if not token or not token[0]:
        return {
            "success": False,
            "error": "No valid token found or failed to extract token."
        }
    headers = _prepare_headers(token[0])
    try:
        if method.upper() == "GET":
            response = requests.get(URL, headers=headers, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(URL, headers=headers, json=data, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(URL, headers=headers, json=data, timeout=30)
        elif method.upper() == "DELETE":
            response = requests.delete(URL, headers=headers, timeout=30)
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
   
@mcp.tool(
    name="make_api_request",
    description="Get devices that require firmware updates. Use this tool when asked about devices needing firmware updates, firmware status, or device update requirements.",
)
async def make_api_request(
    endpoint: str = "/rmm/fss/fwupd/getFirmwareUpdateList",
    method: str = "GET",
    payload: Optional[dict] = None
) -> any:
    """Make an API request to the specified endpoint.

    Args:
        endpoint (str, optional): The API endpoint to call. Defaults to "/rmm/fss/fwupd/getFirmwareUpdateList".
        method (str, optional): The HTTP method to use. Defaults to "GET".
        payload (Optional[dict], optional): The request payload. Defaults to None.
    
    Note:
        If "latestFirmwareVersion" has a value, it indicates that the device requires a firmware update.
    
    Returns:
        any: The API response.
    """
    return await _make_api_call(endpoint, method, payload)

def _decode_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode JWT token payload to extract claims using PyJWT library.
    
    Args:
        token (str): JWT token string
        
    Returns:
        Optional[Dict[str, Any]]: Decoded payload or None if invalid
    """
    try:
        # Decode JWT token without verification (since we just need the payload)
        # Note: This is safe for extracting claims from trusted tokens
        payload_dict = jwt.decode(token, options={"verify_signature": False})
        return payload_dict
    except Exception as e:
        logger.error(f"Failed to decode JWT payload: {e}")
        return None

async def _get_group_id_from_token() -> Optional[str]:
    """
    Extract groupId (sspTenantId) from the current JWT token using PyJWT.
    
    Returns:
        Optional[str]: The sspTenantId from JWT token or None if not found
    """
    token_data = await token_manager.load_token_data() or {}
    extraction_result = token_data.get("token_extraction", {})
    token = extraction_result.get("token") if isinstance(extraction_result, dict) else None
    
    if not token or not token.strip():
        logger.warning("No token available to extract groupId")
        return None
        
    payload = _decode_jwt_payload(token)
    if not payload:
        logger.warning("Failed to decode JWT token payload")
        return None
        
    group_id = payload.get("sspTenantId")
    if group_id:
        logger.info(f"Extracted groupId from JWT token: {group_id}")
        return group_id
    else:
        logger.warning("sspTenantId not found in JWT token payload")
        return None

@mcp.tool(
    name="list_devices",
    description="Retrieve and display all managed devices with their current firmware status. This tool shows device information including model, serial number, firmware version, and update status. Devices with a 'latestFirmwareVersion' value require firmware updates.",
)
async def list_devices(
    group_id: Optional[str] = None,
    page_size: int = 25,
    start_index: int = 0
) -> Dict[str, Any]:
    """
    List all managed devices with their current firmware status.
    
    Args:
        group_id (Optional[str]): Filter by specific group ID. If None, extracts from JWT token.
        page_size (int): Number of devices to return (default: 25, max: 100).
        start_index (int): Starting index for pagination (default: 0).
    
    Returns:
        Dict containing device list with formatted information including:
        - Device identification (model, serial, IP address)
        - Current firmware version and latest available version
        - Update status and OTA configuration
        - Whether firmware update is needed
    """
    # Extract group ID from JWT token if not provided
    logger.info(f"Using group ID: {group_id}")
    if not group_id:
        group_id = await _get_group_id_from_token()
        
    # Use fallback default group ID if extraction fails
    if not group_id:
        default_group_id = "6d167a66-9c03-b981-6e37-8770c76676be"
        group_id = default_group_id
        logger.warning(f"Using fallback default group ID: {default_group_id}")
    
    target_group_id = group_id
    logger.info(f"Target group ID for device listing: {target_group_id}")
    # Validate page size
    if page_size > 100:
        page_size = 100
    elif page_size < 1:
        page_size = 25
    
    payload = {
        "startIndex": start_index,
        "count": page_size,
        "groupId": target_group_id,
        "simpleFilters": [],
        "orderBy": [
            {
                "key": "otaMode",
                "order": "ascending"
            }
        ]
    }
    logger.info(f"Payload for API request: {payload}")
    # Make API request using existing function
    api_result = await _make_api_call(
        endpoint="/rmm/fss/fwupd/getFirmwareUpdateList",
        method="POST",
        payload=payload
    )
    logger.info(f"API result: {api_result}")
    if not api_result.get("success"):
        return {
            "success": False,
            "error": api_result.get("error", "Failed to retrieve device list"),
            "endpoint": "/rmm/fss/fwupd/getFirmwareUpdateList"
        }
    
    response_data = api_result.get("response_data", {})
    device_list = response_data.get("deviceList", [])
    
    # Format device information for better readability
    formatted_devices = []
    update_needed_count = 0
    
    for device in device_list:
        # Check if device needs firmware update
        needs_update = bool(device.get("latestFirmwareVersion", "").strip())
        if needs_update:
            update_needed_count += 1
            
        formatted_device = {
            "device_id": device.get("deviceId", ""),
            "model_name": device.get("modelName", ""),
            "serial_number": device.get("serialNumber", ""),
            "ip_address": device.get("ipAddress", ""),
            "friendly_name": device.get("friendlyName", ""),
            "current_firmware": device.get("firmwareVersion", ""),
            "latest_firmware": device.get("latestFirmwareVersion", ""),
            "needs_update": needs_update,
            "update_status": device.get("updateStatus", ""),
            "ota_mode": device.get("otaMode", ""),
            "ota_setting_status": device.get("otaSettingStatus", ""),
            "ota_window": {
                "start_hour": device.get("otaStartHour", ""),
                "end_hour": device.get("otaEndHour", "")
            }
        }
        formatted_devices.append(formatted_device)
    
    # Prepare summary information
    summary = {
        "total_devices": response_data.get("totalCount", len(device_list)),
        "returned_count": len(formatted_devices),
        "devices_needing_update": update_needed_count,
        "start_index": start_index,
        "page_size": page_size,
        "group_id": target_group_id,
        "group_id_source": "jwt_token" if group_id == await _get_group_id_from_token() else "parameter_or_fallback"
    }
    
    return {
        "success": True,
        "summary": summary,
        "devices": formatted_devices,
        "raw_response": response_data,
        "retrieved_at": datetime.now().isoformat()
    }

@mcp.tool(
    name="configure_ota_mode",
    description="Set automatic update preferences for devices. Configure OTA (Over-The-Air) update mode and schedule for Sharp MFP devices.",
)
async def configure_ota_mode(
    device_ids: List[str],
    ota_mode: str,
    start_hour: Optional[int] = None,
    end_hour: Optional[int] = None,
    group_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Configure OTA update mode and schedule for specified devices.
    
    Args:
        device_ids (List[str]): Array of target device IDs to configure
        ota_mode (str): OTA mode - "auto", "confirmation", or "off"
        start_hour (Optional[int]): Update window start time (0-23 hours, -1 for 24hrs). Default: 2
        end_hour (Optional[int]): Update window end time (0-23 hours, -1 for 24hrs). Default: 4
        group_id (Optional[str]): Group ID. If None, extracts from JWT token
    
    Returns:
        Dict containing configuration result and validation details
    """
    # Validate OTA mode
    valid_modes = ["auto", "confirmation", "off"]
    if ota_mode not in valid_modes:
        return {
            "success": False,
            "error": f"Invalid ota_mode '{ota_mode}'. Must be one of: {', '.join(valid_modes)}"
        }
    
    # Validate device IDs format
    import re
    device_id_pattern = r'^mn=[A-Za-z0-9+/=]+:sn=[A-Za-z0-9+/=]+$'
    invalid_devices = []
    for device_id in device_ids:
        if not re.match(device_id_pattern, device_id):
            invalid_devices.append(device_id)
    
    if invalid_devices:
        return {
            "success": False,
            "error": f"Invalid device ID format: {invalid_devices}. Expected format: 'mn=<base64>:sn=<base64>'"
        }
    
    # Set default hours if not provided
    if start_hour is None:
        start_hour = 2
    if end_hour is None:
        end_hour = 4
        
    # Validate time range - only for "auto" mode
    if ota_mode == "auto":
        # Valid values: 0-23 or -1 (for 24 hours availability)
        if not ((-1 <= start_hour <= 23) and (-1 <= end_hour <= 23)):
            return {
                "success": False,
                "error": "start_hour and end_hour must be between 0-23 or -1 (for 24hrs availability)"
            }
        
        # If not using 24hr availability (-1), validate logical time range
        if start_hour != -1 and end_hour != -1 and start_hour >= end_hour:
            return {
                "success": False,
                "error": "start_hour must be less than end_hour when not using 24hr availability (-1)"
            }
    
    # Extract group ID from JWT token if not provided
    if not group_id:
        group_id = await _get_group_id_from_token()
        
    # Use fallback default group ID if extraction fails
    if not group_id:
        default_group_id = "6d167a66-9c03-b981-6e37-8770c76676be"
        group_id = default_group_id
        logger.warning(f"Using fallback default group ID: {default_group_id}")
    
    # Prepare payload for setOTAMode API
    payload = {
        "groupId": group_id,
        "deviceIds": device_ids,
        "isExclude": False,
        "otaMode": ota_mode,
        "otaStartHour": start_hour,
        "otaEndHour": end_hour
    }
    
    # Make API request to configure OTA mode
    api_result = await _make_api_call(
        endpoint="/stateful/fss/fwupd/setOTAMode",
        method="POST",
        payload=payload
    )
    
    if not api_result.get("success"):
        return {
            "success": False,
            "error": api_result.get("error", "Failed to configure OTA mode"),
            "endpoint": "/stateful/fss/fwupd/setOTAMode",
            "api_response": api_result
        }
    
    response_data = api_result.get("response_data", {})
    error_list = response_data.get("common", {}).get("errorList", [])
    
    # Check for API errors
    if error_list:
        return {
            "success": False,
            "error": "API returned errors",
            "error_details": error_list,
            "endpoint": "/stateful/fss/fwupd/setOTAMode"
        }
    
    # Prepare success response with enhanced window description
    update_window_description = "24 hours availability" if start_hour == -1 or end_hour == -1 else f"{end_hour - start_hour} hours"
    
    configuration_summary = {
        "configured_devices": len(device_ids),
        "device_ids": device_ids,
        "ota_mode": ota_mode,
        "update_window": {
            "start_hour": start_hour,
            "end_hour": end_hour,
            "description": update_window_description
        },
        "group_id": group_id,
        "group_id_source": "jwt_token" if group_id == await _get_group_id_from_token() else "parameter_or_fallback"
    }
    
    return {
        "success": True,
        "message": f"Successfully configured OTA mode '{ota_mode}' for {len(device_ids)} device(s)",
        "configuration": configuration_summary,
        "raw_response": response_data,
        "configured_at": datetime.now().isoformat()
    }

@mcp.tool(
    name="list_staged_firmware",
    description="Show all available staged firmware files for Sharp MFP devices. Returns metadata including title, filename, size, and upload date.",
)
async def list_staged_firmware(
    group_id: Optional[str] = None,
    start_index: int = 0,
    count: int = 100
) -> Dict[str, Any]:
    """
    List all available staged firmware files.

    Args:
        group_id (Optional[str]): Group ID to filter firmware files. If None, extracts from JWT token.
        start_index (int): Pagination start index (default: 0).
        count (int): Number of firmware files to return (default: 100, max: 100).

    Returns:
        Dict containing a list of firmware files with metadata.
    """
    # Extract group ID from JWT token if not provided
    if not group_id:
        group_id = await _get_group_id_from_token()
    if not group_id:
        group_id = "6d167a66-9c03-b981-6e37-8770c76676be"  # fallback default

    payload = {
        "startIndex": start_index,
        "count": min(count, 100),
        "groupId": group_id
    }

    api_result = await _make_api_call(
        endpoint="/rmm/fss/fwupd/getFirmwareDataList",
        method="POST",
        payload=payload
    )

    if not api_result.get("success"):
        return {
            "success": False,
            "error": api_result.get("error", "Failed to retrieve staged firmware list"),
            "endpoint": "/rmm/fss/fwupd/getFirmwareDataList"
        }

    response_data = api_result.get("response_data", {})
    firmware_list = response_data.get("firmwareDataList", [])

    formatted_firmware = []
    for fw in firmware_list:
        formatted_firmware.append({
            "file_id": fw.get("fileId", ""),
            "title": fw.get("fileTitle", ""),
            "filename": fw.get("fileName", ""),
            "size_bytes": fw.get("fileSize", 0),
            "uploaded_at": fw.get("uploadDate", None)
        })

    summary = {
        "total_files": response_data.get("totalCount", len(firmware_list)),
        "returned_count": len(formatted_firmware),
        "group_id": group_id,
        "start_index": start_index,
        "count": count
    }

    return {
        "success": True,
        "summary": summary,
        "firmware_files": formatted_firmware,
        "raw_response": response_data,
        "retrieved_at": datetime.now().isoformat()
    }

@mcp.tool(
    name="schedule_firmware_update",
    description="Schedule firmware updates for specific devices. Configures when to transfer firmware and when to execute the update.",
)
async def schedule_firmware_update(
    device_ids: List[str],
    firmware_file_id: str,
    transfer_datetime: int,
    execute_datetime: str,
    timezone: str = "UTC+05:30",
    group_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Schedule firmware update for specified devices.
    
    Args:
        device_ids (List[str]): Array of target device IDs to update
        firmware_file_id (str): ID of the staged firmware file to deploy
        transfer_datetime (int): Unix timestamp (milliseconds) when to transfer firmware to device
        execute_datetime (str): When to execute update (format: "YYYYMMDDHHDD")
        timezone (str): Timezone for the transfer (default: "UTC+05:30")
        group_id (Optional[str]): Group ID. If None, extracts from JWT token
    
    Note:
        - Before directly scheduling ask the user if they want to schedule a firmware update.
            If the user confirms, proceed with the scheduling.
        - Validate all inputs including device IDs, firmware file ID, and datetime formats.
        - Ask user which staged firmware file to use if multiple are available.

    Returns:
        Dict containing scheduling result and validation details
    """
    # Validate device IDs format
    import re
    device_id_pattern = r'^mn=[A-Za-z0-9+/=]+:sn=[A-Za-z0-9+/=]+$'
    invalid_devices = []
    for device_id in device_ids:
        if not re.match(device_id_pattern, device_id):
            invalid_devices.append(device_id)
    
    if invalid_devices:
        return {
            "success": False,
            "error": f"Invalid device ID format: {invalid_devices}. Expected format: 'mn=<base64>:sn=<base64>'"
        }
    
    # Validate firmware file ID (UUID format)
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if not re.match(uuid_pattern, firmware_file_id):
        return {
            "success": False,
            "error": f"Invalid firmware file ID format: {firmware_file_id}. Expected UUID format."
        }
    
    # Validate execute_datetime format (YYYYMMDDHHDD)
    datetime_pattern = r'^\d{12}$'
    if not re.match(datetime_pattern, execute_datetime):
        return {
            "success": False,
            "error": f"Invalid execute_datetime format: {execute_datetime}. Expected format: YYYYMMDDHHDD"
        }
    
    # Validate transfer_datetime is in the future
    current_timestamp = int(datetime.now().timestamp() * 1000)
    if transfer_datetime <= current_timestamp:
        return {
            "success": False,
            "error": f"transfer_datetime must be in the future. Current: {current_timestamp}, Provided: {transfer_datetime}"
        }
    
    # Extract group ID from JWT token if not provided
    if not group_id:
        group_id = await _get_group_id_from_token()
        
    # Use fallback default group ID if extraction fails
    if not group_id:
        default_group_id = "6d167a66-9c03-b981-6e37-8770c76676be"
        group_id = default_group_id
        logger.warning(f"Using fallback default group ID: {default_group_id}")
    
    # Prepare payload for setUpdateReservation API
    payload = {
        "groupId": group_id,
        "deviceIds": device_ids,
        "fileId": firmware_file_id,
        "fileTransferTimestamp": transfer_datetime,
        "fileTransferTimeZone": timezone,
        "executeUpdateDateTime": execute_datetime,
        "isExclude": False
    }
    
    # Make API request to schedule firmware update
    api_result = await _make_api_call(
        endpoint="/rmm/fss/fwupd/setUpdateReservation",
        method="POST",
        payload=payload
    )
    
    if not api_result.get("success"):
        return {
            "success": False,
            "error": api_result.get("error", "Failed to schedule firmware update"),
            "endpoint": "/rmm/fss/fwupd/setUpdateReservation",
            "api_response": api_result
        }
    
    response_data = api_result.get("response_data", {})
    error_list = response_data.get("common", {}).get("errorList", [])
    
    # Check for API errors
    if error_list:
        return {
            "success": False,
            "error": "API returned errors",
            "error_details": error_list,
            "endpoint": "/rmm/fss/fwupd/setUpdateReservation"
        }
    
    # Format transfer datetime for display
    transfer_dt = datetime.fromtimestamp(transfer_datetime / 1000)
    
    # Format execute datetime for display
    execute_year = execute_datetime[:4]
    execute_month = execute_datetime[4:6]
    execute_day = execute_datetime[6:8]
    execute_hour = execute_datetime[8:10]
    execute_minute = execute_datetime[10:12]
    execute_formatted = f"{execute_year}-{execute_month}-{execute_day} {execute_hour}:{execute_minute}"
    
    schedule_summary = {
        "scheduled_devices": len(device_ids),
        "device_ids": device_ids,
        "firmware_file_id": firmware_file_id,
        "transfer_schedule": {
            "timestamp": transfer_datetime,
            "datetime": transfer_dt.isoformat(),
            "timezone": timezone
        },
        "execute_schedule": {
            "datetime_string": execute_datetime,
            "formatted": execute_formatted
        },
        "group_id": group_id,
        "group_id_source": "jwt_token" if group_id == await _get_group_id_from_token() else "parameter_or_fallback"
    }
    
    return {
        "success": True,
        "message": f"Successfully scheduled firmware update for {len(device_ids)} device(s)",
        "schedule": schedule_summary,
        "raw_response": response_data,
        "scheduled_at": datetime.now().isoformat()
    }

@mcp.tool(
    name="cancel_scheduled_update",
    description="Cancel scheduled firmware updates for specific devices. Removes any pending update reservations.",
)
async def cancel_scheduled_update(
    device_ids: List[str],
    group_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Cancel scheduled firmware updates for specified devices.
    
    Args:
        device_ids (List[str]): Array of target device IDs to cancel updates for
        group_id (Optional[str]): Group ID. If None, extracts from JWT token
    
    Returns:
        Dict containing cancellation result and validation details
    """
    # Validate device IDs format
    import re
    device_id_pattern = r'^mn=[A-Za-z0-9+/=]+:sn=[A-Za-z0-9+/=]+$'
    invalid_devices = []
    for device_id in device_ids:
        if not re.match(device_id_pattern, device_id):
            invalid_devices.append(device_id)
    
    if invalid_devices:
        return {
            "success": False,
            "error": f"Invalid device ID format: {invalid_devices}. Expected format: 'mn=<base64>:sn=<base64>'"
        }
    
    # Extract group ID from JWT token if not provided
    if not group_id:
        group_id = await _get_group_id_from_token()
        
    # Use fallback default group ID if extraction fails
    if not group_id:
        default_group_id = "6d167a66-9c03-b981-6e37-8770c76676be"
        group_id = default_group_id
        logger.warning(f"Using fallback default group ID: {default_group_id}")
    
    # Prepare payload for removeUpdateReservation API
    payload = {
        "groupId": group_id,
        "deviceIds": device_ids,
        "isExclude": False
    }
    
    # Make API request to cancel scheduled updates
    api_result = await _make_api_call(
        endpoint="/rmm/fss/fwupd/removeUpdateReservation",
        method="POST",
        payload=payload
    )
    
    if not api_result.get("success"):
        return {
            "success": False,
            "error": api_result.get("error", "Failed to cancel scheduled updates"),
            "endpoint": "/rmm/fss/fwupd/removeUpdateReservation",
            "api_response": api_result
        }
    
    response_data = api_result.get("response_data", {})
    error_list = response_data.get("common", {}).get("errorList", [])
    
    # Check for API errors
    if error_list:
        return {
            "success": False,
            "error": "API returned errors",
            "error_details": error_list,
            "endpoint": "/rmm/fss/fwupd/removeUpdateReservation"
        }
    
    cancellation_summary = {
        "cancelled_devices": len(device_ids),
        "device_ids": device_ids,
        "group_id": group_id,
        "group_id_source": "jwt_token" if group_id == await _get_group_id_from_token() else "parameter_or_fallback"
    }
    
    return {
        "success": True,
        "message": f"Successfully cancelled scheduled updates for {len(device_ids)} device(s)",
        "cancellation": cancellation_summary,
        "raw_response": response_data,
        "cancelled_at": datetime.now().isoformat()
    }

# Add a resource for the token file
@mcp.resource(uri="file://auth_token.json")
def get_token_file() -> str:
    """
    Resource providing access to the current token data file.
    
    Returns:
        String content of the auth_token.json file
    """
    try:
        if os.path.exists(token_manager.token_file):
            with open(token_manager.token_file, 'r') as f:
                token_data = json.load(f)
            return json.dumps(token_data, indent=2)
    except Exception as e:
        logger.error(f"Error reading token file: {e}")
    
    return json.dumps({"message": "No token data available"}, indent=2)



# Export for importable MCP server
__all__ = [
    "mcp",
    "TokenManager",
    "token_manager",
    "extract_auth_token",
    "make_api_request",
    "list_devices",
    "configure_ota_mode",
    "list_staged_firmware",
    "schedule_firmware_update",
    "cancel_scheduled_update",
    "get_token_file",
]
