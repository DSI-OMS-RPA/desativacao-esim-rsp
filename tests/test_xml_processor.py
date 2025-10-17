# tests/test_xml_processor.py
import json
from pathlib import Path

import pytest

from core.xml_processor import XMLProcessor, XMLValidationError


def _write_tmp_xml(tmp_path: Path, content: str) -> str:
    p = tmp_path / "sample.xml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_parse_valid_xml_and_identify_esim(tmp_path):
    # XML com dois registos: um dentro do range (esim), outro fora
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <ListOfCvtNginPrepaidDataIo>
      <CvtNginPrepaidData>
        <ICCID>89238010000101567890</ICCID>
        <IMSI>625019101000001</IMSI>
        <MSISDN>23891234567</MSISDN>
        <StatusDate>2025-10-16T12:00:00</StatusDate>
      </CvtNginPrepaidData>
      <CvtNginPrepaidData>
        <ICCID>89238010000102000000</ICCID>
        <IMSI>625019101000002</IMSI>
        <MSISDN>23899876543</MSISDN>
        <StatusDate>2025-10-16T12:30:00</StatusDate>
      </CvtNginPrepaidData>
    </ListOfCvtNginPrepaidDataIo>
    """
    path = _write_tmp_xml(tmp_path, xml)

    # Definir range de eSIM que inclui o primeiro ICCID
    esim_range = type("ER", (), {"is_esim": lambda self, iccid: iccid == "89238010000101567890"})()

    processor = XMLProcessor(esim_range=esim_range)
    valid_records, invalid_records = processor.parse_file(path)

    assert len(valid_records) == 2
    assert len(invalid_records) == 0

    esims = processor.filter_esim_iccids(valid_records)
    assert len(esims) == 1
    assert esims[0].iccid == "89238010000101567890"
    assert esims[0].msisdn == "23891234567"
    assert esims[0].imsi == "625019101000001"


def test_parse_missing_iccid(tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <ListOfCvtNginPrepaidDataIo>
      <CvtNginPrepaidData>
        <IMSI>625019101000003</IMSI>
        <MSISDN>23890000000</MSISDN>
      </CvtNginPrepaidData>
    </ListOfCvtNginPrepaidDataIo>
    """
    path = _write_tmp_xml(tmp_path, xml)
    processor = XMLProcessor()  # default EsimRange not used here

    valid_records, invalid_records = processor.parse_file(path)
    assert len(valid_records) == 0
    assert len(invalid_records) == 1
    raw, reason = invalid_records[0]
    assert reason == "Missing ICCID"
    # raw deve conter o MSISDN e IMSI extraídos
    assert raw.get("MSISDN") == "23890000000"
    assert raw.get("IMSI") == "625019101000003"


def test_parse_non_numeric_iccid(tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <ListOfCvtNginPrepaidDataIo>
      <CvtNginPrepaidData>
        <ICCID>ABCDEF12345</ICCID>
        <IMSI>625019101000004</IMSI>
        <MSISDN>23891111111</MSISDN>
      </CvtNginPrepaidData>
    </ListOfCvtNginPrepaidDataIo>
    """
    path = _write_tmp_xml(tmp_path, xml)
    processor = XMLProcessor()

    valid_records, invalid_records = processor.parse_file(path)
    assert len(valid_records) == 0
    assert len(invalid_records) == 1
    raw, reason = invalid_records[0]
    assert reason == "ICCID not numeric"
    assert raw.get("ICCID") == "ABCDEF12345"


def test_extract_esim_list_from_file(tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <ListOfCvtNginPrepaidDataIo>
      <CvtNginPrepaidData>
        <ICCID>89238010000101567890</ICCID>
        <IMSI>625019101000005</IMSI>
        <MSISDN>23892222222</MSISDN>
      </CvtNginPrepaidData>
      <CvtNginPrepaidData>
        <ICCID>89238010000102000001</ICCID>
        <IMSI>625019101000006</IMSI>
        <MSISDN>23893333333</MSISDN>
      </CvtNginPrepaidData>
      <CvtNginPrepaidData>
        <ICCID>NOTNUM</ICCID>
      </CvtNginPrepaidData>
    </ListOfCvtNginPrepaidDataIo>
    """
    path = _write_tmp_xml(tmp_path, xml)

    # create an EsimRange that matches the first ICCID only
    class DummyRange:
        def is_esim(self, iccid):
            return iccid == "89238010000101567890"

    processor = XMLProcessor(esim_range=DummyRange())
    out = processor.extract_esim_list_from_file(path)

    assert isinstance(out, dict)
    assert out["total_records"] == 3
    assert out["valid_records"] == 2
    assert out["invalid_records"] == 1
    assert out["esim_count"] == 1
    assert out["esim_records"][0]["iccid"] == "89238010000101567890"
