from pathlib import Path
from src.parsers.html_parser import HTMLParser
import pandas as pd

file_path = Path('input/DONNER&REUSCHEL - VEEAM Monthly Backup Reporting.htm')
parser = HTMLParser()
df = parser.parse(file_path)

print(f"Columns: {df.columns.tolist()}")
print(f"\nShape: {df.shape}")
print(f"\nFirst 5 Start Times:")
print(df['Start Time'].head(5))
print(f"\nLast 5 Start Times:")
print(df['Start Time'].tail(5))

# Extract dates
dates_str = df['Start Time'].astype(str).str.extract(r'(\d{2}/\d{2}/\d{4})')[0]
print(f"\nExtracted date strings (first 5):")
print(dates_str.head(5))

parsed_dates = pd.to_datetime(dates_str, format='%d/%m/%Y', errors='coerce')
print(f"\nParsed dates (first 5):")
print(parsed_dates.head(5))
print(f"\nParsed dates (last 5):")
print(parsed_dates.tail(5))

print(f"\nDate range: {parsed_dates.min()} to {parsed_dates.max()}")
print(f"\nUnique months:")
print(parsed_dates.dt.to_period('M').value_counts().sort_index())
