import sys
import pandas as pd
sys.path.insert(0, 'src')
from parsers import PDFParser
from pathlib import Path

parser = PDFParser()
df = parser.safe_parse(Path('input/DONNER&REUSCHEL - VEEAM Monthly Backup Reporting - 2025-08.pdf'))

if df is not None:
    df.to_csv('temp_debug.csv', index=False)
    print('Saved to temp_debug.csv')
    print(f'\nShape: {df.shape}')
    print(f'\nColumns: {df.columns.tolist()}')

    # Print all rows
    print('\nAll rows:')
    for i, row in df.iterrows():
        vals = [str(v) for v in row.values if pd.notna(v) and str(v).strip()]
        if vals:
            content = " | ".join(vals)
            if len(content) > 300:
                content = content[:300] + "..."
            print(f'Row {i}: {content}')
else:
    print('Failed to parse PDF')
