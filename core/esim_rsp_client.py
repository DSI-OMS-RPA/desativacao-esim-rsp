from datetime import datetime
import os
import json
import uuid
import time
import hashlib
import logging
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class RSPClientError(Exception):
    """Base exception for RSP client errors."""

class RSPClientRequestError(RSPClientError):
    """Raised for errors during API requests."""

class RSPClientAuthenticationError(RSPClientError):
    """Raised for authentication issues."""

class ESIMRSPClient:
    """
    A comprehensive client for interacting with the eSIM.plus Remote SIM Provisioning (RSP) platform.

    This client supports various operations defined in the eSIM.plus RSP Interface Manual.
    """

    def __init__(self, environment: str = 'test', env_path: Optional[str] = None):
        """
        Initialize the RSP client with environment-specific configuration.

        Attributes:
            environment (str): 'test' or 'prod' to select the environment
            env_path (str, optional): Path to the .env file

        Raises:
            ValueError: If an invalid environment is provided
            RSPClientAuthenticationError: If authentication fails
            RSPClientRequestError: For other request-related errors

        Returns:
            None
        """

        # Carregar .env a partir de configs/.env por omissão
        if env_path:
            env_file = Path(env_path)
        else:
            project_root = Path(__file__).resolve().parent.parent
            env_file = project_root / "configs" / ".env"

        if env_file.exists():
            load_dotenv(dotenv_path=env_file)
            logger.info(f".env carregado a partir de: {env_file}")
        else:
            # fallback: carregar variáveis de ambiente do processo
            load_dotenv()  # tenta carregar do cwd se existir
            logger.warning(f".env não encontrado em {env_file}, carregado fallback padrão (cwd).")

        self.environment = environment
        # obtém credenciais (p.ex. TEST_ACCESS_KEY, TEST_SECRET_KEY, TEST_URL)
        self.access_key, self.secret_key, self.base_url = self._get_environment_config()

        # configurar política de retry local (valores por defeito)
        # preferível injetar esta policy de configs.json via rules_from_config
        from core.business_rules import get_default_rules
        _, retry_policy = get_default_rules()  # retorna (EsimRange, RetryPolicy)
        self.retry_policy = retry_policy

    def _get_environment_config(self) -> tuple:
        """
        Retrieve environment-specific configuration.

        :return: Tuple of (access_key, secret_key, base_url)
        :raises ValueError: If an invalid environment is provided
        """
        access_key = os.getenv(f"{self.environment.upper()}_ACCESS_KEY")
        secret_key = os.getenv(f"{self.environment.upper()}_SECRET_KEY")
        base_url = os.getenv(f"{self.environment.upper()}_URL")
        if not access_key or not secret_key or not base_url:
            raise ValueError(f"Missing credentials for {self.environment} environment.")
        return access_key, secret_key, base_url

    def _prepare_headers(self, body: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Prepare headers for API request with signature.

        :param body: Request body
        :return: Dictionary of headers
        """
        request_id = str(uuid.uuid4())
        timestamp = str(int(time.time() * 1000))

        body_raw = json.dumps(body) if body else ""
        data_str = f"{timestamp}{request_id}{body_raw}{self.secret_key}"
        signature = hashlib.sha256(data_str.encode()).hexdigest()

        return {
            "Content-Type": "application/json",
            "Access-Key": self.access_key,
            "Request-ID": request_id,
            "Timestamp": timestamp,
            "Sign-Method": "SHA256",
            "Signature": signature
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def _make_request(self, endpoint: str, method: str = 'POST', body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make a generic request to the RSP platform.

        :param endpoint: API endpoint
        :param method: HTTP method (default: POST)
        :param body: Request body
        :return: Response JSON
        """
        full_url = f"{self.base_url}{endpoint}"
        headers = self._prepare_headers(body)

        try:
            logger.info(f"Making {method} request to {full_url}")
            response = requests.request(method, full_url, headers=headers, json=body, timeout=10)
            response.raise_for_status()
            logger.info(f"Request succeeded: {response.status_code}")
            return response.json()
        except requests.RequestException as e:
            error_message = f"API request failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_message += f" | Response: {e.response.text}"
            logger.error(error_message)
            raise RSPClientRequestError(error_message)

    def get_order_info(self, iccid: str, eid: str = None, matchingId: str = None) -> Dict[str, Any]:
        """
        Retrieve information about a specific order.

        :param iccid: ICCID of the order
        :param eid: EID of the order
        :param matchingId: Matching ID of the order
        :return: Order information
        """
        endpoint = '/redtea/rsp2/es2plus/order/info'
        body = {
            "iccid": iccid,
            "eid": eid,
            "matchingId": matchingId,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "getOrderInfo"
            }
        }
        return self._make_request(endpoint, body=body)

    def get_profile_info(self, iccid: str) -> Dict[str, Any]:
        """
        Retrieve information about a specific profile.

        :param iccid: ICCID of the profile
        :return: Profile information
        """
        endpoint = '/redtea/rsp2/es2plus/profile/info'
        body = {
            "iccid": iccid,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "profileInfo"
            }
        }
        return self._make_request(endpoint, body=body)

    def get_profile_type_info(self, profile_type_name: str) -> Dict[str, Any]:
        """
        Retrieve information about a specific profile type.

        :param profile_type_name: Name of the profile type
        :return: Profile type information
        """
        endpoint = '/redtea/rsp2/es2plus/profileType/info'
        body = {
            "profileTypeName": profile_type_name,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "getProfileTypeInfo"
            }
        }
        return self._make_request(endpoint, body=body)

    def list_profile_types(self) -> Dict[str, Any]:
        """
        List all available profile types.

        :return: List of profile types
        """
        endpoint = '/redtea/rsp2/es2plus/profileType/list'
        body = {
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "listProfileType"
            }
        }
        return self._make_request(endpoint, body=body)

    def generate_by_profile_metadata(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a profile by providing metadata.

        :param profile_data: Profile metadata dictionary
        :return: Profile generation response
        """
        endpoint = '/redtea/rsp2/es2plus/order/generateByProfileMetadata'

        # Ensure required fields are present
        required_fields = ['iccid', 'imsi', 'ki', 'opc', 'encAesKey']
        for field in required_fields:
            if field not in profile_data:
                raise ValueError(f"Missing required field: {field}")

        # Prepare the full request body
        body = {
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "generateByProfileMetadata"
            },
            **profile_data
        }

        return self._make_request(endpoint, body=body)

    def batch_generate_by_profile_metadata(self, profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Batch generate profiles using metadata.

        :param profiles: List of profile metadata dictionaries
        :return: Batch generation response
        """
        endpoint = '/redtea/rsp2/es2plus/order/batchGenerateByProfileMetadata'

        body = {
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "batchGenerateByProfileMetadata"
            },
            "metadatas": profiles
        }

        return self._make_request(endpoint, body=body)

    def list_device_blocklist(self, page_num: int = 1, page_size: int = 20, block_type: int = 0) -> Dict[str, Any]:
        """
        Retrieve the list of blocked devices.

        :param page_num: Page number
        :param page_size: Number of results per page
        :param block_type: Blocking type (0: by EID, 1: by TAC)
        :return: List of blocked devices
        """
        endpoint = '/redtea/rsp2/es2plus/device/blocklist/list'
        body = {
            "pageParam": {
                "pageNum": page_num,
                "pageSize": page_size
            },
            "blockType": block_type,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "listDeviceBlocklist"
            }
        }

        return self._make_request(endpoint, body=body)

    def get_transaction_list(self, iccid: str) -> Dict[str, Any]:
        """
        Retrieve transaction logs for a specific ICCID.

        :param iccid: ICCID of the profile
        :return: List of transaction logs
        """
        endpoint = '/redtea/rsp2/es2plus/transaction/list'
        body = {
            "iccid": iccid,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "listTransaction"
            }
        }

        return self._make_request(endpoint, body=body)

    def get_health_check_status(self) -> Dict[str, Any]:
        """
        Check the health status of the RSP platform services.

        :return: Service health status
        """
        endpoint = '/redtea/rsp2/es2plus/health/status'

        body = {
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "healthCheck"
            }
        }

        return self._make_request(endpoint, body=body)

    def add_profile1(self, iccid: str, imsi: str, enc_aes_key: str, enc_upp: str, profile_type: str = "") -> Dict[str, Any]:
        """
        Endpoint for adding a profile using encrypted parameters

        :param iccid: ICCID of the SIM
        :param imsi: International Mobile Subscriber Identity
        :param enc_aes_key: Encrypted AES key
        :param enc_upp: Encrypted UPP parameters
        :param profile_type: Optional profile type
        :return: Response from the API
        """
        endpoint = '/redtea/rsp2/es2plus/profile/addByUpp'
        body = {
            "iccid": iccid,  # Unique identifier for the SIM
            "imsi": imsi,  # International Mobile Subscriber Identity
            "encAesKey": enc_aes_key,  # Encrypted AES key
            "encUpp": enc_upp,  # Encrypted UPP parameters
            "profileType": profile_type,  # Optional profile type
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),  # Unique request identifier
                "functionCallIdentifier": "addByUpp"  # Function call identifier
            }
        }
        return self._make_request(endpoint, body=body)

    def add_profile2(self, iccid: str, imsi: str, ki: str, opc: str, enc_aes_key: str, profile_type: str = "") -> Dict[str, Any]:
        """
        Endpoint for adding a profile using metadata
        """
        endpoint = '/redtea/rsp2/es2plus/profile/addByMeta'
        body = {
            "iccid": iccid,
            "imsi": imsi,
            "ki": ki,  # Key Identifier
            "opc": opc,  # Operator Code
            "encAesKey": enc_aes_key,
            "profileType": profile_type,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "addByMeta"
            }
        }
        return self._make_request(endpoint, body=body)

    def update_profile_param(self, iccid: str, param_key_value_list: List[Dict[str, str]], enc_aes_key: str = "") -> Dict[str, Any]:
        """
        Endpoint for updating profile parameters
        """
        endpoint = '/redtea/rsp2/es2plus/profile/updateParam'
        body = {
            "iccid": iccid,
            "paramKeyValueList": param_key_value_list,  # List of parameters to update
            "encAesKey": enc_aes_key,  # Optional encrypted AES key
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "updateParam"
            }
        }
        return self._make_request(endpoint, body=body)

    def get_profile_state_statistics(self, profile_type: str = "", state: str = "") -> Dict[str, Any]:
        """
        Endpoint for retrieving profile state statistics
        """
        endpoint = '/redtea/rsp2/es2plus/profile/getProfileStateStatistics'
        body = {
            "profileType": profile_type,  # Optional profile type filter
            "state": state,  # Optional state filter
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "getProfileStateStatistics"
            }
        }
        return self._make_request(endpoint, body=body)

    def add_profile_type(self, name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Endpoint for adding a new profile type
        """
        endpoint = '/redtea/rsp2/es2plus/profileType/add'
        body = {
            "name": name,  # Name of the profile type
            **parameters,  # Additional parameters for the profile type
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "AddProfileType"
            }
        }
        return self._make_request(endpoint, body=body)

    def update_profile_type(self, name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Endpoint for updating an existing profile type
        """
        endpoint = '/redtea/rsp2/es2plus/profileType/update'
        body = {
            "name": name,  # Name of the profile type
            **parameters,  # Parameters to update
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "UpdateProfileType"
            }
        }
        return self._make_request(endpoint, body=body)

    def add_op(self, name: str, op_type: str, enc_op: str) -> Dict[str, Any]:
        """
        Endpoint for adding a new Operator Code (OP)
        """
        endpoint = '/redtea/rsp2/es2plus/mno/op/add'
        body = {
            "name": name,  # Name of the OP
            "type": op_type,  # Type of the OP
            "encOP": enc_op,  # Encrypted Operator Code
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "AddOP"
            }
        }
        return self._make_request(endpoint, body=body)

    def delete_op(self, name: str) -> Dict[str, Any]:
        """
        Endpoint for deleting an existing Operator Code (OP)
        """
        endpoint = '/redtea/rsp2/es2plus/mno/op/delete'
        body = {
            "name": name,  # Name of the OP to delete
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "DeleteOP"
            }
        }
        return self._make_request(endpoint, body=body)

    def list_op(self) -> Dict[str, Any]:
        """
        Endpoint for listing all Operator Codes (OPs)
        """
        endpoint = '/redtea/rsp2/es2plus/mno/op/list'
        body = {
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "ListOP"
            }
        }
        return self._make_request(endpoint, body=body)

    def add_device_to_blocklist(self, device_id: str, block_reason: str) -> Dict[str, Any]:
        """
        Endpoint for adding a device to the blocklist
        """
        endpoint = '/redtea/rsp2/es2plus/device/blocklist/add'
        body = {
            "deviceId": device_id,  # Identifier for the device
            "blockReason": block_reason,  # Reason for blocking the device
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "AddDeviceToBlocklist"
            }
        }
        return self._make_request(endpoint, body=body)

    def delete_device_from_blocklist(self, device_id: str) -> Dict[str, Any]:
        """
        Endpoint for removing a device from the blocklist
        """
        endpoint = '/redtea/rsp2/es2plus/device/blocklist/delete'
        body = {
            "deviceId": device_id,  # Identifier for the device to remove
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "DeleteDeviceFromBlocklist"
            }
        }
        return self._make_request(endpoint, body=body)

    def create_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Endpoint for creating a new campaign
        """
        endpoint = '/redtea/rsp2/es2plus/campaign/create'
        body = {
            **campaign_data,  # Campaign-specific data
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "CreateCampaign"
            }
        }
        return self._make_request(endpoint, body=body)

    def get_transaction_list(self, iccid: str) -> Dict[str, Any]:
        """
        Endpoint for retrieving transaction logs for a specific ICCID
        """
        endpoint = '/redtea/rsp2/es2plus/transaction/list'
        body = {
            "iccid": iccid,  # ICCID of the SIM
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "GetTransactionList"
            }
        }
        return self._make_request(endpoint, body=body)

    def download_order(self, iccid: str) -> Dict[str, Any]:
        """
        Download/allocate a profile order for an AVAILABLE profile.
        Initiates a new profile download order on RSP platform.

        :param iccid: ICCID of the profile to download
        :return: Response containing order information and execution status
        :raises RSPClientRequestError: If API request fails
        """
        endpoint = '/redtea/rsp2/es2plus/downloadOrder'
        body = {
            "iccid": iccid,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "downloadOrder"
            }
        }

        logger.info(f"[DownloadOrder] Initiating download order for ICCID={iccid}")
        response = self._make_request(endpoint=endpoint, method='POST', body=body)
        logger.info(f"[DownloadOrder] Success for ICCID={iccid}")

        return response

    def expire_order(self, iccid: str, final_status: str = "Unavailable", matchingId: Optional[str] = None, eid: Optional[str] = None) -> Dict[str, Any]:
        """
        Chama o endpoint ExpireOrder para marcar o perfil como 'Unavailable' ou 'Available'.
        Usa retry manual baseado em self.retry_policy para maior controlo e logging.

        :param iccid: ICCID do perfil a expirar (string)
        :param final_status: 'Unavailable' (default) ou 'Available'
        :param matchingId: (opcional) matchingId do order, se disponível
        :param eid: (opcional) EID do eUICC
        :return: dicionário com resultado (status, attempts, http_status, response)
        """
        endpoint = "/redtea/rsp2/es2plus/order/expire"
        payload = {
            "iccid": iccid,
            "finalProfileStatusIndicator": final_status,
            "header": {
                "functionRequesterIdentifier": str(uuid.uuid4()),
                "functionCallIdentifier": "expireOrder"
            }
        }
        # adicionar campos condicionais se fornecidos
        if matchingId:
            payload["matchingId"] = matchingId
        if eid:
            payload["eid"] = eid

        attempts = 0
        last_exception = None
        start_ts = datetime.utcnow().isoformat() + "Z"

        while True:
            attempts += 1
            try:
                logger.info(f"[ExpireOrder] ICCID={iccid} attempt={attempts} payload={payload}")
                # Usa o _make_request existente para juntar headers e fazer a request
                response = self._make_request(endpoint=endpoint, method='POST', body=payload)
                # Log estruturado do sucesso
                result = {
                    "iccid": iccid,
                    "status": "success",
                    "attempts": attempts,
                    "http_status": 200,
                    "response": response,
                    "start_ts": start_ts,
                    "end_ts": datetime.utcnow().isoformat() + "Z"
                }
                logger.info(f"[ExpireOrder] Success ICCID={iccid} attempts={attempts}")
                return result

            except Exception as exc:
                last_exception = exc
                logger.warning(f"[ExpireOrder] ICCID={iccid} attempt={attempts} failed: {exc}")

                # se ainda é permitido retentar
                if self.retry_policy.can_retry(attempts):
                    delay = self.retry_policy.next_delay(attempts)
                    logger.info(f"[ExpireOrder] ICCID={iccid} retrying in {delay:.1f}s (attempt {attempts+1})")
                    time.sleep(delay)
                    continue
                else:
                    # Registo final de falha e retorno com erro estruturado
                    payload_err = {
                        "iccid": iccid,
                        "status": "failed",
                        "attempts": attempts,
                        "http_status": None,
                        "error": str(last_exception),
                        "start_ts": start_ts,
                        "end_ts": datetime.utcnow().isoformat() + "Z"
                    }
                    logger.error(f"[ExpireOrder] ICCID={iccid} failed after {attempts} attempts: {last_exception}")
                    # opcional: lançar exceção ou devolver payload_err — escolhe conforme política
                    return payload_err
