# core/xml_processor.py
"""
XML Processor for NGIN/Siebel files

Provides:
- XMLProcessor: class that validates and parses the Siebel XML file
- Extracts ICCID, MSISDN, IMSI, Action, StatusDate, etc.
- Identifies which ICCIDs are eSIM according to the EsimRange from business_rules
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import xml.etree.ElementTree as ET

from core.business_rules import EsimRange, get_default_rules

logger = logging.getLogger(__name__)


class XMLProcessingError(Exception):
    """Base error for XML processing issues."""
    pass


class XMLValidationError(XMLProcessingError):
    """Raised when the XML doesn't match expected structure or is malformed."""
    pass


@dataclass
class NginRecord:
    iccid: str
    imsi: Optional[str] = None
    msisdn: Optional[str] = None
    action: Optional[str] = None
    status_date: Optional[datetime] = None
    raw: Dict[str, Any] = None


class XMLProcessor:
    """
    Processes a Siebel NGIN XML file and identifies eSIM ICCIDs.

    Usage:
        processor = XMLProcessor()
        records, invalids = processor.parse_file("path/to/file.xml")
        esim_iccids = processor.filter_esim_iccids(records)
    """

    # expected element path under root: ListOfCvtNginPrepaidDataIo / CvtNginPrepaidData
    ITEM_TAG = "CvtNginPrepaidData"

    def __init__(self, esim_range: Optional[EsimRange] = None):
        # load default rules if not provided
        if esim_range is None:
            esim_range, _ = get_default_rules()
        self.esim_range = esim_range
        logger.debug("XMLProcessor initialized with EsimRange: %s", self.esim_range)

    def _parse_status_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        # Try multiple formats commonly found; expand if necessary
        formats = ["%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except Exception:
                continue
        # fallback: return None but log
        logger.debug("Unrecognized date format: %r", date_str)
        return None

    def parse_file(self, xml_path: str) -> Tuple[List[NginRecord], List[Tuple[Dict, str]]]:
        """
        Parse and validate the XML file.
        Returns (valid_records, invalid_records)
        invalid_records is a list of tuples (raw_fields_dict, reason)
        """
        p = Path(xml_path)
        if not p.exists():
            raise XMLValidationError(f"File not found: {xml_path}")
        try:
            tree = ET.parse(str(p))
            root = tree.getroot()
        except ET.ParseError as e:
            raise XMLValidationError(f"Malformed XML: {e}") from e

        # find all CvtNginPrepaidData nodes (namespaces are absent in sample)
        items = root.findall(".//" + self.ITEM_TAG)
        if not items:
            # Try alternative: some siebel exports have different casing/namespace
            raise XMLValidationError(f"No '{self.ITEM_TAG}' elements found in XML.")

        valid_records: List[NginRecord] = []
        invalid_records: List[Tuple[Dict, str]] = []

        for it in items:
            raw = {}
            # extract known child elements
            for child in it:
                tag = child.tag.strip() if isinstance(child.tag, str) else str(child.tag)
                text = child.text.strip() if child.text else ""
                raw[tag] = text

            iccid = raw.get("ICCID") or raw.get("iccid") or raw.get("Iccid")
            imsi = raw.get("IMSI") or raw.get("imsi")
            msisdn = raw.get("MSISDN") or raw.get("msisdn")
            action = raw.get("Action") or raw.get("action")
            status_date_raw = raw.get("StatusDate") or raw.get("statusDate")

            # Basic validations
            if not iccid:
                invalid_records.append((raw, "Missing ICCID"))
                logger.debug("Skipping record without ICCID: %s", raw)
                continue

            # Clean ICCID (remove whitespace, non-printable)
            iccid_clean = "".join(ch for ch in str(iccid).strip() if ch.isprintable())
            # optionally remove non-digit characters (but ICCIDs normally numeric, sometimes hex)
            # We'll leave as-is but validate digits:
            if not iccid_clean.isdigit():
                # still accept if hex? depending on your system. Here we treat non-digit as invalid.
                invalid_records.append((raw, "ICCID not numeric"))
                logger.debug("ICCID not numeric: %r", iccid_clean)
                continue

            # length checks (common ICCID lengths 19-22; adjust to your policy)
            if len(iccid_clean) < 19 or len(iccid_clean) > 22:
                invalid_records.append((raw, f"ICCID length {len(iccid_clean)} out of expected range"))
                logger.debug("ICCID length invalid: %s (len=%d)", iccid_clean, len(iccid_clean))
                continue

            status_date = self._parse_status_date(status_date_raw)
            rec = NginRecord(
                iccid=iccid_clean,
                imsi=(imsi.strip() if imsi else None),
                msisdn=(msisdn.strip() if msisdn else None),
                action=(action.strip() if action else None),
                status_date=status_date,
                raw=raw
            )
            valid_records.append(rec)

        logger.info("Parsed %d valid records and %d invalid records from %s", len(valid_records), len(invalid_records), xml_path)
        return valid_records, invalid_records

    def filter_esim_iccids(self, records: List[NginRecord]) -> List[NginRecord]:
        """
        Returns the subset of records whose ICCIDs match the esim_range.
        """
        esims = []
        for rec in records:
            if self.esim_range.is_esim(rec.iccid):
                esims.append(rec)
        logger.info("Identified %d eSIM ICCIDs from %d records", len(esims), len(records))
        return esims

    def extract_esim_list_from_file(self, xml_path: str) -> Dict[str, Any]:
        """
        High level helper: parse file, filter eSIMs, and produce a structured result dictionary
        {
            "total": n,
            "valid": v,
            "invalid": i,
            "esim_count": e,
            "esim_records": [ {iccid, msisdn, imsi, ...}, ... ],
            "invalid_records": [ {raw, reason}, ... ]
        }
        """
        valid, invalid = self.parse_file(xml_path)
        esims = self.filter_esim_iccids(valid)

        return {
            "total_records": len(valid) + len(invalid),
            "valid_records": len(valid),
            "invalid_records": len(invalid),
            "esim_count": len(esims),
            "esim_records": [rec.__dict__ for rec in esims],
            "invalid_details": invalid
        }
