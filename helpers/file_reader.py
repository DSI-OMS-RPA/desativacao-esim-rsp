import pandas as pd
from pathlib import Path
import logging
from chardet import detect
import csv
from typing import List, Tuple
from .models import ReportMetadata

logger = logging.getLogger(__name__)

class FileReader:
    def __init__(self):
        self.supported_extensions = {'.csv', '.xlsx', '.txt', '.xls', '.lst'}

    def detect_file_encoding(file_path):
        """
        Função melhorada para detectar encoding de ficheiros
        Tenta múltiplos encodings comuns para ficheiros de cupões
        """
        import chardet
        from pathlib import Path

        # Encodings mais comuns para ficheiros de sistemas legados
        encodings_to_try = [
            'latin1',       # ISO-8859-1 (muito comum em sistemas Windows antigos)
            'cp1252',       # Windows-1252 (extensão do Latin1 com caracteres especiais)
            'iso-8859-15',  # Latin-9 (inclui símbolo Euro)
            'utf-8',        # UTF-8
            'cp850',        # DOS/OEM - Portuguese
            'ascii'         # ASCII puro (fallback)
        ]

        try:
            # Primeiro tentar detecção automática
            with open(file_path, 'rb') as f:
                raw_data = f.read(4096)  # Ler primeiros 4KB

            result = chardet.detect(raw_data)
            if result['confidence'] > 0.8:
                detected_encoding = result['encoding']
                print(f"Auto-detected encoding: {detected_encoding} (confidence: {result['confidence']:.2f})")
                return detected_encoding
        except Exception as e:
            print(f"Auto-detection failed: {e}")

        # Se auto-detecção falhou, tentar encodings manualmente
        for encoding in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    # Tentar ler o ficheiro inteiro
                    f.read()
                print(f"Successfully read file with encoding: {encoding}")
                return encoding
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error with encoding {encoding}: {e}")
                continue

        # Se nada funcionou, usar latin1 como fallback (nunca falha)
        print("Using fallback encoding: latin1")
        return 'latin1'


    def validate_file(self, file_path: Path, metadata: ReportMetadata) -> None:
        """
        Validate file existence and format.

        Args:
            file_path (Path): Path to the file
            metadata (ReportMetadata): File metadata

        Raises:
            ValueError: If validation fails
        """
        if not file_path.exists():
            raise ValueError(f"File not found: {file_path}")

        if file_path.suffix.lower() not in self.supported_extensions:
            raise ValueError(f"Unsupported file extension: {file_path.suffix}")

    def preprocess_txt(self, file_path: Path, metadata: ReportMetadata, encoding: str) -> Path:
        """
        Preprocess the TXT file, handling fixed-width or custom-delimited formats with dynamic delimiter detection.

        Args:
            file_path (Path): Path to the original TXT file
            metadata (ReportMetadata): File metadata
            encoding (str): File encoding

        Returns:
            Path: Path to the preprocessed file
        """
        processed_lines = []
        invalid_rows = []

        # Define possible delimiters with their escape sequences
        DELIMITER_MAP = {
            'tab': '\t',
            't': '\t',
            '\\t': '\t',
            'semicolon': ';',
            'comma': ',',
            'pipe': '|',
            'space': ' ',
            'colon': ':',
        }

        try:
            # Determine the delimiter
            specified_delimiter = metadata.delimiter.lower() if metadata.delimiter else None
            effective_delimiter = None

            if specified_delimiter:
                # Check if it's a known delimiter name
                if specified_delimiter in DELIMITER_MAP:
                    effective_delimiter = DELIMITER_MAP[specified_delimiter]
                # Check if it's a raw delimiter character
                elif len(specified_delimiter) == 1:
                    effective_delimiter = specified_delimiter
                else:
                    logger.warning(f"Unrecognized delimiter '{specified_delimiter}', attempting auto-detection")

            # If no valid delimiter specified, attempt auto-detection
            if not effective_delimiter:
                effective_delimiter = self.detect_delimiter(file_path, encoding)
                logger.info(f"Auto-detected delimiter: {repr(effective_delimiter)}")

            with open(file_path, 'r', encoding=encoding) as file:
                # Skip initial rows if specified
                for _ in range(metadata.skip_rows):
                    next(file)

                # Read and process the remaining lines
                for line_number, line in enumerate(file, start=metadata.skip_rows + 1):
                    line = line.strip()
                    if not line:  # Skip empty lines
                        continue

                    try:
                        # Handle fixed-width format if specified in metadata
                        if hasattr(metadata, 'column_widths') and metadata.column_widths:
                            fields = []
                            start = 0
                            for width in metadata.column_widths:
                                fields.append(line[start:start + width].strip())
                                start += width
                            processed_line = fields
                        else:
                            # Split using the determined delimiter
                            if effective_delimiter == ' ':
                                # Handle multiple spaces
                                processed_line = ' '.join(line.split()).split(effective_delimiter)
                            else:
                                processed_line = line.split(effective_delimiter)

                            # Clean up each field
                            processed_line = [field.strip() for field in processed_line]

                        processed_lines.append(processed_line)

                    except Exception as e:
                        logger.warning(f"Error processing line {line_number}: {str(e)}")
                        invalid_rows.append((line_number, line))
                        continue

            # Save processed lines to a temporary CSV file
            processed_file = file_path.with_name(f"processed_{file_path.name}.csv")
            with open(processed_file, 'w', newline='', encoding=encoding) as file:
                writer = csv.writer(file)
                writer.writerows(processed_lines)

            # Log processing summary
            total_lines = len(processed_lines)
            invalid_count = len(invalid_rows)
            logger.info(f"Processed {total_lines} lines with delimiter: {repr(effective_delimiter)}")
            if invalid_rows:
                logger.warning(f"Found {invalid_count} invalid rows")
                for line_num, line in invalid_rows[:5]:  # Log first 5 invalid rows
                    logger.debug(f"Invalid row at line {line_num}: {line[:100]}...")

            return processed_file

        except Exception as e:
            logger.error(f"Error preprocessing TXT file {file_path}: {str(e)}")
            raise

    def detect_delimiter(self, file_path: Path, encoding: str) -> str:
        """
        Detect the delimiter used in a file by analyzing the first few lines.

        Args:
            file_path (Path): Path to the file
            encoding (str): File encoding

        Returns:
            str: Detected delimiter
        """
        possible_delimiters = [',', ';', '\t', '|']
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                # Read a larger sample for better detection
                sample_lines = []
                for _ in range(5):  # Increased to 5 lines for better sampling
                    try:
                        line = next(file)
                        if line.strip():  # Only include non-empty lines
                            sample_lines.append(line)
                    except StopIteration:
                        break

                if not sample_lines:
                    logger.warning("Empty file or no valid lines found")
                    return ','

                # Join the sample lines
                sample = ''.join(sample_lines)

                # Count occurrences and calculate consistency
                delimiter_stats = {}
                for delimiter in possible_delimiters:
                    # Count occurrences in each line
                    line_counts = [line.count(delimiter) for line in sample_lines]

                    if not any(line_counts):  # Skip if delimiter not found
                        continue

                    # Calculate consistency score
                    avg_count = sum(line_counts) / len(line_counts)
                    consistency = sum(1 for count in line_counts if count == line_counts[0]) / len(line_counts)

                    delimiter_stats[delimiter] = {
                        'total_count': sum(line_counts),
                        'avg_count': avg_count,
                        'consistency': consistency
                    }

                if not delimiter_stats:
                    logger.warning("No common delimiters found")
                    return ','

                # Choose the best delimiter based on consistency and frequency
                best_delimiter = max(
                    delimiter_stats.items(),
                    key=lambda x: (x[1]['consistency'], x[1]['avg_count'])
                )[0]

                # Log detailed detection information
                logger.info(f"Detected delimiter: {repr(best_delimiter)}")
                logger.debug(f"Delimiter statistics: {delimiter_stats}")

                return best_delimiter

        except Exception as e:
            logger.warning(f"Error detecting delimiter: {str(e)}. Defaulting to comma.")
            return ','

    def preprocess_csv(self, file_path: Path, metadata: ReportMetadata, encoding: str) -> Path:
        """
        Preprocess the CSV file to handle mismatched rows and decimal commas.

        Args:
            file_path (Path): Path to the original CSV file
            metadata (ReportMetadata): File metadata
            encoding (str): File encoding

        Returns:
            Path: Path to the preprocessed file
        """
        processed_lines = []
        invalid_rows = []
        header_fields = None

        # Get delimiter from metadata or detect it
        delimiter = metadata.delimiter or self.detect_delimiter(file_path, encoding)
        if delimiter == '\\t':  # Handle escaped tab character
            delimiter = '\t'

        try:
            with open(file_path, 'r', encoding=encoding, newline='') as file:
                reader = csv.reader(file, delimiter=delimiter)

                # Skip the specified number of rows
                for _ in range(metadata.skip_rows):
                    next(reader, None)

                # Process remaining rows
                for row_number, row in enumerate(reader, start=metadata.skip_rows + 1):

                    # Capture the header
                    if header_fields is None:
                        header_fields = len(row)
                        processed_lines.append(row)
                        continue

                    # Handle rows with different number of fields
                    if len(row) > header_fields:
                        row = row[:header_fields]
                    elif len(row) < header_fields:
                        invalid_rows.append((row_number, row))
                        continue

                    # Replace commas with dots in numeric fields
                    cleaned_row = []
                    for cell in row:
                        # Check if the cell might be a numeric value with a comma
                        test_cell = cell.replace(",", "").replace(".", "").strip()
                        if test_cell.isdigit() or (test_cell.startswith('-') and test_cell[1:].isdigit()):
                            cleaned_row.append(cell.replace(",", "."))
                        else:
                            cleaned_row.append(cell)

                    processed_lines.append(cleaned_row)

            # Log invalid rows
            if invalid_rows:
                logger.warning(f"Found {len(invalid_rows)} invalid rows in {file_path.name}")
                for row_number, row in invalid_rows:
                    logger.debug(f"Invalid row at line {row_number}: {row}")

            # Save processed lines to a temporary file
            processed_file = file_path.with_name(f"processed_{file_path.name}")
            with open(processed_file, 'w', newline='', encoding=encoding) as file:
                writer = csv.writer(file, delimiter=delimiter)
                writer.writerows(processed_lines)

            logger.info(f"Preprocessed CSV saved to: {processed_file}")
            return processed_file

        except Exception as e:
            logger.error(f"Error preprocessing CSV file {file_path}: {str(e)}")
            raise

    def read_txt_file(self, file_path: Path, metadata: ReportMetadata, encoding: str) -> pd.DataFrame:
        """
        Read TXT file with error handling and preprocessing.

        Args:
            file_path (Path): Path to the TXT file
            metadata (ReportMetadata): File metadata
            encoding (str): File encoding

        Returns:
            pd.DataFrame: Loaded data
        """
        try:
            # Preprocess the TXT file to CSV format
            processed_file = self.preprocess_txt(file_path, metadata, encoding)

            # Configure pandas read options
            read_options = {
                'filepath_or_buffer': processed_file,
                'encoding': encoding,
                'dtype': str,
                'on_bad_lines': 'skip'
            }

            if metadata.date_format:
                read_options.update({
                    'parse_dates': True,
                    'date_format': metadata.date_format
                })

            # Read the preprocessed file
            df = pd.read_csv(**read_options)

            # Clean up the temporary file
            processed_file.unlink()

            return df

        except Exception as e:
            logger.error(f"Error reading TXT file {file_path}: {str(e)}")
            raise

    def read_csv_file(self, file_path: Path, metadata: ReportMetadata, encoding: str) -> pd.DataFrame:
        """
        Read CSV file with error handling and preprocessing.

        Args:
            file_path (Path): Path to the CSV file
            metadata (ReportMetadata): File metadata
            encoding (str): File encoding

        Returns:
            pd.DataFrame: Loaded data
        """
        try:
            # Preprocess the CSV file
            processed_file = self.preprocess_csv(file_path, metadata, encoding)

            # Configure pandas read options
            read_options = {
                'filepath_or_buffer': processed_file,
                'encoding': encoding,
                'delimiter': metadata.delimiter or ',',
                'skiprows': metadata.skip_rows,
                'header': 0 if metadata.header else None,
                'dtype': str,
                'on_bad_lines': 'skip'
            }

            if metadata.date_format:
                read_options.update({
                    'parse_dates': True,
                    'date_format': metadata.date_format
                })

            # Read the preprocessed file
            df = pd.read_csv(**read_options)

            # Clean up the temporary file
            processed_file.unlink()

            return df

        except Exception as e:
            logger.error(f"Error reading CSV file {file_path}: {str(e)}")
            raise

    def read_excel_file(self, file_path: Path, metadata: ReportMetadata) -> pd.DataFrame:
        """
        Read Excel file with error handling.

        Args:
            file_path (Path): Path to the Excel file
            metadata (ReportMetadata): File metadata

        Returns:
            pd.DataFrame: Loaded data
        """
        read_options = {
            'io': file_path,
            'sheet_name': metadata.sheet_name or 0,
            'skip_rows': metadata.skip_rows
        }

        try:
            return pd.read_excel(**read_options)
        except Exception as e:
            logger.error(f"Error reading Excel file: {str(e)}")
            try:
                read_options['engine'] = 'xlrd'
                return pd.read_excel(**read_options)
            except Exception:
                raise

    def read_file_data(self, file_path: Path, metadata: ReportMetadata) -> pd.DataFrame:
        """
        Read file data based on file extension and configuration.

        Args:
            file_path (Path): Path to the file to read
            metadata (ReportMetadata): Metadata configuration for the file

        Returns:
            pd.DataFrame: The loaded data as a pandas DataFrame

        Raises:
            ValueError: If file validation fails
            Exception: If file reading fails
        """
        try:
            # Validate file
            self.validate_file(file_path, metadata)

            # Detect encoding if not provided
            encoding = metadata.encoding or self.detect_file_encoding(file_path)
            logger.info(f"Using encoding: {encoding} for file: {file_path.name}")

            # Read file based on extension
            file_ext = file_path.suffix.lower()

            if file_ext == '.csv':
                df = self.read_csv_file(file_path, metadata, encoding)
            elif file_ext == '.txt':
                df = self.read_txt_file(file_path, metadata, encoding)
            elif file_ext in ['.xlsx', '.xls']:
                df = self.read_excel_file(file_path, metadata)
            elif file_ext == '.lst':
                # Tratar ficheiros .lst como CSV com delimiter específico
                df = self.read_csv_file(file_path, metadata, encoding)
            else:
                raise ValueError(f"Unsupported file extension: {file_ext}")

            # Validate DataFrame
            if df.empty:
                raise ValueError(f"No data found in file: {file_path}")

            logger.info(f"Successfully read file {file_path.name} with {len(df)} rows")
            return df

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            raise
