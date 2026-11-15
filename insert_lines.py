#!/usr/bin/env python
import sqlite3
import json

conn = sqlite3.connect(r'C:\Users\Thinkpad\tulip-factures\data\tulip_factures.db')
c = conn.cursor()

c.execute('DELETE FROM invoice_lines WHERE invoice_id = 27')

lines_data = [
    ('TLI TLI 500GRS EXTRA COUDE3EXTRA500GRS PLUME 500 GRS EXTRA X10', 8.0, 105.00, 840.00),
    ('PAIN BURGER SENIOR 4PX12', 80.0, 46.00, 3680.00),
]

for pos, (designation, qty, price, total) in enumerate(lines_data, 1):
    c.execute('''
        INSERT INTO invoice_lines (
            invoice_id, position, raw_designation, quantity,
            unit_price_ht, line_total_ht_extracted, confidence, source_page,
            match_status, match_candidates
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (27, pos, designation, qty, price, total, json.dumps({"global": 0.75}),
          1, 'UNMATCHED', json.dumps([])))

conn.commit()
c.execute('SELECT COUNT(*) FROM invoice_lines WHERE invoice_id = 27')
print(f"Lignes insérées: {c.fetchone()[0]}")
conn.close()
