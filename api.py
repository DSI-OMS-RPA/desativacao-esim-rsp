import logging
import json
import os
import sys

# Add project root to path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import project modules
from core.esim_rsp_client import ESIMRSPClient, RSPClientError

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

        try:
            # Initialize the client
            client = ESIMRSPClient(environment='prod')
            logger.info("ESIM RSP Client initialized.")

            # Expire Order
            try:
                logger.info("Attempting to expire order...")
                expire_order = client.expire_order("89238010001010036214")
                logger.info(f"Expire order response: {json.dumps(expire_order, indent=2)}")
            except RSPClientError as e:
                logger.error(f"Profile expiration failed: {e}")

        except Exception as e:
            logger.critical(f"Unexpected error: {e}")

    except Exception as e:
        logger.critical(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
