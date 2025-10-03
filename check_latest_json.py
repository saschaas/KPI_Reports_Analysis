import json
from pathlib import Path

files = list(Path('output/2025-10').glob('*.json'))
latest = max(files, key=lambda f: f.stat().st_mtime)
data = json.load(open(latest))

print(f'File: {latest.name}')

vm_analysis = data['reports'][0]['extracted_data'].get('vm_analysis')
print(f'Has vm_analysis: {vm_analysis is not None}')

if vm_analysis:
    print(f"Report month: {vm_analysis.get('report_month')}")
    print(f"VM count: {len(vm_analysis.get('vms', {}))}")

    vms = vm_analysis.get('vms', {})
    if vms:
        first_vm_name = list(vms.keys())[0]
        first_vm = vms[first_vm_name]
        print(f"\nFirst VM: {first_vm_name}")
        print(f"Backup dates (sample): {first_vm.get('backup_dates', [])[:5]}")
        print(f"Missing days (sample): {first_vm.get('missing_days_list', [])[:5]}")
else:
    print("No VM analysis found - check extracted_data")
    print(f"Keys in extracted_data: {data['reports'][0]['extracted_data'].keys()}")
    print(f"\nMissing backup days: {data['reports'][0]['extracted_data'].get('missing_backup_days', [])[:10]}")
