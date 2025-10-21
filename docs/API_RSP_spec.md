# eSIM Remote SIM Provisioning (RSP) Client

## Overview

This Python client provides a comprehensive interface for interacting with the eSIM.plus Remote SIM Provisioning (RSP) platform. It supports a wide range of operations defined in the eSIM.plus RSP Interface Manual, including profile management, device management, and campaign operations.

## Features

- Full support for eSIM.plus RSP platform APIs
- Environment-based configuration (test and production)
- Robust error handling
- Logging support
- Retry mechanism for transient network issues
- Comprehensive method coverage for:
  - Profile management
  - Profile type management
  - Device management
  - Campaign management
  - Operator code management
  - Transaction logging

## Prerequisites

- Python 3.8+
- pip

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/esim-rsp-client.git
cd esim-rsp-client
```

2. Create a virtual environment (optional but recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root with the following structure:

```
# Test Environment Credentials
TEST_ACCESS_KEY=your_test_access_key
TEST_SECRET_KEY=your_test_secret_key
TEST_URL=https://rsp-xian.redteaready.cn

# Production Environment Credentials
PROD_ACCESS_KEY=your_prod_access_key
PROD_SECRET_KEY=your_prod_secret_key
PROD_URL=https://rsp-eu.esim.plus
```

## Usage Examples

### Basic Initialization

```python
from esim_rsp_client import ESIMRSPClient

# Initialize for test environment
client = ESIMRSPClient(environment='test')

# Initialize for production environment
# client = ESIMRSPClient(environment='prod')
```

### Retrieving Profile Information

```python
try:
    profile_info = client.get_profile_info("88845846546874987566")
    print(profile_info)
except RSPClientError as e:
    print(f"Error retrieving profile: {e}")
```

### Adding a Profile

```python
try:
    # Add profile using metadata
    profile_response = client.add_profile2(
        iccid="your_iccid",
        imsi="your_imsi",
        ki="your_ki",
        opc="your_opc",
        enc_aes_key="your_encrypted_aes_key"
    )
    print(profile_response)
except RSPClientError as e:
    print(f"Error adding profile: {e}")
```

### Creating a Campaign

```python
campaign_data = {
    "campaignName": "Test Campaign",
    "detail": "Campaign description",
    "profileTypeName": "your_profile_type"
}

try:
    campaign_response = client.create_campaign(campaign_data)
    print(campaign_response)
except RSPClientError as e:
    print(f"Error creating campaign: {e}")
```

## Error Handling

The client uses custom exceptions for different types of errors:

- `RSPClientError`: Base exception for RSP client errors
- `RSPClientRequestError`: Raised for API request-related errors
- `RSPClientAuthenticationError`: Raised for authentication issues

## Logging

The client uses Python's `logging` module. Configure logging in your application:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

[Specify your license, e.g., MIT License]

## Contact

[Your Name/Organization]

- Email: your.email@example.com
- Project Link: https://github.com/yourusername/esim-rsp-client

## Acknowledgments

- [eSIM.plus](https://www.esim.plus) for their Remote SIM Provisioning platform
- [Requests](https://docs.python-requests.org/en/master/) library
- [python-dotenv](https://github.com/theskumar/python-dotenv)
- [tenacity](https://github.com/jd/tenacity)
