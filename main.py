import logging
import json
from .core.esim_rsp_client import ESIMRSPClient, RSPClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    try:
        # Initialize the client
        client = ESIMRSPClient(environment='prod')

        # Demonstrate various API calls with error handling

        # 88845846546874987566 - Test Profile ID
        # 89238010001010016471 - Prod Profile ID

        # 1. Get Profile Information
        try:
            print("\n=== Retrieving Profile Information ===")
            profile_info = client.get_profile_info("89238010001010016471")
            print(json.dumps(profile_info, indent=2))
        except RSPClientError as e:
            logger.error(f"Profile info retrieval failed: {e}")

        # 2. List Profile Types
        try:
            print("\n=== Listing Profile Types ===")
            profile_types = client.list_profile_types()
            print(json.dumps(profile_types, indent=2))
        except RSPClientError as e:
            logger.error(f"Profile types listing failed: {e}")

        # 3. Get Profile State Statistics
        try:
            print("\n=== Retrieving Profile State Statistics ===")
            stats = client.get_profile_state_statistics(profile_type="Webapp_Prepaid")
            print(json.dumps(stats, indent=2))
        except RSPClientError as e:
            logger.error(f"Profile state statistics retrieval failed: {e}")

        # 4. List Operator Codes
        try:
            print("\n=== Listing Operator Codes ===")
            op_list = client.list_op()
            print(json.dumps(op_list, indent=2))
        except RSPClientError as e:
            logger.error(f"Operator codes listing failed: {e}")

        # 5. Device Blocklist
        try:
            print("\n=== Retrieving Device Blocklist ===")
            blocklist = client.list_device_blocklist()
            print(json.dumps(blocklist, indent=2))
        except RSPClientError as e:
            logger.error(f"Device blocklist retrieval failed: {e}")

    except Exception as e:
        logger.critical(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
