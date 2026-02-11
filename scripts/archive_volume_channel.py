import zipfile, os, datetime
# Note: The legacy Volume Channel engine was removed and archived in commit aacfeea.
# No active files to archive remain; keep this script for historical/utility purposes.
files=[]
found = [f for f in files if os.path.exists(f)]
if found:
    ts=datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    out=f'artifacts/archived_volume_channel_flow_{ts}.zip'
    os.makedirs('artifacts', exist_ok=True)
    with zipfile.ZipFile(out,'w') as z:
        for f in found:
            z.write(f)
    print('Archived to', out)
else:
    print('No files to archive')
