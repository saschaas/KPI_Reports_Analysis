import logging
import re
from typing import Dict, Any, List
from datetime import datetime, timedelta
import pandas as pd
from difflib import SequenceMatcher
import unicodedata
from analyzers.base_analyzer import BaseAnalyzer
from utils.scoring import CheckResult

logger = logging.getLogger(__name__)


class EntraDevicesAnalyzer(BaseAnalyzer):
    """Analyzer for Microsoft Entra (Azure AD) Devices Reports."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize EntraDevicesAnalyzer.

        Args:
            config: Analysis configuration dictionary from entra_devices.yaml
        """
        super().__init__(config)
        self.fuzzy_config = config.get('identification', {}).get('fuzzy_matching', {})
        self.field_mappings = self.fuzzy_config.get('field_mappings', {})
        self.fuzzy_threshold = self.fuzzy_config.get('threshold', 0.85)
        self.report_month = None  # Will be set via user input

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

        logger.info(f"Starting column mapping for {len(df.columns)} columns: {list(df.columns)}")

        for col in df.columns:
            # Check each field mapping
            for field_name, field_config in self.field_mappings.items():
                alternatives = field_config.get('alternatives', [])

                if self._fuzzy_match(col, alternatives):
                    column_mapping[col] = field_name
                    logger.info(f"✓ Mapped column '{col}' -> '{field_name}'")
                    break

        # Rename columns
        if column_mapping:
            mapped_df = mapped_df.rename(columns=column_mapping)
            logger.info(f"Successfully mapped {len(column_mapping)} columns: {column_mapping}")
        else:
            logger.warning(f"No columns were mapped! Original columns: {list(df.columns)}")

        logger.info(f"Final columns after mapping: {list(mapped_df.columns)}")

        return mapped_df

    def _detect_date_format(self, dates: pd.Series) -> str:
        """
        Detect date format by analyzing all date values.

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
        logger.info(f"Detected date format for {date_col}: {date_format}")

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
            df[f'_parsed_{date_col}'] = pd.to_datetime(df[date_col], format=pandas_format, errors='coerce')
            logger.info(f"Parsed {df[f'_parsed_{date_col}'].notna().sum()} dates successfully for {date_col}")
        except Exception as e:
            logger.warning(f"Date parsing with format {pandas_format} failed: {e}")
            # Fallback to pandas automatic parsing
            df[f'_parsed_{date_col}'] = pd.to_datetime(df[date_col], errors='coerce')

        return df

    def _prompt_user_for_report_month(self) -> str:
        """
        Prompt user to enter the report month.

        Returns:
            Report month in YYYY-MM format
        """
        print("\n" + "="*60)
        print("ENTRA DEVICES REPORT - MONAT EINGABE")
        print("="*60)
        print("\nBitte geben Sie den Berichtszeitraum für diesen Entra Devices Report ein.")
        print("Format: YYYY-MM (z.B. 2024-10 für Oktober 2024)")
        print()

        while True:
            user_input = input("Berichtszeitraum (YYYY-MM): ").strip()

            # Validate format
            if re.match(r'^\d{4}-\d{2}$', user_input):
                # Validate month is 01-12
                year, month = user_input.split('-')
                if 1 <= int(month) <= 12:
                    logger.info(f"User entered report month: {user_input}")
                    print(f"\nBerichtszeitraum gesetzt: {user_input}")
                    print("="*60 + "\n")
                    return user_input
                else:
                    print(f"Fehler: Monat '{month}' ist ungültig. Bitte einen Monat zwischen 01 und 12 eingeben.")
            else:
                print(f"Fehler: Ungültiges Format '{user_input}'. Bitte Format YYYY-MM verwenden (z.B. 2024-10)")

    def _calculate_inactive_devices(self, df: pd.DataFrame, report_date: datetime) -> pd.DataFrame:
        """
        Calculate which devices are inactive (>90 days since last sign-in).

        Args:
            df: DataFrame with parsed approximateLastSignInDateTime
            report_date: The report date (end of report month)

        Returns:
            DataFrame with _inactive_device column added
        """
        if 'approximateLastSignInDateTime' not in df.columns:
            logger.warning("approximateLastSignInDateTime column not found")
            df['_inactive_device'] = False
            return df

        # Parse dates
        df = self._parse_dates(df, 'approximateLastSignInDateTime')

        # Calculate days since last sign-in
        if '_parsed_approximateLastSignInDateTime' in df.columns:
            df['_days_since_signin'] = (report_date - df['_parsed_approximateLastSignInDateTime']).dt.days

            # Mark devices inactive if >90 days
            df['_inactive_device'] = df['_days_since_signin'] > 90

            inactive_count = df['_inactive_device'].sum()
            logger.info(f"Found {inactive_count} inactive devices (>90 days)")
        else:
            df['_inactive_device'] = False

        return df

    def _calculate_recent_registrations(self, df: pd.DataFrame, report_date: datetime) -> pd.DataFrame:
        """
        Calculate which devices were recently registered (last 30 days).

        Args:
            df: DataFrame with parsed registrationDateTime
            report_date: The report date (end of report month)

        Returns:
            DataFrame with _recent_registration column added
        """
        if 'registrationDateTime' not in df.columns:
            logger.warning("registrationDateTime column not found")
            df['_recent_registration'] = False
            return df

        # Parse dates
        df = self._parse_dates(df, 'registrationDateTime')

        # Calculate days since registration
        if '_parsed_registrationDateTime' in df.columns:
            df['_days_since_registration'] = (report_date - df['_parsed_registrationDateTime']).dt.days

            # Mark devices as recent if registered in last 30 days
            df['_recent_registration'] = df['_days_since_registration'] <= 30

            recent_count = df['_recent_registration'].sum()
            logger.info(f"Found {recent_count} recently registered devices (last 30 days)")
        else:
            df['_recent_registration'] = False

        return df

    def run_checks(self, data: pd.DataFrame) -> List[CheckResult]:
        """Run configured checks on the Entra devices data."""
        checks = []

        # Map columns
        df = self._map_columns(data)

        logger.info(f"Analyzing {len(df)} device entries")

        # Prompt user for report month
        self.report_month = self._prompt_user_for_report_month()

        # Parse report month to datetime (end of month)
        year, month = map(int, self.report_month.split('-'))
        if month == 12:
            report_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            report_date = datetime(year, month + 1, 1) - timedelta(days=1)

        logger.info(f"Using report date: {report_date.strftime('%Y-%m-%d')}")

        # Calculate inactive devices and recent registrations
        df = self._calculate_inactive_devices(df, report_date)
        df = self._calculate_recent_registrations(df, report_date)

        # Store modified dataframe for field extraction
        self._enriched_df = df

        # Completeness check
        required_cols = ['displayName', 'operatingSystem']
        missing_cols = [col for col in required_cols if col not in df.columns]

        checks.append(CheckResult(
            check_id='completeness',
            name='Vollständigkeitsprüfung',
            passed=len(missing_cols) == 0,
            severity='high',
            message='Alle Pflichtfelder vorhanden' if len(missing_cols) == 0 else f'Fehlende Pflichtfelder: {", ".join(missing_cols)}',
            details={'missing_columns': missing_cols}
        ))

        # Inactive devices check
        inactive_count = df['_inactive_device'].sum()
        total_devices = len(df)
        inactive_rate = (inactive_count / total_devices * 100) if total_devices > 0 else 0

        checks.append(CheckResult(
            check_id='inactive_devices',
            name='Inaktive Geräte (>90 Tage)',
            passed=inactive_count == 0,
            severity='medium',
            message=f'{inactive_count} inaktive Geräte gefunden ({inactive_rate:.1f}%)' if inactive_count > 0 else 'Keine inaktiven Geräte',
            details={
                'inactive_count': int(inactive_count),
                'inactive_rate': round(inactive_rate, 2)
            }
        ))

        # Non-compliant devices check (if compliance data available)
        if 'isCompliant' in df.columns:
            # Normalize compliance values
            df['_normalized_compliant'] = df['isCompliant'].astype(str).str.lower().str.strip()
            non_compliant_count = (df['_normalized_compliant'] == 'false').sum()
            non_compliant_rate = (non_compliant_count / total_devices * 100) if total_devices > 0 else 0

            checks.append(CheckResult(
                check_id='non_compliant_devices',
                name='Nicht-konforme Geräte',
                passed=non_compliant_count == 0,
                severity='medium',
                message=f'{non_compliant_count} nicht-konforme Geräte gefunden ({non_compliant_rate:.1f}%)' if non_compliant_count > 0 else 'Alle Geräte konform',
                details={
                    'non_compliant_count': int(non_compliant_count),
                    'non_compliant_rate': round(non_compliant_rate, 2)
                }
            ))

        return checks

    def extract_fields(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Extract fields from Entra devices data."""
        fields = {}

        # Use enriched dataframe if available (from run_checks)
        if hasattr(self, '_enriched_df'):
            df = self._enriched_df
        else:
            # Map columns and enrich
            df = self._map_columns(data)

            # If report month not set, prompt user
            if not self.report_month:
                self.report_month = self._prompt_user_for_report_month()

            # Parse report month
            year, month = map(int, self.report_month.split('-'))
            if month == 12:
                report_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                report_date = datetime(year, month + 1, 1) - timedelta(days=1)

            df = self._calculate_inactive_devices(df, report_date)
            df = self._calculate_recent_registrations(df, report_date)

        # Basic counts
        fields['total_devices'] = len(df)
        fields['report_month'] = self.report_month

        # Devices without owner
        if 'registeredOwners' in df.columns:
            # Empty, NaN, or whitespace-only values count as "no owner"
            devices_without_owner_mask = df['registeredOwners'].fillna('').astype(str).str.strip() == ''
            fields['devices_without_owner'] = int(devices_without_owner_mask.sum())

            # Get list of devices without owner (informational)
            devices_without_owner_df = df[devices_without_owner_mask]
            fields['devices_without_owner_list'] = []
            for idx, row in devices_without_owner_df.iterrows():
                fields['devices_without_owner_list'].append({
                    'displayName': row.get('displayName', 'N/A'),
                    'operatingSystem': row.get('operatingSystem', 'N/A'),
                    'deviceId': row.get('deviceId', 'N/A')
                })
        else:
            fields['devices_without_owner'] = 0
            fields['devices_without_owner_list'] = []

        # Inactive devices
        fields['inactive_devices'] = int(df['_inactive_device'].sum())

        # Get list of inactive devices
        inactive_df = df[df['_inactive_device'] == True]
        fields['inactive_devices_list'] = []
        for idx, row in inactive_df.iterrows():
            fields['inactive_devices_list'].append({
                'displayName': row.get('displayName', 'N/A'),
                'operatingSystem': row.get('operatingSystem', 'N/A'),
                'approximateLastSignInDateTime': row.get('approximateLastSignInDateTime', 'N/A'),
                'days_since_signin': int(row.get('_days_since_signin', 0)) if pd.notna(row.get('_days_since_signin')) else 'N/A'
            })

        # Recent registrations
        fields['recent_registrations'] = int(df['_recent_registration'].sum())

        # Get list of recent registrations
        recent_df = df[df['_recent_registration'] == True]
        fields['recent_registrations_list'] = []
        for idx, row in recent_df.iterrows():
            fields['recent_registrations_list'].append({
                'displayName': row.get('displayName', 'N/A'),
                'operatingSystem': row.get('operatingSystem', 'N/A'),
                'registrationDateTime': row.get('registrationDateTime', 'N/A')
            })

        # Compliance data
        if 'isCompliant' in df.columns:
            df['_normalized_compliant'] = df['isCompliant'].astype(str).str.lower().str.strip()
            fields['compliant_devices'] = int((df['_normalized_compliant'] == 'true').sum())
            fields['non_compliant_devices'] = int((df['_normalized_compliant'] == 'false').sum())
        else:
            fields['compliant_devices'] = 0
            fields['non_compliant_devices'] = 0

        # Enabled devices
        if 'accountEnabled' in df.columns:
            df['_normalized_enabled'] = df['accountEnabled'].astype(str).str.lower().str.strip()
            fields['enabled_devices'] = int((df['_normalized_enabled'] == 'true').sum())
        else:
            fields['enabled_devices'] = 0

        # Managed devices
        if 'isManaged' in df.columns:
            df['_normalized_managed'] = df['isManaged'].astype(str).str.lower().str.strip()
            fields['managed_devices'] = int((df['_normalized_managed'] == 'true').sum())
        else:
            fields['managed_devices'] = 0

        # Calculate rates
        if fields['total_devices'] > 0:
            fields['inactive_rate'] = round((fields['inactive_devices'] / fields['total_devices']) * 100, 2)
            fields['compliance_rate'] = round((fields['compliant_devices'] / fields['total_devices']) * 100, 2) if fields['compliant_devices'] > 0 else 0.0
        else:
            fields['inactive_rate'] = 0.0
            fields['compliance_rate'] = 0.0

        # Operating system breakdown (keep separate categories)
        if 'operatingSystem' in df.columns:
            os_counts = df['operatingSystem'].value_counts().to_dict()
            # Convert to regular types for JSON serialization
            fields['os_breakdown'] = {str(k): int(v) for k, v in os_counts.items()}
        else:
            fields['os_breakdown'] = {}

        # Trust type breakdown
        if 'trustType' in df.columns:
            trust_counts = df['trustType'].value_counts().to_dict()
            fields['trust_type_breakdown'] = {str(k): int(v) for k, v in trust_counts.items()}
        else:
            fields['trust_type_breakdown'] = {}

        logger.info(f"Extracted fields: {fields['total_devices']} devices, {fields['inactive_devices']} inactive, {fields['devices_without_owner']} without owner")

        return fields
