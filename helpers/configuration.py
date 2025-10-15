import json
import logging
from configparser import ConfigParser, NoOptionError, NoSectionError
from pathlib import Path
from typing import Optional
from dotenv import dotenv_values
import os

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent.parent  # Go up one level from core/ to project root

# Define configuration file paths relative to project root
JSON_PATH = SCRIPT_DIR / 'configs' / 'configs.json'
INI_PATH = SCRIPT_DIR / 'configs' / 'config.ini'
DOTENV_PATH = SCRIPT_DIR / 'configs' / '.env'

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_json_config(config_file: Optional[str] = None) -> dict:
    """
    Load static variables from a JSON configuration file.

    Args:
        config_file (str, optional): The path to the configuration file.
            If None, the default 'config/configs.json' will be used.

    Returns:
        dict: A dictionary containing the static variables.

    Raises:
        FileNotFoundError: If the configuration file is not found.
        ValueError: If the JSON format in the configuration file is invalid.
    """
    if config_file is None:
        config_file = JSON_PATH
    else:
        # If a specific file is provided, make it relative to config directory
        config_file = SCRIPT_DIR / 'config' / config_file

    try:
        with open(config_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError as e:
        logger.error(f"Configuration file '{config_file}' not found.")
        raise FileNotFoundError(f"Configuration file '{config_file}' not found.") from e
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in '{config_file}'.")
        raise ValueError(f"Invalid JSON format in '{config_file}'.") from e

def load_ini_config(section: str) -> dict:
    """
    Load all options from a section in an INI configuration file.

    Args:
        section (str): The section in the INI file to load.

    Returns:
        dict: A dictionary containing all options and their values from the specified section.

    Raises:
        FileNotFoundError: If the INI configuration file is not found.
        ValueError: If the section is not found.
    """
    if not INI_PATH.exists():
        logger.error(f"INI configuration file '{INI_PATH}' not found.")
        raise FileNotFoundError(f"INI configuration file '{INI_PATH}' not found.")

    conf = ConfigParser()
    conf.read(INI_PATH)

    if not conf.has_section(section):
        logger.error(f"Section '{section}' not found in '{INI_PATH}'.")
        raise ValueError(f"Section '{section}' not found in '{INI_PATH}'.")

    return dict(conf.items(section))

def load_env_config() -> dict:
    """
    Load environment variables from a .env file.

    Returns:
        dict: A dictionary of environment variables loaded from the .env file.

    Raises:
        FileNotFoundError: If the .env file is not found.
    """
    if not DOTENV_PATH.exists():
        logger.error(f"Environment file '{DOTENV_PATH}' not found.")
        raise FileNotFoundError(f"Environment file '{DOTENV_PATH}' not found.")

    env_vars = dotenv_values(DOTENV_PATH)
    return env_vars
