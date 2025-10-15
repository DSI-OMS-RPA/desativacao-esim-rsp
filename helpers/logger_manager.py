import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


class LoggerManager:
    """
    LoggerManager sets up a logging system that logs messages to a file,
    with options to add console and rotating file handlers.

    Attributes:
        log_dir (str): Directory where log files will be saved.
        log_level (int): Logging level.
        log_filename (str): Generated log filename based on the current datetime.
        logger (logging.Logger): The logger instance for the class.
    """

    def __init__(self, log_dir='logs', log_level=logging.DEBUG):
        """
        Initializes the LoggerManager with the specified log directory and log level.

        Args:
            log_dir (str): Directory to save log files.
            log_level (int): Logging level (e.g., logging.DEBUG, logging.INFO).
        """
        self.log_dir = log_dir
        self.log_level = log_level
        self.log_filename = self.generate_log_filename()
        self.logger = None
        self.setup_logging()

    def generate_log_filename(self):
        """
        Generates a log filename based on the current datetime.

        Returns:
            str: The generated log filename.
        """
        return datetime.now().strftime(f'{self.log_dir}/agt003dsi_%Y%m%d%H%M%S.log')

    def setup_logging(self):
        """
        Sets up the logging configuration, ensuring the log directory exists
        and configuring the root logger to log messages to a file.
        """
        # Ensure the log directory exists
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # Configure the basic logging settings
        logging.basicConfig(
            level=self.log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

        # Create a file handler to log to a file
        file_handler = logging.FileHandler(self.log_filename)
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            '%Y-%m-%d %H:%M:%S'
        ))

        # Get the root logger and add the file handler to it
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

        # Assign the class logger
        self.logger = logging.getLogger(__name__)

    def get_logger(self, name=None):
        """
        Retrieves a logger by name or returns the default logger.

        Args:
            name (str): Optional name of the logger to retrieve.

        Returns:
            logging.Logger: The retrieved logger.
        """
        return logging.getLogger(name) if name else self.logger

    def add_console_handler(self):
        """
        Adds a console handler to the root logger to output log messages to the console.
        """
        console_handler = logging.StreamHandler()
        self.add_handler(console_handler, '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def add_rotating_file_handler(self, max_bytes=10485760, backup_count=5):
        """
        Adds a rotating file handler to the root logger to manage log file sizes.

        Args:
            max_bytes (int): Maximum file size in bytes before rotating.
            backup_count (int): Number of backup files to keep.
        """
        rotating_handler = RotatingFileHandler(
            self.log_filename, maxBytes=max_bytes, backupCount=backup_count
        )
        self.add_handler(
            rotating_handler, '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def add_handler(self, handler, format_str):
        """
        Adds a specified handler to the root logger with the given format.

        Args:
            handler (logging.Handler): The handler to add (e.g., console or file handler).
            format_str (str): The format string for the log messages.
        """
        handler.setLevel(self.log_level)
        handler.setFormatter(logging.Formatter(
            format_str, '%Y-%m-%d %H:%M:%S'))
        logging.getLogger().addHandler(handler)

    def get_log_filename(self):
        """
        Retrieves the generated log filename.

        Returns:
            str: The generated log filename.
        """
        return self.log_filename
