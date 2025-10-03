import pandas as pd

tables = pd.read_html('input/DONNER&REUSCHEL - VEEAM Monthly Backup Reporting.htm')
print(f'Found {len(tables)} tables')

for i, df in enumerate(tables):
    print(f'\n=== Table {i} ===')
    print(f'Shape: {df.shape}')
    print(f'Columns: {df.columns.tolist()}')
    if len(df) > 0:
        print(f'First 2 rows:\n{df.head(2)}')

# Get the largest table
largest = max(tables, key=lambda df: len(df) * len(df.columns))
print(f'\n\n=== LARGEST TABLE ===')
print(f'Shape: {largest.shape}')
print(f'Columns: {largest.columns.tolist()}')

# Try to find Start Time column
if 'Start Time' in largest.columns:
    print('\nStart Time column found!')
    dates = pd.to_datetime(largest['Start Time'].str.extract(r'(\d{2}/\d{2}/\d{4})')[0],
                          format='%d/%m/%Y', errors='coerce')
    print(f'\nDate range: {dates.min()} to {dates.max()}')
    print(f'\nUnique months:')
    print(dates.dt.to_period('M').value_counts().sort_index())
