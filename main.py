# main.py
"""
Main Orchestrator for eSIM Deactivation Process

Complete implementation of the eSIM deactivation workflow:
1. Lock management
2. FTP file discovery and download
3. XML parsing and validation
4. eSIM identification and filtering
5. Batch processing with RSP API
6. Report generation and email notification
7. Cleanup and retention management
"""

import fnmatch
import os
import sys
import shutil
import logging
import time
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# Add project root to path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import project modules
from core.esim_rsp_client import ESIMRSPClient, RSPClientError
from core.xml_processor import XMLProcessor, NginRecord
from core.business_rules import get_default_rules
from core.report_generator import ReportGenerator, ProcessingResult
from helpers.lock_manager import ProcessLock
from helpers.ftp_client import FTPClient, TransferProtocol
from helpers.logger_manager import LoggerManager
from helpers.email_sender import EmailSender
from helpers.exception_handler import ExceptionHandler
from helpers.configuration import load_json_config, load_ini_config, load_env_config
from helpers.database import DatabaseFactory, PostgresqlGenericCRUD


# Configure main logger
logger = logging.getLogger(__name__)


@dataclass
class ProcessConfig:
    """Configuration for the deactivation process."""
    process_name: str = "Desativação de Cartões eSIM - RSP"
    batch_size: int = 10
    rate_limit_sleep: float = 1.0
    success_threshold: float = 0.95
    retention_days: int = 7
    staging_dir: str = "staging"
    processed_dir: str = "processed"
    reports_dir: str = "reports"
    ftp_root_path: str = "/SIEBEL/NGIN"
    ftp_done_folder: str = "done"
    file_pattern: str = "NGIN_DataFile_*.xml"
    environment: str = "prod"  # test or prod
    env_path: str = "configs/.env"
    no_files_alert: Dict[str, Any] = None
    enable_database: bool = False
    enable_email: bool = True


class ESIMDeactivationOrchestrator:
    """
    Main orchestrator for the eSIM deactivation process.
    Coordinates all components and manages the complete workflow.
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the orchestrator with configuration."""
        self.start_time = datetime.now()

        # Setup logging
        self.logger_manager = LoggerManager()
        self.logger = logging.getLogger(__name__)

        self.logger.info("="*60)
        self.logger.info("Starting eSIM Deactivation Process")
        self.logger.info(f"Process started at: {self.start_time}")
        self.logger.info("="*60)

        # Load configurations
        self._load_configurations(config_path)

        # Initialize components
        self._initialize_components()

        # Process statistics
        self.all_results: List[ProcessingResult] = []
        self.files_processed = []
        self.files_failed = []

    def _load_configurations(self, config_path: Optional[str] = None):
        """Load all configuration files."""
        try:
            # Load JSON config
            self.json_config = load_json_config(config_path)
            self.email_config = self.json_config.get("report", {})

            # Load INI configs
            self.ftp_config = load_ini_config("FTP")
            self.smtp_config = load_ini_config("SMTP")

            # Load environment variables
            self.env_config = load_env_config()

            # Create process configuration
            process_cfg = self.json_config.get("process", {})
            self.config = ProcessConfig(
                process_name=process_cfg.get("name", "Desativação de Cartões eSIM - RSP"),
                batch_size=process_cfg.get("batch_size", 10),
                rate_limit_sleep=process_cfg.get("rate_limit_sleep", 1.0),
                success_threshold=process_cfg.get("success_threshold", 0.95),
                retention_days=process_cfg.get("retention_days", 7),
                staging_dir=self.json_config.get("paths", {}).get("staging", "staging"),
                processed_dir=self.json_config.get("paths", {}).get("processed", "processed"),
                reports_dir=self.json_config.get("paths", {}).get("reports", "reports"),
                ftp_root_path=self.ftp_config.get("path", "/SIEBEL/NGIN"),
                ftp_done_folder=self.ftp_config.get("done_folder", "done"),
                file_pattern=process_cfg.get("file_pattern", "NGIN_DataFile_*.xml"),
                environment=self.env_config.get("environment", "prod"),
                env_path=process_cfg.get("env_path", "configs/.env"),
                no_files_alert=self.json_config.get("no_files_alert", {}),
                enable_database=process_cfg.get("enable_database", False),
                enable_email=process_cfg.get("enable_email", True)
            )

            self.logger.info(f"Configuration loaded: {self.config}")

        except Exception as e:
            self.logger.error(f"Failed to load configurations: {e}")
            raise

    def _initialize_components(self):
        """Initialize all necessary components."""
        try:
            # Create required directories
            for dir_path in [self.config.staging_dir, self.config.processed_dir, self.config.reports_dir]:
                Path(dir_path).mkdir(parents=True, exist_ok=True)

            # Initialize business rules
            self.esim_range, self.retry_policy = get_default_rules()

            # Initialize FTP client
            self.ftp_client = FTPClient(
                hostname=self.ftp_config["hostname"],
                username=self.ftp_config["username"],
                password=self.ftp_config["password"],
                port=int(self.ftp_config.get("port", 21)),
                protocol=TransferProtocol.FTP if self.ftp_config.get("protocol", "FTP") == "FTP" else TransferProtocol.SFTP,
                use_passive_mode=self.ftp_config.get("passive_mode", "true").lower() == "true"
            )

            # Initialize RSP client
            self.rsp_client = ESIMRSPClient(
                environment=self.config.environment,
                env_path=self.config.env_path
            )

            # Initialize XML processor
            self.xml_processor = XMLProcessor(esim_range=self.esim_range)

            # Initialize report generator
            self.report_generator = ReportGenerator(
                report_dir=self.config.reports_dir,
                retention_days=self.config.retention_days
            )

            # Initialize email sender if enabled
            if self.config.enable_email:
                self.email_sender = EmailSender(self.smtp_config)
            else:
                self.email_sender = None

            # Initialize database if enabled
            if self.config.enable_database:
                db_config = load_ini_config("POSTGRESQL")
                db = DatabaseFactory.get_database('postgresql', db_config)
                db.connect()
                self.db_crud = PostgresqlGenericCRUD(db)
            else:
                self.db_crud = None

            # Initialize exception handler
            if self.email_sender and self.db_crud:
                error_config = self.json_config.get("error_report", {})
                self.exception_handler = ExceptionHandler(
                    crud=self.db_crud,
                    email_sender=self.email_sender,
                    config=error_config
                )
            else:
                self.exception_handler = None

            self.logger.info("All components initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            raise

    def _clean_processed_folder(self):
        """Clean the processed folder at the start of execution."""
        try:
            # Files to preserve during cleanup
            PRESERVE_FILES = {'.gitignore', '.gitkeep', '.ignore'}

            processed_path = Path(self.config.processed_dir)
            if processed_path.exists():
                for file in processed_path.glob("*"):
                    if file.is_file() and file.name not in PRESERVE_FILES:
                        file.unlink()
                        self.logger.debug(f"Deleted: {file}")
            self.logger.info(f"Cleaned processed folder: {self.config.processed_dir}")
        except Exception as e:
            self.logger.error(f"Error cleaning processed folder: {e}")

    def _discover_files(self) -> List[str]:
        """
        Discover XML files in FTP server.

        Returns:
            List of file paths to process (sorted by date in filename)
        """
        try:
            self.logger.info("Discovering files on FTP server...")

            # List files in the directory (returns full paths)
            remote_files = self.ftp_client.list_files(self.config.ftp_root_path, only_files=True)

            # Use the configured glob pattern directly (e.g. "NGIN_DataFile_*.xml")
            pattern = self.config.file_pattern

            # Match against the filename (basename) using fnmatch (supports globs)
            matched = [f for f in remote_files if fnmatch.fnmatch(os.path.basename(f), pattern)]

            # Optional: sort by date embedded in filename (assumes format NGIN_DataFile_YYYYMMDD.xml)
            def _date_key(path: str):
                name = os.path.splitext(os.path.basename(path))[0] # -> "NGIN_DataFile_20251009"
                parts = name.rsplit('_', 1)
                return parts[1] if len(parts) == 2 else name

            matched.sort(key=_date_key)

            self.logger.info(f"Found {len(matched)} files to process")
            for f in matched:
                self.logger.debug(f"  - {f}")

            return matched

        except Exception as e:
            self.logger.error(f"Failed to discover files: {e}")
            return []

    def _download_file(self, remote_file: str) -> Optional[str]:
        """
        Download a file from FTP to staging directory.

        Args:
            remote_file: Remote file path

        Returns:
            Local file path if successful, None otherwise
        """
        try:
            filename = os.path.basename(remote_file)
            local_path = os.path.join(self.config.staging_dir, filename)

            self.logger.info(f"Downloading: {remote_file}")
            self.ftp_client.download_file(remote_file, local_path)

            # Verify download
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                self.logger.info(f"Downloaded successfully: {local_path}")
                return local_path
            else:
                self.logger.error(f"Download verification failed: {local_path}")
                return None

        except Exception as e:
            self.logger.error(f"Failed to download {remote_file}: {e}")
            return None

    def _process_xml_file(self, xml_path: str) -> Tuple[List[NginRecord], List[Any]]:
        """
        Parse and validate XML file.

        Args:
            xml_path: Path to local XML file

        Returns:
            Tuple of (valid records, invalid records)
        """
        try:
            self.logger.info(f"Processing XML: {xml_path}")
            records, invalids = self.xml_processor.parse_file(xml_path)

            self.logger.info(f"Parsed {len(records)} valid records, {len(invalids)} invalid")
            return records, invalids

        except Exception as e:
            self.logger.error(f"Failed to process XML {xml_path}: {e}")
            return [], []

    def _filter_deactivations(self, records: List[NginRecord]) -> List[NginRecord]:
        """
        Filter records for DEACTIVATE action and eSIM range.

        Args:
            records: List of all records

        Returns:
            List of eSIM records to deactivate
        """
        deactivations = []
        out_of_range = 0
        other_actions = 0

        for record in records:
            # Check if action is DEACTIVATE
            if record.action and record.action.upper() == "DEACTIVATE":
                # Check if ICCID is in eSIM range
                if self.esim_range.is_esim(record.iccid):
                    deactivations.append(record)
                else:
                    out_of_range += 1
            else:
                other_actions += 1
        self.logger.info(f"Filtered records: {len(deactivations)} eSIM deactivations, "
                        f"{out_of_range} out of range, {other_actions} other actions")

        return deactivations

    def _process_batch(self, batch: List[NginRecord], file_source: str) -> List[ProcessingResult]:
        """
        Process a batch of ICCIDs through the RSP API.

        Args:
            batch: List of records to process
            file_source: Source file name

        Returns:
            List of processing results
        """
        results = []

        for record in batch:
            start_time = time.time()
            result = ProcessingResult(
                iccid=record.iccid,
                imsi=record.imsi,
                msisdn=record.msisdn,
                file_source=file_source,
                timestamp=datetime.now(),
                status="PENDING",
                retry_attempts=0
            )

            try:
                # Retry loop
                for attempt in range(1, self.retry_policy.max_attempts + 1):
                    try:
                        self.logger.info(
                            f"Attempting to deactivate ICCID {record.iccid} "
                            f"(attempt {attempt}/{self.retry_policy.max_attempts})"
                        )

                        response = self.rsp_client.expire_order(iccid=record.iccid)
                        result.retry_attempts = attempt
                        result.api_response = response

                        # Extract business status from nested response structure
                        exec_status = response.get("response", {}).get("header", {}).get("functionExecutionStatus", {})
                        status = exec_status.get("status")

                        if status == "Executed-Success":
                            result.status = "SUCCESS"
                            result.success_reason = "DEACTIVATED"
                            self.logger.info(
                                f"Successfully deactivated ICCID {record.iccid} - "
                                f"profile marked as unavailable"
                            )
                            break

                        elif status == "Failed":
                            status_data = exec_status.get("statusCodeData", {})
                            subject_code = status_data.get('subjectCode', '')
                            reason_code = status_data.get('reasonCode', '')
                            error_code = f"{subject_code}/{reason_code}"
                            error_msg = status_data.get("message", "Unknown error")

                            # Business case: Expire Order not Exist (8.2.1/3.3)
                            # Interpretation: The order to expire doesn't exist because
                            # the profile is already in an expired/unavailable state
                            if error_code == "8.2.1/3.3":
                                result.status = "SUCCESS"
                                result.success_reason = "ALREADY_EXPIRED"
                                self.logger.info(
                                    f"ICCID {record.iccid}: Expire order not found [{error_code}] - "
                                    f"profile already expired or unavailable (treated as success)"
                                )
                                break

                            # Other business errors - retry
                            else:
                                result.error_message = f"[{error_code}] {error_msg}"
                                self.logger.error(
                                    f"Business error for ICCID {record.iccid}: "
                                    f"[{error_code}] {error_msg}"
                                )

                                if attempt >= self.retry_policy.max_attempts:
                                    result.status = "FAILED"
                                    self.logger.error(
                                        f"Max retries reached for ICCID {record.iccid}"
                                    )
                                    break
                                else:
                                    delay = self.retry_policy.next_delay(attempt)
                                    self.logger.warning(
                                        f"Retrying ICCID {record.iccid} in {delay}s..."
                                    )
                                    time.sleep(delay)

                        else:
                            # Status is None or unexpected value
                            result.status = "FAILED"
                            result.error_message = f"Unexpected API status: {status}"
                            self.logger.error(
                                f"Unexpected status '{status}' for ICCID {record.iccid}. "
                                f"Response keys: {list(response.keys())}"
                            )
                            break

                    except RSPClientError as e:
                        result.retry_attempts = attempt

                        if attempt >= self.retry_policy.max_attempts:
                            result.status = "FAILED"
                            result.error_message = f"RSP Client Error: {str(e)}"
                            self.logger.error(
                                f"Failed to expire ICCID {record.iccid} after "
                                f"{attempt} attempts: {e}"
                            )
                        else:
                            delay = self.retry_policy.next_delay(attempt)
                            self.logger.warning(
                                f"RSP error for ICCID {record.iccid} (attempt {attempt}), "
                                f"retrying in {delay}s: {e}"
                            )
                            time.sleep(delay)

            except Exception as e:
                result.status = "FAILED"
                result.error_message = f"Unexpected error: {str(e)}"
                self.logger.error(
                    f"Unexpected error processing ICCID {record.iccid}: {e}",
                    exc_info=True
                )

            # Log final outcome
            result.processing_time_ms = int((time.time() - start_time) * 1000)

            # Enhanced logging with success reason
            if result.status == "SUCCESS" and result.success_reason:
                self.logger.info(
                    f"Finished processing ICCID {record.iccid}: "
                    f"status={result.status} ({result.success_reason}), "
                    f"attempts={result.retry_attempts}, time={result.processing_time_ms}ms"
                )
            else:
                self.logger.info(
                    f"Finished processing ICCID {record.iccid}: "
                    f"status={result.status}, attempts={result.retry_attempts}, "
                    f"time={result.processing_time_ms}ms"
                )
            self.logger.info(f"{'='*80}")

            results.append(result)

        return results

    def _process_file(self, remote_file: str, local_file: str) -> Tuple[bool, List[ProcessingResult]]:
        """
        Process a single file completely.

        Args:
            remote_file: Remote file path
            local_file: Local file path

        Returns:
            Tuple of (success, results)
        """
        file_results = []
        filename = os.path.basename(remote_file)

        try:
            # Parse XML
            records, invalids = self._process_xml_file(local_file)

            # Add invalid records to results
            for invalid_data, error in invalids:
                file_results.append(ProcessingResult(
                    iccid=invalid_data.get('iccid', 'UNKNOWN'),
                    imsi=invalid_data.get('imsi'),
                    msisdn=invalid_data.get('msisdn'),
                    file_source=filename,
                    timestamp=datetime.now(),
                    status="INVALID",
                    error_message=error
                ))

            # Filter for deactivations
            deactivations = self._filter_deactivations(records)

            if not deactivations:
                self.logger.warning(f"No eSIM deactivations found in {filename}")
                return True, file_results

            # Remove duplicates
            unique_iccids = {}
            for record in deactivations:
                if record.iccid not in unique_iccids:
                    unique_iccids[record.iccid] = record
            deactivations = list(unique_iccids.values())

            self.logger.info(f"Processing {len(deactivations)} unique eSIM deactivations")

            # Process in batches
            for i in range(0, len(deactivations), self.config.batch_size):
                batch = deactivations[i:i + self.config.batch_size]

                self.logger.info(f"Processing batch {i//self.config.batch_size + 1} "
                               f"({len(batch)} records)")

                batch_results = self._process_batch(batch, filename)
                file_results.extend(batch_results)

                # Rate limiting between batches
                if i + self.config.batch_size < len(deactivations):
                    time.sleep(self.config.rate_limit_sleep)

            # Calculate success rate
            total_esim = len([r for r in file_results if r.status in ["SUCCESS", "FAILED"]])
            successful = len([r for r in file_results if r.status == "SUCCESS"])

            if total_esim > 0:
                success_rate = successful / total_esim
                self.logger.info(f"File {filename} success rate: {success_rate:.1%}")

                return success_rate >= self.config.success_threshold, file_results
            else:
                return True, file_results

        except Exception as e:
            self.logger.error(f"Error processing file {filename}: {e}")
            return False, file_results

    def _move_file_to_done(self, remote_file: str) -> bool:
        """
        Move file to done folder on FTP server.

        Args:
            remote_file: Remote file path

        Returns:
            True if successful, False otherwise
        """
        try:
            dest_path = f"{self.config.ftp_root_path}/{self.config.ftp_done_folder}"
            self.logger.info(f"Moving {remote_file} to {dest_path}")

            self.ftp_client.move_file(remote_file, dest_path)
            self.logger.info(f"Successfully moved {remote_file} to done folder")
            return True

        except Exception as e:
            self.logger.error(f"Failed to move {remote_file} to done: {e}")
            return False

    def _generate_reports(self) -> Dict[str, str]:
        """
        Generate all reports.

        Returns:
            Dictionary with report paths
        """
        try:
            # Calculate statistics
            files_info = {
                'total': len(self.files_processed) + len(self.files_failed),
                'processed': len(self.files_processed),
                'failed': len(self.files_failed)
            }
            stats = self.report_generator.calculate_stats(self.all_results, files_info)

            # Generate reports
            csv_path = self.report_generator.generate_csv(self.all_results)
            summary_csv = self.report_generator.generate_summary_csv(self.all_results)
            json_path = self.report_generator.save_json_report(self.all_results, stats)
            text_summary = self.report_generator.generate_summary(stats)

            # Print summary to console
            print(text_summary)

            return {
                'csv': csv_path,
                'summary_csv': summary_csv,
                'json': json_path,
                'text_summary': text_summary,
                'stats': stats
            }

        except Exception as e:
            self.logger.error(f"Failed to generate reports: {e}")
            return {}

    def _send_email_report(self, reports: Dict[str, Any]) -> bool:
        """
        Send email report with attachments.

        Args:
            reports: Dictionary with report information

        Returns:
            True if successful, False otherwise
        """
        if not self.config.enable_email or not self.email_sender:
            self.logger.info("Email notifications disabled")
            return True

        try:
            stats = reports.get('stats')
            email_data = self.report_generator.prepare_email_data(stats, self.all_results)

            # Add attachments
            attachments = []
            if reports.get('csv'):
                attachments.append(reports['csv'])
            if reports.get('summary_csv'):
                attachments.append(reports['summary_csv'])

            # Send email
            success = self.email_sender.send_template_email(
                report_config=self.email_config,
                alert_type=email_data['alert_type'],
                alert_title=email_data['alert_title'],
                alert_message=email_data['alert_message'],
                table_data=email_data.get('table_data'),
                environment=email_data['environment'],
                timestamp=email_data['timestamp'],
                attachment_paths=attachments
            )

            if success:
                self.logger.info("Email report sent successfully")
            else:
                self.logger.error("Failed to send email report")

            return success

        except Exception as e:
            self.logger.error(f"Error sending email report: {e}")
            return False

    def _cleanup_staging(self):
        """Clean up staging directory."""
        try:

            # Files to preserve during cleanup
            PRESERVE_FILES = {'.gitignore', '.gitkeep', '.ignore'}

            staging_path = Path(self.config.staging_dir)
            for file in staging_path.glob("*"):
                if file.is_file() and file.name not in PRESERVE_FILES:
                    file.unlink()
                    self.logger.debug(f"Deleted staging file: {file}")
            self.logger.info("Cleaned staging directory")
        except Exception as e:
            self.logger.error(f"Error cleaning staging directory: {e}")

    def run(self) -> int:
        """
        Run the complete deactivation process.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        lock = None
        exit_code = 0

        try:
            # 1. INITIALIZATION - Acquire lock (secure single instance execution)
            lock = ProcessLock()
            lock.acquire()
            self.logger.info("Process lock acquired")

            # Clean processed folder
            self._clean_processed_folder()

            # 2. FILE DISCOVERY
            remote_files = self._discover_files()

            if not remote_files:
                self.logger.warning("No files found to process")

                # Send alert to supplier team
                recipients = self.config.no_files_alert['recipients']

                if recipients:
                    try:
                        self.logger.info("Sending no files alert...")

                        # Change "to" field values with "recipients" list
                        self.email_config['to'] = recipients
                        self.email_config['cc'] = []
                        self.email_config['subject'] = f"[ALERTA] {self.config.process_name}"

                        # Prepare alert details
                        alert_type="warning"
                        alert_title=f"Nenhum ficheiro XML encontrado"
                        alert_message="Nenhum ficheiro foi encontrado no servidor FTP para processamento.</br>Por favor, verifique se os ficheiros foram disponibilizados corretamente."
                        summary_data = [
                            { "label": "Data/Hora", "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S') },
                            { "label": "Caminho FTP", "value": self.config.ftp_root_path },
                            { "label": "Padrão esperado", "value": self.config.file_pattern }
                        ]
                        environment=str(self.config.environment)
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                        # Send email
                        self.email_sender.send_template_email(
                            report_config=self.email_config,
                            alert_type=alert_type,
                            alert_title=alert_title,
                            alert_message=alert_message,
                            summary_data=summary_data,
                            environment=environment.upper(),
                            timestamp=timestamp
                        )
                        self.logger.info("No files alert sent successfully")
                    except Exception as e:
                        self.logger.error(f"Failed to send no files alert: {e}")

                return 0

            # 3. MAIN PROCESSING LOOP
            for remote_file in remote_files:
                self.logger.info(f"\n{'='*50}")
                self.logger.info(f"Processing file: {remote_file}")
                self.logger.info(f"{'='*50}")

                # Download file
                local_file = self._download_file(remote_file)
                if not local_file:
                    self.files_failed.append(remote_file)
                    continue

                # Process file
                success, file_results = self._process_file(remote_file, local_file)
                self.all_results.extend(file_results)

                if success:
                    # Move to done on FTP
                    if self._move_file_to_done(remote_file):
                        # Move local file to processed
                        processed_path = Path(self.config.processed_dir) / os.path.basename(local_file)
                        shutil.move(local_file, processed_path)
                        self.files_processed.append(remote_file)
                        self.logger.info(f"File {remote_file} processed successfully")
                    else:
                        self.files_failed.append(remote_file)
                else:
                    self.logger.warning(f"File {remote_file} failed processing threshold, not moved")
                    self.files_failed.append(remote_file)

            # 4. REPORT GENERATION
            self.logger.info("\n" + "="*50)
            self.logger.info("Generating reports...")
            reports = self._generate_reports()

            # 5. EMAIL NOTIFICATION
            if reports:
                self._send_email_report(reports)

            # 6. CLEANUP
            self._cleanup_staging()
            self.report_generator.cleanup_old_reports()

            # Determine exit code
            if self.files_failed and not self.files_processed:
                exit_code = 1
                self.logger.error("Process completed with errors - all files failed")
            elif self.files_failed:
                self.logger.warning("Process completed with partial success")
            else:
                self.logger.info("Process completed successfully")

        except Exception as e:
            exit_code = 1
            self.logger.error(f"Fatal error in main process: {e}")
            self.logger.error(traceback.format_exc())

            # Send error notification if possible
            if self.exception_handler:
                self.exception_handler.get_exception(e, send_email=True)

        finally:
            # Release lock
            if lock:
                lock.release()
                self.logger.info("Process lock released")

            # Log final status
            end_time = datetime.now()
            duration = end_time - self.start_time

            self.logger.info("\n" + "="*60)
            self.logger.info("Process Summary:")
            self.logger.info(f"  Start Time: {self.start_time}")
            self.logger.info(f"  End Time: {end_time}")
            self.logger.info(f"  Duration: {duration}")
            self.logger.info(f"  Files Processed: {len(self.files_processed)}")
            self.logger.info(f"  Files Failed: {len(self.files_failed)}")
            self.logger.info(f"  Total Records: {len(self.all_results)}")
            self.logger.info(f"  Exit Code: {exit_code}")
            self.logger.info("="*60)

            return exit_code


def main():
    """
    Entry point for the eSIM deactivation process.
    """
    try:
        # Create and run orchestrator
        orchestrator = ESIMDeactivationOrchestrator()
        exit_code = orchestrator.run()

        # Exit with appropriate code
        sys.exit(exit_code)

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
