import logging
import re
from typing import Dict, Any, List, Set
from datetime import datetime, timedelta
import pandas as pd
from difflib import SequenceMatcher
import unicodedata
from analyzers.base_analyzer import BaseAnalyzer
from utils.scoring import CheckResult

logger = logging.getLogger(__name__)


class KeeepitBackupAnalyzer(BaseAnalyzer):
    """Analyzer for Keepit Backup Reports (OneDrive, SharePoint, Exchange, User Teams Chats)."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize KeeepitBackupAnalyzer.

        Args:
            config: Analysis configuration dictionary from keepit_backup.yaml
        """
        super().__init__(config)
        self.fuzzy_config = config.get('identification', {}).get('fuzzy_matching', {})
        self.field_mappings = self.fuzzy_config.get('field_mappings', {})
        self.fuzzy_threshold = self.fuzzy_config.get('threshold', 0.85)

    def _normalize_string(self, text: str) -> str:
        """
        Normalize string for fuzzy matching.

        Args:
            text: Input string

        Returns:
            Normalized string
        """
        if not isinstance(text, str):
            return str(text)

        # Trim whitespace
        text = text.strip()

        # Lowercase
        text = text.lower()

        # Unicode normalization (NFD)
        text = unicodedata.normalize('NFD', text)

        # Remove diacritics
        text = ''.join(
            char for char in text
            if unicodedata.category(char) != 'Mn'
        )

        return text

    def _fuzzy_match(self, text: str, alternatives: List[str], threshold: float = None) -> bool:
        """
        Check if text fuzzy matches any of the alternatives.

        Args:
            text: Text to match
            alternatives: List of alternative strings
            threshold: Similarity threshold (0-1)

        Returns:
            True if match found
        """
        if threshold is None:
            threshold = self.fuzzy_threshold

        normalized_text = self._normalize_string(text)

        for alt in alternatives:
            normalized_alt = self._normalize_string(alt)
            similarity = SequenceMatcher(None, normalized_text, normalized_alt).ratio()

            if similarity >= threshold:
                logger.debug(f"Fuzzy match found: '{text}' ~ '{alt}' (similarity: {similarity:.2f})")
                return True

        return False

    def _map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Map DataFrame columns to standardized field names using fuzzy matching.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with mapped column names
        """
        mapped_df = df.copy()
        column_mapping = {}

        for col in df.columns:
            # Check each field mapping
            for field_name, field_config in self.field_mappings.items():
                alternatives = field_config.get('alternatives', [])

                if self._fuzzy_match(col, alternatives):
                    column_mapping[col] = field_name
                    logger.debug(f"Mapped column '{col}' -> '{field_name}'")
                    break

        # Rename columns
        if column_mapping:
            mapped_df = mapped_df.rename(columns=column_mapping)
            logger.info(f"Mapped {len(column_mapping)} columns")

        return mapped_df

    def _normalize_status(self, status: str) -> str:
        """
        Normalize status value to standard categories.

        Args:
            status: Raw status value

        Returns:
            Normalized status (success/failed/warning/unknown)
        """
        if not isinstance(status, str):
            status = str(status)

        normalized = self._normalize_string(status)

        # Get status value mappings from config
        status_config = self.field_mappings.get('status', {}).get('values', {})

        for category, alternatives in status_config.items():
            for alt in alternatives:
                if self._normalize_string(alt) in normalized:
                    return category

        return 'unknown'

    def _detect_date_format(self, dates: pd.Series) -> str:
        """
        Detect date format by analyzing all date values.

        Similar to Veeam analyzer - analyzes the entire dataset to determine format.

        Args:
            dates: Series of date strings

        Returns:
            Format string ('yyyy-mm-dd', 'yyyy-dd-mm', 'dd-mm-yyyy', 'mm-dd-yyyy', etc.)
        """
        # Sample some dates to analyze
        sample_dates = dates.dropna().head(50)

        if len(sample_dates) == 0:
            return 'yyyy-mm-dd'  # Default

        # Try to extract components from dates
        # Common separators: -, /, space, .
        date_pattern = r'(\d{1,4})[/\-\s\.](\d{1,2})[/\-\s\.](\d{1,4})'

        components = []
        for date_str in sample_dates:
            match = re.search(date_pattern, str(date_str))
            if match:
                components.append([int(match.group(1)), int(match.group(2)), int(match.group(3))])

        if not components:
            return 'yyyy-mm-dd'  # Default

        # Analyze components to determine format
        first_vals = [c[0] for c in components]
        second_vals = [c[1] for c in components]
        third_vals = [c[2] for c in components]

        # Check if first position has years (>31)
        if any(v > 31 for v in first_vals):
            # Format: yyyy-??-??
            # Check if second position has all same value (likely month)
            if len(set(second_vals)) == 1 or all(v <= 12 for v in second_vals):
                # Check if third position has values >12 (must be day)
                if any(v > 12 for v in third_vals):
                    return 'yyyy-mm-dd'
                # Both could be valid, check second position range
                if any(v > 12 for v in second_vals):
                    return 'yyyy-dd-mm'
                return 'yyyy-mm-dd'
            else:
                return 'yyyy-dd-mm'

        # Check if third position has years
        if any(v > 31 for v in third_vals):
            # Format: ??-??-yyyy
            # Similar logic for day/month determination
            if any(v > 12 for v in first_vals):
                return 'dd-mm-yyyy'
            if any(v > 12 for v in second_vals):
                return 'mm-dd-yyyy'
            return 'dd-mm-yyyy'

        # Default fallback
        return 'yyyy-mm-dd'

    def _parse_dates(self, df: pd.DataFrame, date_col: str) -> pd.DataFrame:
        """
        Parse date column with automatic format detection.

        Args:
            df: DataFrame
            date_col: Name of date column

        Returns:
            DataFrame with parsed dates in _parsed_date column
        """
        if date_col not in df.columns:
            logger.warning(f"Date column '{date_col}' not found")
            return df

        # Detect format
        date_format = self._detect_date_format(df[date_col])
        logger.info(f"Detected date format: {date_format}")

        # Map format to pandas format string
        format_mapping = {
            'yyyy-mm-dd': '%Y-%m-%d',
            'yyyy-dd-mm': '%Y-%d-%m',
            'dd-mm-yyyy': '%d-%m-%Y',
            'mm-dd-yyyy': '%m-%d-%Y',
        }

        pandas_format = format_mapping.get(date_format, '%Y-%m-%d')

        # Parse dates
        try:
            df['_parsed_date'] = pd.to_datetime(df[date_col], format=pandas_format, errors='coerce')
            logger.info(f"Parsed {df['_parsed_date'].notna().sum()} dates successfully")
        except Exception as e:
            logger.warning(f"Date parsing with format {pandas_format} failed: {e}")
            # Fallback to pandas automatic parsing
            df['_parsed_date'] = pd.to_datetime(df[date_col], errors='coerce')

        return df

    def _determine_report_month(self, df: pd.DataFrame) -> tuple:
        """
        Determine the report month by analyzing Start Time values.

        Args:
            df: DataFrame with _parsed_date column

        Returns:
            Tuple of (year, month) for the report period
        """
        if '_parsed_date' not in df.columns or df['_parsed_date'].isna().all():
            # Fallback to current month
            now = datetime.now()
            return (now.year, now.month)

        # Count occurrences of each month
        month_counts = df['_parsed_date'].dt.to_period('M').value_counts()

        if len(month_counts) == 0:
            now = datetime.now()
            return (now.year, now.month)

        # Most frequent month is the report month
        report_period = month_counts.index[0]
        return (report_period.year, report_period.month)

    def _get_missing_backup_days(self, df: pd.DataFrame) -> List[str]:
        """
        Find days in the report month where NO backups were performed.

        Strategy:
        1. Determine the report month from Start Time values
        2. Generate all days in that month
        3. Find days with no backup entries
        4. Return those missing days

        Args:
            df: DataFrame with parsed dates

        Returns:
            List of missing days (YYYY-MM-DD format)
        """
        # Find start_time column
        start_time_col = None
        for col in df.columns:
            if self._fuzzy_match(col, self.field_mappings.get('start_time', {}).get('alternatives', [])):
                start_time_col = col
                break

        if not start_time_col:
            logger.warning("Start time column not found")
            return []

        # Parse dates
        df = self._parse_dates(df, start_time_col)

        if df['_parsed_date'].isna().all():
            logger.warning("No valid dates found")
            return []

        # Determine report month
        report_year, report_month = self._determine_report_month(df)
        logger.info(f"Report month detected: {report_year}-{report_month:02d}")

        # Filter to report month
        target_month_df = df[
            (df['_parsed_date'].dt.year == report_year) &
            (df['_parsed_date'].dt.month == report_month)
        ]

        if len(target_month_df) == 0:
            logger.warning("No entries found in detected report month")
            return []

        # Get all days in the month
        from calendar import monthrange
        days_in_month = monthrange(report_year, report_month)[1]

        all_days_in_month = set()
        for day in range(1, days_in_month + 1):
            all_days_in_month.add(datetime(report_year, report_month, day).date())

        # Get days with backups
        backup_days = set(target_month_df['_parsed_date'].dt.date.dropna())

        # Find missing days
        missing_days = sorted(list(all_days_in_month - backup_days))

        logger.info(f"Found {len(missing_days)} days without backups in {report_year}-{report_month:02d}")

        return [str(day) for day in missing_days]

    def run_checks(self, data: pd.DataFrame) -> List[CheckResult]:
        """Run configured checks on the Keepit backup data."""
        checks = []

        # Map columns
        df = self._map_columns(data)

        logger.info(f"Analyzing {len(df)} backup entries")

        # Normalize status values
        if 'status' in df.columns:
            df['_normalized_status'] = df['status'].apply(self._normalize_status)
        else:
            logger.error("Status column not found after mapping")
            return [CheckResult(
                check_id='missing_status',
                name='Status-Spalte fehlt',
                passed=False,
                severity='high',
                message='Die erforderliche Status-Spalte wurde nicht gefunden'
            )]

        # Count status types
        status_counts = df['_normalized_status'].value_counts()
        total_backups = len(df)
        successful_backups = status_counts.get('success', 0)
        failed_backups = status_counts.get('failed', 0)
        warning_backups = status_counts.get('warning', 0)

        logger.info(f"Backup status: {successful_backups} success, {failed_backups} failed, {warning_backups} warnings")

        # Completeness check
        required_cols = ['connector', 'status']
        missing_cols = [col for col in required_cols if col not in df.columns]

        checks.append(CheckResult(
            check_id='completeness',
            name='Vollständigkeitsprüfung',
            passed=len(missing_cols) == 0,
            severity='high',
            message='Alle Pflichtfelder vorhanden' if len(missing_cols) == 0 else f'Fehlende Pflichtfelder: {", ".join(missing_cols)}',
            details={'missing_columns': missing_cols}
        ))

        # Failed backups check
        failed_entries = df[df['_normalized_status'] == 'failed']

        # Get dates of failed backups
        failed_dates = []
        if 'start_time' in df.columns and not failed_entries.empty:
            temp_df = self._parse_dates(failed_entries, 'start_time')
            failed_dates = temp_df['_parsed_date'].dt.strftime('%Y-%m-%d').dropna().tolist()

        checks.append(CheckResult(
            check_id='backup_failures',
            name='Fehlerhafte Backups',
            passed=failed_backups == 0,
            severity='high',
            message=f'{failed_backups} fehlerhafte Backups gefunden' if failed_backups > 0 else 'Keine fehlerhaften Backups',
            details={
                'failed_count': failed_backups,
                'failed_dates': failed_dates
            }
        ))

        # Warning backups check
        checks.append(CheckResult(
            check_id='backup_warnings',
            name='Backup-Warnungen',
            passed=warning_backups == 0,
            severity='medium',
            message=f'{warning_backups} Backup-Warnungen gefunden' if warning_backups > 0 else 'Keine Backup-Warnungen',
            details={'warning_count': warning_backups}
        ))

        # Missing backups check - days without any backups
        missing_days = self._get_missing_backup_days(df)

        checks.append(CheckResult(
            check_id='missing_backups',
            name='Fehlende Backups',
            passed=len(missing_days) == 0,
            severity='medium',
            message=f'{len(missing_days)} Tage ohne Backups gefunden' if len(missing_days) > 0 else 'Alle erwarteten Backups vorhanden',
            details={'missing_days': missing_days}
        ))

        return checks

    def extract_fields(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Extract fields from Keepit backup data."""
        fields = {}

        # Map columns
        df = self._map_columns(data)

        # Normalize status
        if 'status' in df.columns:
            df['_normalized_status'] = df['status'].apply(self._normalize_status)
        else:
            df['_normalized_status'] = 'unknown'

        # Basic counts
        fields['total_backups'] = len(df)

        status_counts = df['_normalized_status'].value_counts()
        fields['successful_backups'] = int(status_counts.get('success', 0))
        fields['failed_backups'] = int(status_counts.get('failed', 0))
        fields['warning_backups'] = int(status_counts.get('warning', 0))

        # Calculate success rate
        if fields['total_backups'] > 0:
            fields['success_rate'] = round((fields['successful_backups'] / fields['total_backups']) * 100, 2)
            fields['failure_rate'] = round((fields['failed_backups'] / fields['total_backups']) * 100, 2)
        else:
            fields['success_rate'] = 100.0
            fields['failure_rate'] = 0.0

        # Date range
        if 'start_time' in df.columns:
            df_with_dates = self._parse_dates(df, 'start_time')

            if not df_with_dates['_parsed_date'].isna().all():
                fields['period_start'] = df_with_dates['_parsed_date'].min().strftime('%Y-%m-%d')
                fields['period_end'] = df_with_dates['_parsed_date'].max().strftime('%Y-%m-%d')
            else:
                fields['period_start'] = 'N/A'
                fields['period_end'] = 'N/A'
        else:
            fields['period_start'] = 'N/A'
            fields['period_end'] = 'N/A'

        # Connector types (OneDrive, SharePoint, Exchange, Teams)
        if 'connector' in df.columns:
            connector_counts = df['connector'].value_counts().to_dict()
            fields['connector_breakdown'] = connector_counts
            fields['unique_connectors'] = len(connector_counts)
        else:
            fields['connector_breakdown'] = {}
            fields['unique_connectors'] = 0

        # Failed backup details
        failed_df = df[df['_normalized_status'] == 'failed']
        failed_details = []

        if not failed_df.empty:
            # Parse dates for failed backups
            if 'start_time' in failed_df.columns:
                failed_df = self._parse_dates(failed_df, 'start_time')

            for idx, row in failed_df.iterrows():
                detail = {
                    'connector': row.get('connector', 'N/A'),
                    'type': row.get('type', 'N/A'),
                    'description': row.get('description', 'N/A'),
                    'start_time': row.get('start_time', 'N/A')
                }
                failed_details.append(detail)

        fields['failed_backup_details'] = failed_details

        # Missing backup days
        fields['missing_backup_days'] = self._get_missing_backup_days(df)
        fields['missing_backup_days_count'] = len(fields['missing_backup_days'])

        # Type breakdown (if available)
        if 'type' in df.columns:
            type_counts = df['type'].value_counts().to_dict()
            fields['type_breakdown'] = type_counts
        else:
            fields['type_breakdown'] = {}

        logger.info(f"Extracted fields: {fields['total_backups']} backups, {fields['success_rate']}% success rate")

        return fields
