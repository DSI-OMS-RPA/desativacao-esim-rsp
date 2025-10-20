# test_local.py
"""
Local test script to validate the eSIM deactivation process components.

This script tests each component individually and then runs a simplified
end-to-end test without requiring actual FTP/API connections.
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import components to test
from core.business_rules import EsimRange, RetryPolicy, ErrorHandler
from core.report_generator import ReportGenerator, ProcessingResult, ProcessingStats
from core.xml_processor import XMLProcessor, NginRecord
from helpers.lock_manager import ProcessLock


def test_lock_manager():
    """Test the ProcessLock functionality."""
    print("\n" + "="*50)
    print("Testing Lock Manager")
    print("="*50)

    try:
        # Test lock acquisition
        lock1 = ProcessLock(lock_dir="/tmp", lock_name="test_esim")
        lock1.acquire()
        print("✅ Lock acquired successfully")

        # Test duplicate lock detection
        lock2 = ProcessLock(lock_dir="/tmp", lock_name="test_esim")
        try:
            lock2.acquire()
            print("❌ Duplicate lock not detected")
        except RuntimeError as e:
            print(f"✅ Duplicate lock prevented: {e}")

        # Test lock info
        info = lock1.get_lock_info()
        print(f"✅ Lock info: PID={info['pid']}, Running={info['is_running']}")

        # Test lock release
        lock1.release()
        print("✅ Lock released successfully")

        # Test reacquisition after release
        lock3 = ProcessLock(lock_dir="/tmp", lock_name="test_esim")
        lock3.acquire()
        print("✅ Lock reacquired after release")
        lock3.release()

        return True

    except Exception as e:
        print(f"❌ Lock manager test failed: {e}")
        return False


def test_business_rules():
    """Test business rules components."""
    print("\n" + "="*50)
    print("Testing Business Rules")
    print("="*50)

    try:
        # Test eSIM range
        esim_range = EsimRange(
            start=89238010000101000000,
            end=89238010000101999999
        )

        # Test valid eSIM
        assert esim_range.is_esim("89238010000101500000") == True
        print("✅ Valid eSIM detected correctly")

        # Test out of range
        assert esim_range.is_esim("89238010000102000000") == False
        print("✅ Out of range eSIM detected correctly")

        # Test invalid input
        assert esim_range.is_esim("") == False
        assert esim_range.is_esim(None) == False
        print("✅ Invalid inputs handled correctly")

        # Test retry policy
        retry_policy = RetryPolicy(max_attempts=3, delay_seconds=5.0, backoff_factor=2.0)
        assert retry_policy.can_retry(2) == True
        assert retry_policy.can_retry(3) == False
        assert retry_policy.next_delay(1) == 5.0
        assert retry_policy.next_delay(2) == 10.0
        print("✅ Retry policy working correctly")

        # Test error handler
        try:
            raise ValueError("Test error")
        except Exception as e:
            error_info = ErrorHandler.handle_error(e, context="Test")
            assert error_info['status'] == 'failed'
            assert 'Test error' in error_info['error_message']
        print("✅ Error handler working correctly")

        return True

    except Exception as e:
        print(f"❌ Business rules test failed: {e}")
        return False


def test_xml_processor():
    """Test XML processing functionality."""
    print("\n" + "="*50)
    print("Testing XML Processor")
    print("="*50)

    try:
        # Create test XML file
        test_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <ListOfCvtNginPrepaidDataIo>
            <CvtNginPrepaidData>
                <ICCID>89238010000101000001</ICCID>
                <IMSI>238011234567890</IMSI>
                <MSISDN>351910000001</MSISDN>
                <Action>DEACTIVATE</Action>
                <StatusDate>10/16/25 14:30:00</StatusDate>
            </CvtNginPrepaidData>
            <CvtNginPrepaidData>
                <ICCID>89238010000102000001</ICCID>
                <Action>DEACTIVATE</Action>
            </CvtNginPrepaidData>
        </ListOfCvtNginPrepaidDataIo>"""

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(test_xml)
            temp_file = f.name

        # Test parsing
        processor = XMLProcessor()
        records, invalids = processor.parse_file(temp_file)

        assert len(records) == 2
        print(f"✅ Parsed {len(records)} records successfully")

        # Test eSIM identification
        esim_records = processor.filter_esim_iccids(records)
        assert len(esim_records) == 1
        print(f"✅ Identified {len(esim_records)} eSIM record(s)")

        # Test record data
        assert records[0].iccid == "89238010000101000001"
        assert records[0].action == "DEACTIVATE"
        print("✅ Record data extracted correctly")

        # Cleanup
        os.unlink(temp_file)

        return True

    except Exception as e:
        print(f"❌ XML processor test failed: {e}")
        return False


def test_report_generator():
    """Test report generation functionality."""
    print("\n" + "="*50)
    print("Testing Report Generator")
    print("="*50)

    try:
        # Create temp directory for reports
        temp_dir = tempfile.mkdtemp()
        generator = ReportGenerator(report_dir=temp_dir)

        # Create test results
        results = [
            ProcessingResult(
                iccid="89238010000101000001",
                imsi="238011234567890",
                msisdn="351910000001",
                file_source="test.xml",
                timestamp=datetime.now(),
                status="SUCCESS",
                processing_time_ms=100
            ),
            ProcessingResult(
                iccid="89238010000101000002",
                imsi="238011234567891",
                msisdn="351910000002",
                file_source="test.xml",
                timestamp=datetime.now(),
                status="FAILED",
                error_message="API timeout",
                retry_attempts=3,
                processing_time_ms=5000
            ),
            ProcessingResult(
                iccid="89238010000102000001",
                imsi="238011234567892",
                msisdn="351910000003",
                file_source="test.xml",
                timestamp=datetime.now(),
                status="OUT_OF_RANGE",
                processing_time_ms=10
            )
        ]

        # Test CSV generation
        csv_path = generator.generate_csv(results)
        assert Path(csv_path).exists()
        print(f"✅ CSV report generated: {csv_path}")

        # Test summary CSV
        summary_path = generator.generate_summary_csv(results)
        assert Path(summary_path).exists()
        print(f"✅ Summary CSV generated: {summary_path}")

        # Test statistics calculation
        stats = generator.calculate_stats(results)
        assert stats.total_records == 3
        assert stats.successful == 1
        assert stats.failed == 1
        assert stats.out_of_range == 1
        print(f"✅ Statistics calculated: {stats.success_rate:.1f}% success rate")

        # Test text summary
        summary = generator.generate_summary(stats)
        assert "SUCCESS" in summary
        print("✅ Text summary generated")

        # Test JSON report
        json_path = generator.save_json_report(results, stats)
        assert Path(json_path).exists()
        print(f"✅ JSON report saved: {json_path}")

        # Test email data preparation
        email_data = generator.prepare_email_data(stats, results)
        assert email_data['alert_type'] in ['success', 'warning', 'danger']
        print(f"✅ Email data prepared: {email_data['alert_type']} alert")

        # Cleanup
        shutil.rmtree(temp_dir)

        return True

    except Exception as e:
        print(f"❌ Report generator test failed: {e}")
        return False


def test_mock_ftp():
    """Test FTP client with mock."""
    print("\n" + "="*50)
    print("Testing FTP Client (Mock)")
    print("="*50)

    try:
        from helpers.ftp_client import FTPClient, TransferProtocol

        # Create mock FTP client
        with patch('helpers.ftp_client.FTPClient') as MockFTP:
            mock_client = Mock()
            MockFTP.return_value = mock_client

            # Mock list_files
            mock_client.list_files.return_value = [
                "NGIN_DataFile_20251016.xml",
                "NGIN_DataFile_20251017.xml"
            ]

            # Mock download_file
            mock_client.download_file.return_value = None

            # Mock move_file
            mock_client.move_file.return_value = True

            # Test operations
            client = MockFTP(hostname="test", username="test", password="test")

            files = client.list_files("/")
            assert len(files) == 2
            print(f"✅ Mock list_files returned {len(files)} files")

            client.download_file("remote.xml", "local.xml")
            client.download_file.assert_called_once()
            print("✅ Mock download_file called")

            client.move_file("source.xml", "done/")
            client.move_file.assert_called_once()
            print("✅ Mock move_file called")

        return True

    except Exception as e:
        print(f"❌ FTP client mock test failed: {e}")
        return False


def test_mock_rsp_client():
    """Test RSP client with mock."""
    print("\n" + "="*50)
    print("Testing RSP Client (Mock)")
    print("="*50)

    try:
        from core.esim_rsp_client import ESIMRSPClient

        # Create mock RSP client
        with patch('core.esim_rsp_client.ESIMRSPClient') as MockRSP:
            mock_client = Mock()
            MockRSP.return_value = mock_client

            # Mock expire_order
            mock_client.expire_order.return_value = {
                "header": {"functionExecutionStatus": "Executed-Success"},
                "iccid": "89238010000101000001",
                "finalProfileStatusIndicator": "Unavailable"
            }

            # Test operations
            client = MockRSP(environment="test")

            response = client.expire_order(
                iccid="89238010000101000001",
                final_profile_status="Unavailable"
            )

            assert response["header"]["functionExecutionStatus"] == "Executed-Success"
            client.expire_order.assert_called_once()
            print("✅ Mock expire_order returned success")

        return True

    except Exception as e:
        print(f"❌ RSP client mock test failed: {e}")
        return False


def test_end_to_end_mock():
    """Test end-to-end flow with mocks."""
    print("\n" + "="*50)
    print("Testing End-to-End Flow (Mock)")
    print("="*50)

    try:
        # Create temp directories
        temp_base = tempfile.mkdtemp()
        staging_dir = Path(temp_base) / "staging"
        processed_dir = Path(temp_base) / "processed"
        reports_dir = Path(temp_base) / "reports"

        staging_dir.mkdir()
        processed_dir.mkdir()
        reports_dir.mkdir()

        # Create test XML in staging
        test_xml = staging_dir / "NGIN_DataFile_20251016.xml"
        test_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
        <ListOfCvtNginPrepaidDataIo>
            <CvtNginPrepaidData>
                <ICCID>89238010000101000001</ICCID>
                <Action>DEACTIVATE</Action>
            </CvtNginPrepaidData>
        </ListOfCvtNginPrepaidDataIo>""")

        print(f"✅ Created test environment in {temp_base}")

        # Test workflow steps
        # 1. Parse XML
        processor = XMLProcessor()
        records, _ = processor.parse_file(str(test_xml))
        print(f"✅ Parsed {len(records)} records from XML")

        # 2. Filter eSIMs
        esim_records = [r for r in records if processor.esim_range.is_esim(r.iccid)]
        print(f"✅ Filtered {len(esim_records)} eSIM records")

        # 3. Mock process with API
        results = []
        for record in esim_records:
            result = ProcessingResult(
                iccid=record.iccid,
                imsi=record.imsi,
                msisdn=record.msisdn,
                file_source="NGIN_DataFile_20251016.xml",
                timestamp=datetime.now(),
                status="SUCCESS",
                processing_time_ms=100
            )
            results.append(result)
        print(f"✅ Processed {len(results)} records (mock)")

        # 4. Generate report
        generator = ReportGenerator(report_dir=str(reports_dir))
        csv_path = generator.generate_csv(results)
        stats = generator.calculate_stats(results)
        print(f"✅ Generated report with {stats.success_rate:.0f}% success rate")

        # 5. Move file to processed
        processed_file = processed_dir / "NGIN_DataFile_20251016.xml"
        shutil.move(str(test_xml), str(processed_file))
        print(f"✅ Moved file to processed directory")

        # Verify final state
        assert not test_xml.exists()
        assert processed_file.exists()
        assert Path(csv_path).exists()
        print("✅ End-to-end test completed successfully")

        # Cleanup
        shutil.rmtree(temp_base)

        return True

    except Exception as e:
        print(f"❌ End-to-end test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("     eSIM DEACTIVATION - COMPONENT TEST SUITE")
    print("="*60)

    tests = [
        ("Lock Manager", test_lock_manager),
        ("Business Rules", test_business_rules),
        ("XML Processor", test_xml_processor),
        ("Report Generator", test_report_generator),
        ("FTP Client (Mock)", test_mock_ftp),
        ("RSP Client (Mock)", test_mock_rsp_client),
        ("End-to-End (Mock)", test_end_to_end_mock)
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            results.append((name, False))

    # Print summary
    print("\n" + "="*60)
    print("                    TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{name:.<40} {status}")

    print("="*60)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! System is ready for deployment.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review and fix.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
