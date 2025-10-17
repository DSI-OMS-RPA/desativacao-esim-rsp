from functools import wraps
import time
from urllib.parse import urlunsplit
from jinja2 import Environment, FileSystemLoader
from ldap3 import Server, Connection, SUBTREE, ALL_ATTRIBUTES, SIMPLE
from datetime import datetime
from pprint import pprint

import psutil
from helpers.database.postgresql_client import PostgreSQLClient
from helpers.configuration import *
import subprocess
import win32api
import random
import string
import re
import os

from helpers.logger_manager import LoggerManager

def setup_logger(name: str) -> logging.Logger:
    """
    Sets up and returns a logger with the specified name.

    Args:
        name (str): The name of the logger.

    Returns:
        logging.Logger: Configured logger instance.
    """
    # Initialize the logger manager
    logger_manager = LoggerManager()

    # Get the logger with the specified name
    logger = logger_manager.get_logger(name)
    return logger

def generate_template(template, variables):
    """
    Generate a string by substituting variables into a template.

    Args:
        template (str): The template string with placeholders for variables.
        variables (dict): A dictionary containing the variable names and their values.

    Returns:
        str: The generated string with variables substituted.
    """
    return template.format(**variables)


def generate_password(length=8):
    """
    Generate a password that meets specific criteria.

    The password must:
    - Have a minimum length of 8 characters
    - Contain at least 1 lowercase letter
    - Contain at least 1 uppercase letter
    - Contain at least 1 digit (0-9)
    - Contain at least 1 special character ($,*,@,#,%,&,?,!)

    If the password starts with "?!" or "!", move these characters to the middle.

    Args:
    - length (int): The length of the password to generate (default is 8)

    Returns:
    - str: The generated password
    """
    special_characters = "$*@#%&?!"
    while True:
        password = ''.join(random.choices(string.ascii_letters + string.digits + special_characters, k=length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in special_characters for c in password)):
            # Move special characters from the beginning to the middle of the password, if present
            if password.startswith(("?", "!")):
                while password and password[0] in "?!":
                    middle = len(password) // 2
                    password = password[1:middle] + \
                        password[0] + password[middle:]
            return password

def convert_date(date_str):
    """
    Convert a date string from the format 'dd/mm/yyyy' to Portuguese format 'dd de Month'.

    Args:
    date_str (str): The date string in the format 'dd/mm/yyyy'.

    Returns:
    str: The date string in the format 'dd de Month' in Portuguese.
    """
    # Convert string to datetime object
    date_obj = datetime.strptime(date_str, "%d/%m/%Y")

    # Dictionary for translating months to Portuguese
    months_in_portuguese = {
        "January": "Janeiro", "February": "Fevereiro", "March": "Março",
        "April": "Abril", "May": "Maio", "June": "Junho",
        "July": "Julho", "August": "Agosto", "September": "Setembro",
        "October": "Outubro", "November": "Novembro", "December": "Dezembro"
    }

    # Formatting the date to 'dd de Month' format
    formatted_date = date_obj.strftime("%d de %B")

    # Extracting the month in English
    month_english = date_obj.strftime("%B")

    # Replacing the English month with the Portuguese equivalent
    return formatted_date.replace(month_english, months_in_portuguese[month_english])


def is_valid_email(email):
    """
    Validate an email address.

    Args:
        email (str): The email address to validate.

    Returns:
        bool: True if the email address is valid, False otherwise.
    """
    # Regex for validating an email address
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)


def is_image_file(filepath):
    """
    Check if a file is an image based on its extension.

    Parameters:
    - filepath: The path of the file to check.

    Returns:
    - True if the file is an image, False otherwise.
    """
    # Define a set of common image file extensions
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}

    # Extract the file extension and check if it is in the set
    _, ext = os.path.splitext(filepath)
    return ext.lower() in image_extensions


def json_to_html(json_data):
    """Converts JSON data to an HTML table.

    Args:
        json_data: A dictionary containing the JSON data or None.

    Returns:
        str: The HTML representation of the JSON data as a table.
    """

    if json_data is None:
        return "<html><body><h1>Error Report</h1><p>No data available to display.</p></body></html>"

    html = "<html><body><h1>Error Report</h1><table border='1'>"
    for key, value in json_data.items():
        html += f"<tr><th>{key}</th><td>{value}</td></tr>"
    html += "</table></body></html>"
    return html


async def get_ad_user(identity: str = None, email: str = None):
    """
    Retrieve and parse Active Directory user information.

    This function executes a PowerShell command to retrieve properties of an Active Directory user
    specified by their identity. The output is then parsed to extract key-value pairs from the data.

    The PowerShell output is decoded from bytes to a string using various encodings. The parsed data is returned as a dictionary of properties.

    Args:
    identity (str): The identity of the Active Directory user.

    Returns:
    dict: A dictionary containing the parsed user properties.

    Raises:
    Exception: If the PowerShell command execution fails or returns an error.
    """
    # Format the PowerShell command with the provided identity
    if identity:
        command = f"Get-ADUser -Identity {identity} -Properties *"
    elif email:
        command = f"Get-ADUser -Filter {{Emailaddress -eq '{email}'}} -Properties *"
    else:
        raise Exception("No identity or email provided.")

    # Execute the PowerShell command
    result = subprocess.run(
        ["powershell", "-Command", command], capture_output=True)

    if result.returncode != 0:
        error_message = result.stderr.decode('utf-8', errors='replace')
        raise Exception(f"Error: {error_message}")

    # List of possible encodings
    encodings = ['utf-8', 'windows-1252', 'iso-8859-1', 'cp850']

    # Try decoding with different encodings
    for encoding in encodings:
        try:
            output = result.stdout.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise Exception("Failed to decode output with known encodings.")

    # Split the output into lines and parse it into a dictionary
    lines = output.strip().split('\n')
    parsed_data = {}
    for line in lines:
        parts = line.split(':', 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            parsed_data[key] = value

    return parsed_data

def get_user_info(crud: PostgreSQLClient, email_address=None, identity=None):
    """
    Fetches user information from an LDAP server based on the provided email address or identity.

    Args:
        crud: PostgreSQLClient: An instance of the PostgreSQLClient class.
        email_address (str, optional): The email address of the user. Defaults to None.
        identity (str, optional): The identity of the user. Defaults to None.

    Returns:
        dict: A dictionary containing the user information, including 'cn', 'displayName', 'email', 'employeeID', 'company', 'mobile', 'mobilePhone', and 'department'. Returns None if no user is found.

    Raises:
        None
    """

    # Load configuration settings
    config = load_json_config()

    # database configs
    database = config['database']
    table = database['ldap']['table']
    ldap_where = database['ldap']['where']

    # Fetch data from the specified table and where clause using an function call
    where_clause = ldap_where['clause']
    where_params = (ldap_where['params'],)
    columns = ['username', 'password', 'url', 'port']
    ldap = crud.read(table, columns, where=where_clause, params=where_params)
    if not ldap:
        return None

    # Get configuration settings
    ip_address = ldap[0]["url"]
    port = int(ldap[0]["port"])
    base_dn = 'OU=cvt.cv,DC=cvt,DC=cv'
    ad_user = ldap[0]["username"]
    ad_password = ldap[0]["password"]

    # Join IP address and port into LDAP URL
    ad_server = urlunsplit(('ldap', f"{ip_address}:{port}", '', '', ''))

    # Connect to the AD server with specified username and password
    server = Server(ad_server, get_info=ALL_ATTRIBUTES)
    connection = Connection(
        server, user=ad_user, password=ad_password, authentication=SIMPLE, auto_bind=True)

    # Search for the specific user using the mail attribute
    if email_address is not None:
        search_filter = f'(mail={email_address})'
    else:
        search_filter = f'(SamAccountName={identity})'

    attributes = ['cn', 'displayName', 'Company', 'mail', 'SamAccountName', 'mobile', 'mobilePhone', 'Department', 'userAccountControl']

    # Perform the search
    connection.search(search_base=base_dn, search_filter=search_filter, search_scope=SUBTREE, attributes=attributes)

    # Return the first entry found
    if connection.entries:
        first_entry = connection.entries[0]
        user_info = {
            "cn": str(first_entry.cn),
            "displayName": str(first_entry.displayName),
            "email": str(first_entry.mail),
            "employeeID": str(first_entry.SamAccountName),
            "company": str(first_entry.Company),
            "mobile": str(first_entry.mobile),
            "mobilePhone": str(first_entry.mobilePhone),
            "department": str(first_entry.Department).split("/")[1] if len(str(first_entry.Department).split("/")) > 1 else None
        }

        # Parse userAccountControl attribute to get Enabled and LockedOut status
        user_account_control = int(first_entry['userAccountControl'].value)
        # Check if the account is enabled
        user_info['enabled'] = not bool(user_account_control & 2)
        # Check if the account is locked out
        user_info['lockedOut'] = bool(user_account_control & 16)

    else:
        user_info = None

    # Disconnect from the AD server
    connection.unbind()

    return user_info


def run_application(software):
    """
    Search for and run an application on the system.
    This function searches for the specified software on all available drives and runs it if found.
    It also measures the time taken to find and run the software.

    Args:
        software (str): The name of the software to search for and run.

    Returns:
        bool: True if the software is found and run successfully, False otherwise.
    """

    logger = setup_logger(__name__)

    # Function to search a drive for the software
    def search_drive(drive, software):
        for root, dirs, files in os.walk(drive):
            if software in files:
                return os.path.join(root, software)
        return None

    # Function to check if the process is running
    def is_process_running(process_name):
        for proc in psutil.process_iter(['pid', 'name']):
            if process_name.lower() in proc.info['name'].lower():
                return True
        return False

    # Check if the software is already running
    if is_process_running(software):
        logger.info(f"{software} is already running.")
        return True

    # Measure the start time
    start_time = time.time()

    # Get all available drives
    drives = win32api.GetLogicalDriveStrings().split('\000')[:-1]

    # Search each drive sequentially
    for drive in drives:
        software_path = search_drive(drive, software)
        if software_path:
            # Measure the end time
            end_time = time.time()
            elapsed_time = end_time - start_time

            logger.info(f"{software} found at {software_path}. Starting {software}...")
            subprocess.Popen(software_path)
            logger.info(f"Time taken to find and open {software}: {elapsed_time:.2f} seconds")
            return True

    # Measure the end time if not found
    end_time = time.time()
    elapsed_time = end_time - start_time
    logger.warning(f"{software} not found.")
    logger.info(f"Time taken to search for {software}: {elapsed_time:.2f} seconds")
    return False

def find_by_field_value(data_list, field, value_to_find):
    """
    Searches for a dictionary in a list of dictionaries where a specified field has a specific value.
    If no dictionary with the specified value is found, it returns the dictionary where the field value is None.

    Parameters:
    data_list (list): List of dictionaries to search through.
    field (str): The field name to search in each dictionary.
    value_to_find (any): The value to search for in the specified field.

    Returns:
    dict: The dictionary with the specified field value, or the one with the field value as None.
    """
    # Define the fallback dictionary with the field value as None
    fallback = next((item for item in data_list if item[field] is None), None)

    # Search for the dictionary with the given field value
    result = next((item for item in data_list if item[field] == value_to_find), fallback)

    return result


# Function to generate the HTML alert
def generate_alert(alert_type, alert_title, alert_message, data_list=None, alert_link=None):
    """
    Generate an HTML alert message using a Jinja template.

    Args:
        alert_type (str): The type of alert (e.g., 'warning', 'danger', 'info', 'success').
        alert_title (str): The title of the alert message.
        alert_message (str): The main content of the alert message.
        data_list (list, optional): A list of dictionaries to display as additional data.
        alert_link (str, optional): A link to include in the alert message.

    Returns:
        str: An HTML string representing the alert message.
    """

    # Set the color based on the type of alert
    if alert_type == 'success':
        alert_color = '#28a745'  # Green to success
    elif alert_type == 'warning':
        alert_color = '#ffc107'  # Yellow for warning
    elif alert_type == 'danger':
        alert_color = '#dc3545'  # Red for error
    else:
        alert_color = '#333333'  # Standard color if the type is unknown

    # Load the Jinja template for the alert
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('alert_template.html')

    # Render the template with the provided data
    html_output = template.render(
        title='Alerta de Processos ETL',
        alert_type=alert_type,
        alert_title=alert_title,
        alert_message=alert_message,
        data_list=data_list,
        alert_link=alert_link,
        alert_color=alert_color
    )

    return html_output

def timed(func):
    """
    Decorator for logging the execution time of a function.

    This decorator measures the time it takes for the decorated function to run and logs the duration.

    Args:
        func (function): The function to be decorated.

    Returns:
        function: A wrapped version of the original function that logs execution time.

    Example:
        @timed
        def process_data():
            # Function logic
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()  # Record start time
        result = func(*args, **kwargs)  # Execute the function
        elapsed_time = time.time() - start_time  # Calculate elapsed time
        logging.info(f"{func.__name__} took {elapsed_time:.2f} seconds")  # Log execution time
        return result  # Return the result of the function
    return wrapper

def robust_retry(max_retries=3, delay=1, backoff=2, max_delay=None, jitter=0.5, exceptions=(Exception,), logger=None, on_failure=None):
    """
    Decorator for retrying a function with exponential backoff and optional jitter.

    Args:
        max_retries (int): Maximum number of retry attempts. Default is 3.
        delay (int or float): Initial delay between retries in seconds. Default is 1.
        backoff (int or float): Factor by which the delay is multiplied after each retry. Default is 2.
        max_delay (int or float): Maximum delay between retries in seconds. If None, no limit. Default is None.
        jitter (int or float): Random jitter added to delay (to avoid retry synchronization). Default is 0.5.
        exceptions (tuple): Tuple of exception classes to catch and retry on. Default is (Exception,).
        logger (logging.Logger): Logger instance for logging. Default is None, which will use the root logger.
        on_failure (callable): Optional callback function executed after final retry failure. Default is None.

    Returns:
        function: A wrapped version of the original function with retry logic.

    Raises:
        Exception: Reraise the last exception encountered if max_retries is exceeded.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            log = logger or logging  # Use provided logger or root logger

            while attempt < max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    log.error(f"Attempt {attempt} failed for {func.__name__} with args={args}, kwargs={kwargs}. Error: {e}")

                    if attempt >= max_retries:
                        log.error(f"Max retries exceeded for function {func.__name__}")
                        if on_failure:
                            on_failure(e, *args, **kwargs)  # Call failure handler
                        raise

                    # Add random jitter to avoid synchronized retries
                    jitter_value = random.uniform(0, jitter)
                    sleep_time = current_delay + jitter_value

                    # Cap the sleep time if max_delay is specified
                    if max_delay:
                        sleep_time = min(sleep_time, max_delay)

                    log.info(f"Retrying in {sleep_time:.2f} seconds (attempt {attempt}/{max_retries})...")
                    time.sleep(sleep_time)
                    current_delay *= backoff  # Exponentially increase the delay

        return wrapper
    return decorator

