import pandas as pd
from pathlib import Path

# Simulate what the analyzer does
file_path = Path('input/archive/2025-10/DONNER&REUSCHEL - VEEAM Monthly Backup Reporting_20251003_135828_20251003_135840.htm')

# Read with pandas - use open() to read file first
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    html_content = f.read()

from io import StringIO
tables = pd.read_html(StringIO(html_content), flavor='lxml')
df = max(tables, key=lambda df: len(df) * len(df.columns))

print("=" * 80)
print("RAW DATA FROM HTM FILE")
print("=" * 80)
print(f"\nColumns: {df.columns.tolist()}")
print(f"\nFirst 3 Start Times (RAW):")
print(df['Start Time'].head(3))

# Extract dates exactly as the analyzer does
df['_date'] = df['Start Time'].astype(str).str.extract(r'(\d{2}/\d{2}/\d{4})')[0]
print(f"\nExtracted date strings (first 5):")
print(df['_date'].head(5))

df['_parsed_date'] = pd.to_datetime(df['_date'], format='%d/%m/%Y', errors='coerce')
print(f"\nParsed dates (first 5):")
print(df['_parsed_date'].head(5))

# Remove invalid rows
valid_df = df[df['_parsed_date'].notna() & df['VM Name'].notna() & (df['VM Name'].astype(str).str.strip() != '')].copy()

print(f"\n\nValid rows: {len(valid_df)}")
print(f"Date range: {valid_df['_parsed_date'].min()} to {valid_df['_parsed_date'].max()}")

# Determine report month
valid_df['_month'] = valid_df['_parsed_date'].dt.to_period('M')
print(f"\nUnique months in data:")
print(valid_df['_month'].value_counts().sort_index())

report_month = valid_df['_month'].mode()[0] if len(valid_df) > 0 else None
print(f"\nReport month (mode): {report_month}")
print(f"Report month type: {type(report_month)}")

# Format as done in the analyzer
formatted_month = f"{report_month.year}-{report_month.month:02d}"
print(f"Formatted month: {formatted_month}")
