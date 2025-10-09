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


class VeeamBackupAnalyzer(BaseAnalyzer):
    """Analyzer for Veeam Backup Reports."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize VeeamBackupAnalyzer.

        Args:
            config: Analysis configuration dictionary from veeam_backup.yaml
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
                    logger.info(f"Mapped column '{col}' -> '{field_name}'")
                    break

        # Rename columns
        if column_mapping:
            mapped_df = mapped_df.rename(columns=column_mapping)

        return mapped_df

    def _normalize_status(self, status: str) -> str:
        """
        Normalize status values to standard values.

        Args:
            status: Raw status value

        Returns:
            Normalized status (success, failed, warning)
        """
        if not isinstance(status, str):
            return 'unknown'

        status_config = self.field_mappings.get('status', {})
        value_mappings = status_config.get('values', {})

        normalized = self._normalize_string(status)

        # Check each status category
        for category, alternatives in value_mappings.items():
            for alt in alternatives:
                if self._normalize_string(alt) in normalized:
                    return category

        return 'unknown'

    def _parse_duration(self, duration_str: str) -> float:
        """
        Parse duration string to seconds.

        Args:
            duration_str: Duration in format HH:MM:SS or similar

        Returns:
            Duration in seconds
        """
        if pd.isna(duration_str):
            return 0.0

        try:
            # Try HH:MM:SS format
            parts = str(duration_str).split(':')
            if len(parts) == 3:
                hours, minutes, seconds = map(float, parts)
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes, seconds = map(float, parts)
                return minutes * 60 + seconds
            else:
                return float(duration_str)
        except:
            return 0.0

    def _detect_date_format(self, dates_series: pd.Series) -> str:
        """
        Intelligently detect the date format by analyzing all date values.

        Strategy:
        1. Extract all date components (3 numbers before time)
        2. Analyze which position has values >12 (must be days or years)
        3. Find position where all values are the same (likely the report month)
        4. Determine format based on patterns

        Args:
            dates_series: Series of date strings

        Returns:
            Detected format string ('yyyy-mm-dd', 'yyyy-dd-mm', 'dd-mm-yyyy', etc.)
        """
        try:
            components = {'pos0': [], 'pos1': [], 'pos2': []}

            for date_str in dates_series:
                if pd.isna(date_str):
                    continue

                # Extract date part (before time if present)
                date_part = str(date_str).split()[0] if ' ' in str(date_str) else str(date_str)
                parts = date_part.split('-')

                if len(parts) >= 3:
                    try:
                        components['pos0'].append(int(parts[0]))
                        components['pos1'].append(int(parts[1]))
                        components['pos2'].append(int(parts[2]))
                    except:
                        continue

            if not components['pos0']:
                return 'yyyy-mm-dd'  # Default fallback

            # Analyze each position
            pos0_unique = set(components['pos0'])
            pos1_unique = set(components['pos1'])
            pos2_unique = set(components['pos2'])

            pos0_max = max(components['pos0'])
            pos1_max = max(components['pos1'])
            pos2_max = max(components['pos2'])

            logger.info(f"Date format detection:")
            logger.info(f"  Position 0: unique={len(pos0_unique)}, max={pos0_max}, values={sorted(pos0_unique)[:5]}")
            logger.info(f"  Position 1: unique={len(pos1_unique)}, max={pos1_max}, values={sorted(pos1_unique)}")
            logger.info(f"  Position 2: unique={len(pos2_unique)}, max={pos2_max}, values={sorted(pos2_unique)}")

            # Position 0 is almost always year (>1000)
            if pos0_max > 1000:
                # yyyy-?-?

                # Check if position 2 has only one unique value (likely the month)
                if len(pos2_unique) == 1:
                    month_value = list(pos2_unique)[0]
                    if 1 <= month_value <= 12:
                        logger.info(f"Detected format: yyyy-dd-mm (month={month_value} in position 2)")
                        return 'yyyy-dd-mm'

                # Check if position 1 has only one unique value (likely the month)
                if len(pos1_unique) == 1:
                    month_value = list(pos1_unique)[0]
                    if 1 <= month_value <= 12:
                        logger.info(f"Detected format: yyyy-mm-dd (month={month_value} in position 1)")
                        return 'yyyy-mm-dd'

                # Check which position has values >12 (must be days)
                if pos1_max > 12:
                    logger.info(f"Detected format: yyyy-dd-mm (position 1 has value {pos1_max} > 12)")
                    return 'yyyy-dd-mm'

                if pos2_max > 12:
                    logger.info(f"Detected format: yyyy-mm-dd (position 2 has value {pos2_max} > 12)")
                    return 'yyyy-mm-dd'

                # Default: standard format
                logger.info("Using default format: yyyy-mm-dd")
                return 'yyyy-mm-dd'

            # If position 0 is not a year, try other patterns
            logger.info("Non-standard date format detected, using yyyy-mm-dd as fallback")
            return 'yyyy-mm-dd'

        except Exception as e:
            logger.error(f"Error detecting date format: {e}", exc_info=True)
            return 'yyyy-mm-dd'

    def _get_missing_backup_days(self, df: pd.DataFrame) -> List[str]:
        """
        Find days where ANY VM is missing backups in the report month.

        Strategy:
        1. Analyze ALL Start Time values to determine the report month
        2. The report month is determined by the month that appears most frequently
        3. For each VM, check if it has backups for all days in the month
        4. Return days where at least one VM is missing a backup

        Args:
            df: DataFrame with start_time column (case-insensitive match)

        Returns:
            List of dates (YYYY-MM-DD) where at least one VM is missing backups
        """
        # Find required columns (case-insensitive)
        start_time_col = None
        vm_name_col = None

        for col in df.columns:
            if 'start' in col.lower() and 'time' in col.lower():
                start_time_col = col
            if 'vm' in col.lower() and 'name' in col.lower():
                vm_name_col = col

        if not start_time_col:
            logger.warning("No start time column found for missing days calculation")
            return []

        if not vm_name_col:
            logger.warning("No VM name column found for missing days calculation")
            return []

        try:
            # First, detect the date format by analyzing raw values
            detected_format = self._detect_date_format(df[start_time_col])

            # Parse dates according to detected format
            if detected_format == 'yyyy-dd-mm':
                # Need to manually parse yyyy-dd-mm format
                parsed_dates = []
                for date_str in df[start_time_col]:
                    if pd.isna(date_str):
                        continue
                    try:
                        date_part = str(date_str).split()[0] if ' ' in str(date_str) else str(date_str)
                        parts = date_part.split('-')
                        if len(parts) >= 3:
                            year = int(parts[0])
                            day = int(parts[1])
                            month = int(parts[2])
                            parsed_dates.append(pd.Timestamp(year=year, month=month, day=day))
                    except:
                        continue
                dates = pd.Series(parsed_dates)
            else:
                # Standard yyyy-mm-dd or other pandas-compatible format
                dates = pd.to_datetime(df[start_time_col], errors='coerce').dropna()

            if dates.empty:
                logger.warning("No valid dates found in start_time column")
                return []

            # Create working dataframe with parsed dates
            work_df = df.copy()
            work_df['_parsed_date'] = dates

            total_entries = len(dates)
            logger.info(f"Analyzing {total_entries} backup entries for missing days")

            # Extract year-month for each date
            year_months = pd.Series([d.to_period('M') for d in dates])
            month_counts = year_months.value_counts()

            logger.info(f"Month distribution after format correction: {dict(month_counts)}")

            # Determine the target month (the one with most entries or the only one)
            if len(month_counts) == 1:
                # Only one month - perfect!
                target_month_period = month_counts.index[0]
                logger.info(f"Single month detected: {target_month_period}")
            else:
                # Multiple months - take the most frequent
                target_month_period = month_counts.idxmax()
                target_month_count = month_counts.max()
                target_month_percentage = (target_month_count / total_entries) * 100

                logger.info(f"Target month: {target_month_period} "
                           f"({target_month_count}/{total_entries} entries = {target_month_percentage:.1f}%)")

                if target_month_percentage < 50:
                    logger.warning(f"No dominant month found (highest is {target_month_percentage:.1f}%). "
                                 f"Report may cover multiple months.")

            # Get month boundaries for target month
            target_year = target_month_period.year
            target_month_num = target_month_period.month

            month_start = pd.Timestamp(year=target_year, month=target_month_num, day=1)
            if target_month_num == 12:
                next_month_start = pd.Timestamp(year=target_year + 1, month=1, day=1)
            else:
                next_month_start = pd.Timestamp(year=target_year, month=target_month_num + 1, day=1)
            month_end = next_month_start - timedelta(days=1)

            logger.info(f"Checking for missing days in: {month_start.date()} to {month_end.date()}")

            # Create set of all days in target month
            all_days_in_month = set()
            current_day = month_start
            while current_day <= month_end:
                all_days_in_month.add(current_day.date())
                current_day += timedelta(days=1)

            # Filter to target month
            target_month_df = work_df[
                (work_df['_parsed_date'] >= month_start) &
                (work_df['_parsed_date'] <= month_end)
            ].copy()

            # Get unique VMs
            unique_vms = target_month_df[vm_name_col].unique()
            logger.info(f"Found {len(unique_vms)} unique VMs in target month")

            # Find days where ANY VM is missing a backup
            days_with_missing_vms = set()

            for vm in unique_vms:
                vm_df = target_month_df[target_month_df[vm_name_col] == vm]
                vm_backup_days = set(vm_df['_parsed_date'].dt.date)

                # Find missing days for this VM
                vm_missing_days = all_days_in_month - vm_backup_days

                if vm_missing_days:
                    logger.info(f"VM '{vm}' missing {len(vm_missing_days)} days: {sorted(list(vm_missing_days))[:3]}...")
                    days_with_missing_vms.update(vm_missing_days)

            missing_days = sorted(days_with_missing_vms)

            logger.info(f"Results: {len(missing_days)} days where at least one VM is missing backups in {target_month_period}")

            return [day.strftime('%Y-%m-%d') for day in missing_days]

        except Exception as e:
            logger.error(f"Error calculating missing backup days: {e}", exc_info=True)
            return []

    def run_checks(self, data: pd.DataFrame) -> List[CheckResult]:
        """
        Run configured checks on the Veeam backup data.

        Args:
            data: DataFrame containing parsed Veeam backup data

        Returns:
            List of check results
        """
        checks = []

        # Perform VM analysis first (needed for accurate missing days calculation)
        self._vm_analysis_cache = self._analyze_per_vm(data)

        # Map columns
        df = self._map_columns(data)

        # Normalize status values
        if 'status' in df.columns:
            df['status'] = df['status'].apply(self._normalize_status)

        # Completeness check
        required_cols = ['vm_name', 'status']
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            checks.append(CheckResult(
                check_id='completeness',
                name='Vollständigkeitsprüfung',
                passed=False,
                severity='high',
                message=f'Pflichtfelder fehlen: {", ".join(missing_cols)}',
                details={'missing_columns': missing_cols}
            ))
        else:
            checks.append(CheckResult(
                check_id='completeness',
                name='Vollständigkeitsprüfung',
                passed=True,
                severity='high',
                message='Alle Pflichtfelder vorhanden'
            ))

        # Backup failures check
        if 'status' in df.columns:
            failed_count = (df['status'] == 'failed').sum()
            total_count = len(df)
            failure_rate = failed_count / total_count if total_count > 0 else 0

            # Get threshold from config
            analysis_config = self.config.get('analysis', {})
            checks_config = analysis_config.get('algorithmic_checks', [])
            max_failure_rate = 0.10  # Default to 10%

            for check_config in checks_config:
                if check_config.get('check_id') == 'backup_failures':
                    max_failure_rate = check_config.get('parameters', {}).get('max_percentage', 0.10)
                    break

            checks.append(CheckResult(
                check_id='backup_failures',
                name='Fehlerhafte Backups',
                passed=failure_rate <= max_failure_rate,
                severity='high',
                message=f'{failed_count} von {total_count} Backups fehlgeschlagen ({failure_rate*100:.1f}%)',
                details={
                    'failed_count': int(failed_count),
                    'total_count': int(total_count),
                    'failure_rate': float(failure_rate)
                }
            ))

            # Backup warnings check
            warning_count = (df['status'] == 'warning').sum()
            warning_rate = warning_count / total_count if total_count > 0 else 0

            checks.append(CheckResult(
                check_id='backup_warnings',
                name='Backup-Warnungen',
                passed=warning_rate <= 0.10,
                severity='medium',
                message=f'{warning_count} von {total_count} Backups mit Warnungen ({warning_rate*100:.1f}%)',
                details={
                    'warning_count': int(warning_count),
                    'total_count': int(total_count),
                    'warning_rate': float(warning_rate)
                }
            ))

        # Missing backups check - use VM analysis results for accurate CRITICAL missing days
        critical_missing_days = []
        if hasattr(self, '_vm_analysis_cache') and 'vms' in self._vm_analysis_cache:
            all_critical_missing = set()
            for vm_name, vm_data in self._vm_analysis_cache['vms'].items():
                critical_count = vm_data.get('missing_days_critical', 0)
                if critical_count > 0:
                    # Only add truly missing days (not recoverable ones)
                    missing_days_list = vm_data.get('missing_days_list', [])
                    recoverable = vm_data.get('missing_days_recoverable', 0)
                    critical_missing = missing_days_list[recoverable:] if recoverable < len(missing_days_list) else missing_days_list
                    all_critical_missing.update(critical_missing)

            critical_missing_days = sorted(list(all_critical_missing))

        checks.append(CheckResult(
            check_id='missing_backups',
            name='Fehlende Backups',
            passed=len(critical_missing_days) == 0,
            severity='medium',
            message=f'{len(critical_missing_days)} Tage ohne Backups gefunden' if len(critical_missing_days) > 0 else 'Alle erwarteten Backups vorhanden',
            details={'missing_days': critical_missing_days}
        ))

        return checks

    def _analyze_per_vm(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze backups per VM with missing days detection and scoring.

        Returns:
            Dict with per-VM analysis including scores, missing days, and failed backups
        """
        logger.info(f"Starting VM analysis with {len(df)} rows")
        logger.info(f"DataFrame columns: {list(df.columns)}")

        # Find columns using fuzzy matching from config
        vm_col = None
        start_time_col = None
        status_col = None

        for col in df.columns:
            col_lower = str(col).lower().strip()
            if 'vm' in col_lower and 'name' in col_lower:
                vm_col = col
            elif 'start' in col_lower and 'time' in col_lower:
                start_time_col = col
            elif 'status' in col_lower:
                status_col = col

        logger.info(f"Columns found: vm={vm_col}, start_time={start_time_col}, status={status_col}")

        if not all([vm_col, start_time_col, status_col]):
            logger.warning(f"VM analysis skipped - columns not found: vm={vm_col}, start_time={start_time_col}, status={status_col}")
            logger.warning(f"Available columns: {list(df.columns)}")
            return {}

        # Extract dates from start_time - handle both string and datetime formats
        # Check if column is already datetime
        if pd.api.types.is_datetime64_any_dtype(df[start_time_col]):
            df['_parsed_date'] = df[start_time_col]
        else:
            # Extract from string (dd/mm/yyyy format)
            df['_date'] = df[start_time_col].astype(str).str.extract(r'(\d{2}/\d{2}/\d{4})')[0]
            df['_parsed_date'] = pd.to_datetime(df['_date'], format='%d/%m/%Y', errors='coerce')

        # Remove invalid rows (footer, header remnants)
        valid_df = df[df['_parsed_date'].notna() & df[vm_col].notna() & (df[vm_col].astype(str).str.strip() != '')].copy()

        # DEBUG: Check parsed dates
        logger.info(f"[VM Analysis] Date range: {valid_df['_parsed_date'].min()} to {valid_df['_parsed_date'].max()}")
        logger.info(f"[VM Analysis] Sample dates: {valid_df['_parsed_date'].head(3).tolist()}")

        # Determine report month (month with most backups)
        valid_df['_month'] = valid_df['_parsed_date'].dt.to_period('M')
        report_month = valid_df['_month'].mode()[0] if len(valid_df) > 0 else None
        logger.info(f"[VM Analysis] Report month determined: {report_month} (type: {type(report_month)})")

        if not report_month:
            return {}

        # Filter to report month only
        month_df = valid_df[valid_df['_month'] == report_month].copy()

        # Get all days in the month
        year = report_month.year
        month = report_month.month
        days_in_month = pd.Period(f"{year}-{month:02d}").days_in_month
        all_days = pd.date_range(start=f"{year}-{month:02d}-01",
                                  periods=days_in_month, freq='D')

        vm_analysis = {}

        for vm_name in sorted(month_df[vm_col].unique()):
            vm_df = month_df[month_df[vm_col] == vm_name].copy()

            # Backup dates for this VM
            vm_backup_dates = set(vm_df['_parsed_date'].dt.date)

            # Find missing days
            missing_days = []
            for day in all_days:
                if day.date() not in vm_backup_dates:
                    missing_days.append(day.date())

            # Status analysis
            status_counts = vm_df[status_col].value_counts().to_dict()
            total_backups = len(vm_df)
            successful = status_counts.get('Success', 0)
            failed = status_counts.get('Failed', 0)
            warning = status_counts.get('Warning', 0)

            # Get failed backup details (full rows)
            failed_backups = []
            if failed > 0:
                failed_rows = vm_df[vm_df[status_col] == 'Failed']
                for _, row in failed_rows.iterrows():
                    # Convert to dict and handle non-serializable types
                    row_dict = {}
                    for key, value in row.items():
                        # Skip internal columns
                        if key.startswith('_'):
                            continue
                        # Convert pandas/numpy types to Python types
                        if pd.isna(value):
                            row_dict[key] = None
                        elif isinstance(value, (pd.Timestamp, pd.Period)):
                            row_dict[key] = str(value)
                        else:
                            row_dict[key] = value
                    failed_backups.append(row_dict)

            # Calculate score
            # Base score: success rate
            success_rate = (successful / total_backups * 100) if total_backups > 0 else 0
            score = success_rate

            # Check for missing days with next-day recovery
            recoverable_missing = 0
            for missing_day in missing_days[:]:
                next_day = missing_day + pd.Timedelta(days=1)
                if next_day in vm_backup_dates:
                    # Check if next day was successful
                    next_day_status = vm_df[vm_df['_parsed_date'].dt.date == next_day][status_col].values
                    if len(next_day_status) > 0 and next_day_status[0] == 'Success':
                        recoverable_missing += 1

            # Adjust score: missing days don't affect score if next day was successful
            actual_missing = len(missing_days) - recoverable_missing

            vm_analysis[vm_name] = {
                'total_backups': total_backups,
                'successful_backups': successful,
                'failed_backups': failed,
                'warning_backups': warning,
                'success_rate': round(success_rate, 2),
                'missing_days_total': len(missing_days),
                'missing_days_recoverable': recoverable_missing,
                'missing_days_critical': actual_missing,
                'missing_days_list': [str(d) for d in sorted(missing_days)],
                'failed_backup_details': failed_backups,
                'score': round(score, 2),
                'backup_dates': sorted([str(d) for d in vm_backup_dates])
            }

        return {
            'report_month': f"{report_month.year}-{report_month.month:02d}",
            'vms': vm_analysis,
            'summary': {
                'total_vms': len(vm_analysis),
                'vms_with_failures': sum(1 for v in vm_analysis.values() if v['failed_backups'] > 0),
                'vms_with_missing_days': sum(1 for v in vm_analysis.values() if v['missing_days_critical'] > 0),
                'average_success_rate': round(sum(v['success_rate'] for v in vm_analysis.values()) / len(vm_analysis), 2) if vm_analysis else 0,
                'average_score': round(sum(v['score'] for v in vm_analysis.values()) / len(vm_analysis), 2) if vm_analysis else 0
            }
        }

    def extract_fields(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Extract defined fields from Veeam backup data.

        Args:
            data: DataFrame containing parsed backup data

        Returns:
            Dictionary with extracted field values
        """
        logger.info(f"===== VeeamBackupAnalyzer.extract_fields() called with {len(data)} rows, {len(data.columns)} columns =====")
        logger.info(f"Data columns: {list(data.columns)}")

        # Map columns
        df = self._map_columns(data)

        # Normalize status values
        if 'status' in df.columns:
            df['status'] = df['status'].apply(self._normalize_status)

        fields = {}

        # Total backups
        fields['total_backups'] = len(df)

        # Count by status
        if 'status' in df.columns:
            fields['successful_backups'] = int((df['status'] == 'success').sum())
            fields['failed_backups'] = int((df['status'] == 'failed').sum())
            fields['warning_backups'] = int((df['status'] == 'warning').sum())
        else:
            fields['successful_backups'] = 0
            fields['failed_backups'] = 0
            fields['warning_backups'] = 0

        # Success and failure rates
        if fields['total_backups'] > 0:
            fields['success_rate'] = round(
                (fields['successful_backups'] / fields['total_backups']) * 100, 2
            )
            fields['failure_rate'] = round(
                (fields['failed_backups'] / fields['total_backups']) * 100, 2
            )
        else:
            fields['success_rate'] = 100.0
            fields['failure_rate'] = 0.0

        # Total capacity
        if 'total_gb' in df.columns:
            fields['total_capacity_gb'] = round(
                pd.to_numeric(df['total_gb'], errors='coerce').sum(), 2
            )
        else:
            fields['total_capacity_gb'] = 0.0

        # Period start/end - use same parsing logic as VM analysis
        if 'start_time' in df.columns:
            # Check if column is already datetime
            if pd.api.types.is_datetime64_any_dtype(df['start_time']):
                dates = df['start_time'].dropna()
            else:
                # Extract from string (dd/mm/yyyy format - European format!)
                date_str = df['start_time'].astype(str).str.extract(r'(\d{2}/\d{2}/\d{4})')[0]
                dates = pd.to_datetime(date_str, format='%d/%m/%Y', errors='coerce').dropna()

            if not dates.empty:
                fields['period_start'] = dates.min().strftime('%Y-%m-%d')
                fields['period_end'] = dates.max().strftime('%Y-%m-%d')
            else:
                fields['period_start'] = 'N/A'
                fields['period_end'] = 'N/A'
        else:
            fields['period_start'] = 'N/A'
            fields['period_end'] = 'N/A'

        # Unique VMs
        if 'vm_name' in df.columns:
            fields['unique_vms'] = int(df['vm_name'].nunique())
        else:
            fields['unique_vms'] = 0

        # Failed VMs details
        if 'status' in df.columns and 'vm_name' in df.columns:
            failed_df = df[df['status'] == 'failed']
            fields['failed_vms'] = []
            for _, row in failed_df.iterrows():
                vm_info = {
                    'vm_name': row.get('vm_name', 'N/A'),
                    'start_time': str(row.get('start_time', 'N/A'))
                }
                fields['failed_vms'].append(vm_info)
        else:
            fields['failed_vms'] = []

        # Per-VM analysis - use cached result from run_checks() if available
        if hasattr(self, '_vm_analysis_cache'):
            fields['vm_analysis'] = self._vm_analysis_cache
            logger.info(f"Using cached VM analysis: {len(fields['vm_analysis'].get('vms', {}))} VMs")
        else:
            fields['vm_analysis'] = self._analyze_per_vm(data)
            logger.info(f"VM analysis completed: {len(fields['vm_analysis'].get('vms', {}))} VMs analyzed")

        # Missing backup days - use VM analysis results (more accurate)
        # Only count CRITICAL missing days (not recoverable ones)
        if 'vms' in fields['vm_analysis']:
            all_critical_missing = set()
            for vm_name, vm_data in fields['vm_analysis']['vms'].items():
                # Only add critical missing days (those that weren't recovered next day)
                critical_count = vm_data.get('missing_days_critical', 0)
                if critical_count > 0:
                    # These are truly missing days
                    missing_days_list = vm_data.get('missing_days_list', [])
                    recoverable = vm_data.get('missing_days_recoverable', 0)
                    # Take only the critical ones (not the recoverable ones)
                    critical_missing = missing_days_list[recoverable:] if recoverable < len(missing_days_list) else missing_days_list
                    all_critical_missing.update(critical_missing)

            fields['missing_backup_days'] = sorted(list(all_critical_missing))
            fields['missing_backup_days_count'] = len(fields['missing_backup_days'])
        else:
            # Fallback to old method if VM analysis not available
            fields['missing_backup_days'] = self._get_missing_backup_days(df)
            fields['missing_backup_days_count'] = len(fields['missing_backup_days'])

        return fields
