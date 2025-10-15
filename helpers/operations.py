import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from dotenv import load_dotenv

from helpers.configuration import load_ini_config, load_json_config
from helpers.database.database_factory import DatabaseFactory
from helpers.database.postgresql_generic_crud import PostgresqlGenericCRUD
from helpers.utils import setup_logger

# Load environment variables from a .env file
load_dotenv()

# Setup logger
logger = setup_logger(__name__)

# Configuration Data Class
@dataclass
class ETLConfig:
    table: str
    table_control: str
    error_report: dict
    smtp_configs: dict
    report: dict
    sap_app: dict
    database: dict
    process: dict

def create_alert_message(title, start_date, all_success, any_partial):
    """
    Create an alert message based on the processing results.

    Args:
        title (str): The title of the alert.
        start_date (datetime): The start date of the processing period.
        all_success (bool): True if all processing tasks were successful.
        any_partial (bool): True if some processing tasks were successful.

    Returns:
        dict: A dictionary containing the alert type, title, and message
    """

    if all_success:
        return {
            'alert_type': 'success',
            'alert_title': title,
            'alert_message': f'O processo foi executado com sucesso em {start_date:%Y-%m-%d}. Favor verificar.'
        }
    elif any_partial:
        return {
            'alert_type': 'warning',
            'alert_title': title,
            'alert_message': f'O processo foi parcialmente executado em {start_date:%Y-%m-%d}. Verifique o log de execução.'
        }
    else:
        return {
            'alert_type': 'danger',
            'alert_title': title,
            'alert_message': 'Ocorreu um erro ao salvar os dados, favor verificar o log de execução.'
        }

def load_etl_config() -> ETLConfig:
    """
    Load the ETL configuration settings from the configuration files.
    Returns:
        ETLConfig: An instance of the ETLConfig data class with the loaded configuration settings.
    """

    db_config = load_ini_config("DATABASE")
    report = load_json_config().get("report")
    process = load_json_config().get("process")
    database = load_json_config().get("database")
    sap_app = load_json_config().get("sap_app")
    error_report = load_json_config().get("error_report")
    smtp_configs = load_ini_config("SMTP")

    return ETLConfig(
        table=db_config.get("table"),
        table_control=db_config.get("table_control"),
        error_report=error_report,
        smtp_configs=smtp_configs,
        report=report,
        sap_app=sap_app,
        database=database,
        process=process
    )

async def setup_db_connections():
    """
    Set up and establish connections to various databases used in the ETL process.
    Returns:
        Tuple containing:
        - Oracle connection and CRUD object
        - SQL Server connection and CRUD object
        - PostgreSQL connection and CRUD object (optional)
    """
    retries = 3  # Number of retries before giving up
    delay = 5  # Delay in seconds between retries
    for attempt in range(retries):
        try:
            logger.info("Setting up database connections...")
            config = {
                'dmkbi': load_ini_config("CVTVMDWBI"),
                'postgresql': load_ini_config("POSTGRESQL")
            }

            # Create the database connection objects
            dmkbi_db = DatabaseFactory.get_database('sqlserver', config['dmkbi'])
            postgresql_db = DatabaseFactory.get_database('postgresql', config['postgresql'])

            # Open all connections manually
            logger.info("Connecting to SQL Server, and PostgreSQL databases...")
            dmkbi_db.connect()
            postgresql_db.connect()

            # Create CRUD objects for respective databases
            postgresql_crud = PostgresqlGenericCRUD(postgresql_db)

            logger.info("Database connections established successfully.")
            return dmkbi_db, postgresql_db, postgresql_crud

        except Exception as e:
            logger.error(f"Error setting up database connections: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                raise  # Give up after the last attempt
            raise

# Ensure to close connections after the entire ETL process is done
def close_connections(dmkbi_db, postgresql_db):
    """
    Close connections to the Oracle, SQL Server, and PostgreSQL databases after the ETL process.
    """
    try:
        logger.info("Closing database connections...")
        if dmkbi_db:
            dmkbi_db.disconnect()
            logger.info("SQL Server connection closed.")
        if postgresql_db:
            postgresql_db.disconnect()
            logger.info("PostgreSQL connection closed.")
    except Exception as e:
        logger.error(f"Error closing connections: {e}")

@asynccontextmanager
async def managed_resources():
    """
    A context manager to manage resources for the ETL process.

    Yields:
        Tuple: A tuple containing the queue and CRUD objects for Oracle, SQL Server, and PostgreSQL databases.
    """

    # Initialize resources
    postgresql_db = None

    # Use try-finally to ensure cleanup of resources
    try:
        # Set up resources
        config = load_etl_config()

        # Setup database connections
        postgresql_db, postgresql_crud = await setup_db_connections() # Set up database connections

        # Return resources to the caller
        yield config, postgresql_crud, (postgresql_db,)

    finally:

        # Close all connections
        if all((postgresql_db)):
            logger.info("Closing all database connections...")
            close_connections(postgresql_db) # Close database connections

def get_last_processed_date(postgresql_crud, table: str, process_name: str) -> datetime:
    """
    Get the last processed date from the control table.

    Args:
        postgresql_crud: PostgreSQL CRUD handler

    Returns:
        datetime: The last processed date, or None if no record exists
    """
    try:
        logger.info("Getting last processed date from control table")

        yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)

        # Query the control table to get the last processed date
        result = postgresql_crud.read(
            table,
            ['last_processed_date'],
            where="process_name = %s",
            params=(process_name,)
        )

        if result and result[0].get('last_processed_date'):
            last_date = datetime.strptime(result[0]['last_processed_date'], '%Y-%m-%d')
            logger.info(f"Last processed date retrieved: {last_date}")
            # Return the day after the last processed date
            return last_date + timedelta(days=1)
        else:
            logger.warning("No last processed date found, using default start date")
            # Return a default date if no record exists
            return yesterday  # Default start date

    except Exception as e:
        logger.error(f"Error retrieving last processed date: {e}")
        # Return a default date if an error occurs
        return yesterday  # Default start date

def update_last_processed_date(postgresql_crud, end_date, table: str, process_name: str) -> bool:
    """
    Update the last processed date in the control table.
    Args:
        postgresql_crud: PostgreSQL CRUD handler
        end_date (datetime): The date to set as last processed
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        logger.info(f"Updating last processed date to {end_date}")
        # Check if a record already exists
        result = postgresql_crud.read(
            table,
            ['id'],
            where="process_name = %s",
            params=(process_name,)
        )

        # Format the date as string in the expected format
        date_str = end_date.strftime('%Y-%m-%d')

        if result:
            # Update existing record
            success = postgresql_crud.update(
                table,
                {'last_processed_date': date_str, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                where="process_name = %s",
                params=(process_name,)
            )
        else:
            # Get next ID value from sequence
            id_result = postgresql_crud.execute_raw_query(f"SELECT nextval('{table}_id_seq')")
            next_id = id_result[0]['nextval']

            # Create new record with explicit ID
            success = postgresql_crud.create(
                table,
                [(
                    next_id,
                    process_name,
                    date_str,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                )],
                ['id', 'process_name', 'last_processed_date', 'created_at', 'updated_at']
            )

        return success
    except Exception as e:
        logger.error(f"Error updating last processed date: {e}")
        return False

def ensure_control_table_exists(postgresql_crud, table: str) -> None:
    """
    Ensure the ETL control table exists in the database.

    Args:
        postgresql_crud: PostgreSQL CRUD handler
        table: Name of the control table to create
    """
    try:
        # Check if table exists by trying to read from it
        postgresql_crud.read(table, ['id'], where="1=0")
        logger.info(f"ETL control table {table} already exists")
    except Exception:
        # Create the table if it doesn't exist
        logger.info(f"Creating ETL control table {table}")

        # Use an f-string to format the table name
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id SERIAL PRIMARY KEY,
            process_name VARCHAR(50) NOT NULL UNIQUE,
            last_processed_date DATE NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
        postgresql_crud.execute_raw_query(create_table_query)
        logger.info(f"ETL control table {table} created successfully")
