# core/report_generator.py
"""
Report Generator for eSIM Deactivation Process

Generates CSV reports, summaries, and prepares email notifications.
"""

import csv
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Data class for individual ICCID processing results."""
    iccid: str
    imsi: Optional[str]
    msisdn: Optional[str]
    file_source: str
    timestamp: datetime
    status: str  # SUCCESS, FAILED, INVALID, SKIPPED
    api_response: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_attempts: int = 0
    processing_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV/JSON export."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['api_response'] = json.dumps(self.api_response) if self.api_response else None
        return data


@dataclass
class ProcessingStats:
    """Statistics for the entire processing run."""
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    total_records: int = 0
    total_esim: int = 0
    successful: int = 0
    failed: int = 0
    invalid: int = 0
    skipped: int = 0
    out_of_range: int = 0
    avg_processing_time_ms: float = 0
    total_processing_time_s: float = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_esim == 0:
            return 0.0
        return (self.successful / self.total_esim) * 100

    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate total processing duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class ReportGenerator:
    """
    Generates various report formats for the eSIM deactivation process.
    """

    def __init__(self, report_dir: str = "reports", retention_days: int = 30):
        """
        Initialize the Report Generator.

        Args:
            report_dir: Directory where reports will be saved
            retention_days: Number of days to retain old reports
        """
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.current_date = datetime.now()

        logger.info(f"ReportGenerator initialized with dir: {self.report_dir}")

    def generate_csv(self,
                    results: List[ProcessingResult],
                    filename: Optional[str] = None) -> str:
        """
        Generate a detailed CSV report of processing results.

        Args:
            results: List of processing results
            filename: Optional custom filename

        Returns:
            Path to the generated CSV file
        """
        if not filename:
            filename = f"desativacao_esim_{self.current_date:%Y%m%d_%H%M%S}.csv"

        csv_path = self.report_dir / filename

        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                if not results:
                    # Write empty file with headers only
                    fieldnames = ['iccid', 'imsi', 'msisdn', 'status', 'timestamp',
                                 'error_message', 'file_source']
                else:
                    # Get all unique fields from results
                    fieldnames = list(results[0].to_dict().keys())

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for result in results:
                    writer.writerow(result.to_dict())

            logger.info(f"CSV report generated: {csv_path}")
            return str(csv_path)

        except Exception as e:
            logger.error(f"Failed to generate CSV report: {e}")
            raise

    def generate_summary_table(self, results: List[ProcessingResult]) -> List[Dict[str, Any]]:
        """
        Generate summary data for email table.

        Args:
            results: List of processing results

        Returns:
            List of dictionaries with summary data in Portuguese
        """
        summary_data = {}

        for result in results:
            key = (result.file_source, result.status)
            if key not in summary_data:
                summary_data[key] = {
                    'Ficheiro': result.file_source,
                    'Estado': result.status,
                    'Quantidade': 0,
                    'Tempo': []
                }
            summary_data[key]['Quantidade'] += 1
            summary_data[key]['Tempo'].append(result.processing_time_ms or 0)

        # Calculate average processing time and format output
        table_data = []
        for data in summary_data.values():
            avg_time_ms = sum(data['Tempo']) / len(data['Tempo']) if data['Tempo'] else 0
            table_data.append({
                'Ficheiro': data['Ficheiro'],
                'Estado': data['Estado'],
                'Quantidade': data['Quantidade'],
                'Tempo Médio': self._format_time(avg_time_ms)
            })

        # Sort by file and status
        table_data.sort(key=lambda x: (x['Ficheiro'], x['Estado']))

        return table_data

    def generate_summary_csv(self,
                            results: List[ProcessingResult],
                            filename: Optional[str] = None) -> str:
        """
        Generate a summary CSV with aggregated statistics by status.

        Args:
            results: List of processing results
            filename: Optional custom filename

        Returns:
            Path to the generated summary CSV file
        """
        if not filename:
            filename = f"resumo_esim_{self.current_date:%Y%m%d_%H%M%S}.csv"

        csv_path = self.report_dir / filename

        # Aggregate by status and file
        summary_data = {}
        for result in results:
            key = (result.file_source, result.status)
            if key not in summary_data:
                summary_data[key] = {
                    'file': result.file_source,
                    'status': result.status,
                    'count': 0,
                    'iccids': []
                }
            summary_data[key]['count'] += 1
            summary_data[key]['iccids'].append(result.iccid)

        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['file', 'status', 'count', 'sample_iccids']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for data in summary_data.values():
                    row = {
                        'file': data['file'],
                        'status': data['status'],
                        'count': data['count'],
                        'sample_iccids': ', '.join(data['iccids'][:5])  # First 5 as sample
                    }
                    writer.writerow(row)

            logger.info(f"Summary CSV generated: {csv_path}")
            return str(csv_path)

        except Exception as e:
            logger.error(f"Failed to generate summary CSV: {e}")
            raise

    def calculate_stats(self,
                       results: List[ProcessingResult],
                       files_info: Optional[Dict[str, Any]] = None) -> ProcessingStats:
        """
        Calculate processing statistics from results.

        Args:
            results: List of processing results
            files_info: Optional information about processed files

        Returns:
            ProcessingStats object with calculated statistics
        """
        stats = ProcessingStats()

        if files_info:
            stats.total_files = files_info.get('total', 0)
            stats.processed_files = files_info.get('processed', 0)
            stats.failed_files = files_info.get('failed', 0)

        stats.total_records = len(results)

        # Count by status
        status_counts = Counter(r.status for r in results)
        stats.successful = status_counts.get('SUCCESS', 0)
        stats.failed = status_counts.get('FAILED', 0)
        stats.invalid = status_counts.get('INVALID', 0)
        stats.skipped = status_counts.get('SKIPPED', 0)
        stats.out_of_range = status_counts.get('OUT_OF_RANGE', 0)

        # eSIM specific
        stats.total_esim = stats.successful + stats.failed

        # Timing statistics
        if results:
            processing_times = [r.processing_time_ms for r in results if r.processing_time_ms > 0]
            if processing_times:
                stats.avg_processing_time_ms = sum(processing_times) / len(processing_times)
                stats.total_processing_time_s = sum(processing_times) / 1000

            # Get time range
            timestamps = [r.timestamp for r in results if r.timestamp]
            if timestamps:
                stats.start_time = min(timestamps)
                stats.end_time = max(timestamps)

        logger.info(f"Statistics calculated: {stats.total_records} records, "
                   f"{stats.success_rate:.1f}% success rate")

        return stats

    def generate_summary(self, stats: ProcessingStats) -> str:
        """
        Generate a text summary of processing statistics.

        Args:
            stats: Processing statistics

        Returns:
            Formatted text summary
        """
        duration_str = "N/A"
        if stats.duration:
            total_seconds = int(stats.duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        summary = f"""
╔══════════════════════════════════════════════════════════════╗
║           eSIM DEACTIVATION PROCESS - SUMMARY               ║
╚══════════════════════════════════════════════════════════════╝

📅 Date: {stats.start_time:%Y-%m-%d %H:%M:%S} to {stats.end_time:%H:%M:%S} if stats.start_time and stats.end_time else 'N/A'
⏱️  Duration: {duration_str}

FILES PROCESSED:
├─ Total Files: {stats.total_files}
├─ Processed: {stats.processed_files}
└─ Failed: {stats.failed_files}

RECORDS SUMMARY:
├─ Total Records: {stats.total_records:,}
├─ Total eSIM: {stats.total_esim:,}
├─ Out of Range: {stats.out_of_range:,}
└─ Invalid: {stats.invalid:,}

PROCESSING RESULTS:
├─ ✅ Successful: {stats.successful:,} ({stats.successful/max(stats.total_esim, 1)*100:.1f}%)
├─ ❌ Failed: {stats.failed:,} ({stats.failed/max(stats.total_esim, 1)*100:.1f}%)
└─ ⏭️  Skipped: {stats.skipped:,}

PERFORMANCE:
├─ Success Rate: {stats.success_rate:.1f}%
├─ Avg Processing Time: {stats.avg_processing_time_ms:.0f}ms per record
└─ Total Processing Time: {stats.total_processing_time_s:.1f}s

═══════════════════════════════════════════════════════════════
"""
        return summary

    def prepare_email_data(self,
                          stats: ProcessingStats,
                          results: List[ProcessingResult]) -> Dict[str, Any]:
        """
        Prepare data for email template.

        Args:
            stats: Processing statistics
            results: Processing results

        Returns:
            Dictionary with email template data
        """
        # Determine alert type based on success rate
        if stats.success_rate >= 95:
            alert_type = 'success'
            alert_title = 'Desativação de cartões eSIM concluída com sucesso.'
            alert_message = f'Processo concluído com taxa de sucesso de {stats.success_rate:.1f}%.'
        elif stats.success_rate >= 80:
            alert_type = 'warning'
            alert_title = 'Desativação de cartões eSIM concluída com avisos.'
            alert_message = f'Processo concluído com taxa de sucesso de {stats.success_rate:.1f}% - revisar itens com falha.'
        else:
            alert_type = 'danger'
            alert_title = 'Desativação de cartões eSIM falhou.'
            alert_message = f'Processo falhou com apenas {stats.success_rate:.1f}% de taxa de sucesso.'

        # Get sample of failed records for email
        failed_samples = []
        for r in results:
            if r.status == 'FAILED' and len(failed_samples) < 10:
                failed_samples.append({
                    'iccid': r.iccid,
                    'error': r.error_message or 'Erro desconhecido',
                    'file': r.file_source
                })

        # Generate summary table data
        table_data = self.generate_summary_table(results)

        email_data = {
            'alert_type': alert_type,
            'alert_title': alert_title,
            'alert_message': alert_message,
            'table_data': table_data,
            'environment': 'Production',
            'timestamp': datetime.now().isoformat(),
            'stats': {
                'total_files': stats.total_files,
                'processed_files': stats.processed_files,
                'total_records': stats.total_records,
                'total_esim': stats.total_esim,
                'successful': stats.successful,
                'failed': stats.failed,
                'success_rate': f"{stats.success_rate:.1f}%",
                'duration': str(stats.duration) if stats.duration else 'N/A'
            },
            'failed_samples': failed_samples,
            'action_button': {
                'text': 'View Full Report',
                'url': '#'  # Can be replaced with actual dashboard URL
            }
        }

        return email_data

    def cleanup_old_reports(self) -> Tuple[int, List[str]]:
        """
        Remove reports older than retention_days.

        Returns:
            Tuple of (number of files deleted, list of deleted filenames)
        """
        deleted_files = []
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        try:
            for file_path in self.report_dir.glob("*.csv"):
                # Check file modification time
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_date:
                    file_path.unlink()
                    deleted_files.append(file_path.name)
                    logger.debug(f"Deleted old report: {file_path.name}")

            if deleted_files:
                logger.info(f"Cleaned up {len(deleted_files)} old reports")

            return len(deleted_files), deleted_files

        except Exception as e:
            logger.error(f"Error cleaning up old reports: {e}")
            return 0, []

    def save_json_report(self,
                        results: List[ProcessingResult],
                        stats: ProcessingStats,
                        filename: Optional[str] = None) -> str:
        """
        Save a detailed JSON report with all data.

        Args:
            results: Processing results
            stats: Processing statistics
            filename: Optional custom filename

        Returns:
            Path to the generated JSON file
        """
        if not filename:
            filename = f"esim_report_{self.current_date:%Y%m%d_%H%M%S}.json"

        json_path = self.report_dir / filename

        report_data = {
            'generated_at': self.current_date.isoformat(),
            'statistics': asdict(stats),
            'results': [r.to_dict() for r in results]
        }

        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, default=str)

            logger.info(f"JSON report saved: {json_path}")
            return str(json_path)

        except Exception as e:
            logger.error(f"Failed to save JSON report: {e}")
            raise

    @staticmethod
    def _format_time(milliseconds: float) -> str:
        """
        Format processing time in human-readable format.

        Args:
            milliseconds: Time in milliseconds

        Returns:
            Formatted time string
        """
        if milliseconds < 1000:
            return f"{milliseconds:.0f}ms"

        seconds = milliseconds / 1000

        if seconds < 60:
            return f"{seconds:.1f}s"

        minutes = seconds / 60

        if minutes < 60:
            return f"{minutes:.1f}min"

        hours = minutes / 60
        return f"{hours:.1f}h"


# Utility function for quick report generation
def generate_quick_report(results: List[Dict[str, Any]],
                         output_dir: str = "reports") -> Dict[str, str]:
    """
    Quick utility to generate all report types at once.

    Args:
        results: List of result dictionaries
        output_dir: Output directory for reports

    Returns:
        Dictionary with paths to all generated reports
    """
    # Convert dicts to ProcessingResult objects
    processing_results = []
    for r in results:
        processing_results.append(ProcessingResult(
            iccid=r.get('iccid', ''),
            imsi=r.get('imsi'),
            msisdn=r.get('msisdn'),
            file_source=r.get('file_source', 'unknown'),
            timestamp=r.get('timestamp', datetime.now()),
            status=r.get('status', 'UNKNOWN'),
            api_response=r.get('api_response'),
            error_message=r.get('error_message'),
            retry_attempts=r.get('retry_attempts', 0),
            processing_time_ms=r.get('processing_time_ms', 0)
        ))

    generator = ReportGenerator(output_dir)

    # Generate all reports
    csv_path = generator.generate_csv(processing_results)
    summary_csv_path = generator.generate_summary_csv(processing_results)
    stats = generator.calculate_stats(processing_results)
    json_path = generator.save_json_report(processing_results, stats)

    return {
        'csv': csv_path,
        'summary_csv': summary_csv_path,
        'json': json_path,
        'text_summary': generator.generate_summary(stats)
    }
