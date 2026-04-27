import sqlite3, sys, io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('./backend/data/aegiscx.db')
c = conn.cursor()
c.execute("SELECT id, original_filename, status, error_message, created_at FROM recordings ORDER BY created_at DESC LIMIT 10")
rows = c.fetchall()
for r in rows:
    err = str(r[3])[:400] if r[3] else "None"
    fname = str(r[1]).encode('utf-8', errors='replace').decode('utf-8')
    print(f"ID      : {r[0][:12]}...")
    print(f"File    : {fname[:70]}")
    print(f"Status  : {r[2]}")
    print(f"Error   : {err}")
    print(f"Created : {r[4]}")
    print("-" * 70)
conn.close()
