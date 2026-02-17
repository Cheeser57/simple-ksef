#!/usr/bin/env python3
"""Debug script to check invoice types in database"""
import sqlite3
import os

DATA_FOLDER = "data"
DB_PATH = os.path.join(DATA_FOLDER, "ksef.db")

if not os.path.exists(DB_PATH):
    print(f"Database not found at {DB_PATH}")
    exit(1)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

# Check invoice counts by type
print("Invoice counts by type:")
cur.execute("SELECT type, COUNT(*) FROM invoices GROUP BY type ORDER BY COUNT(*) DESC;")
results = cur.fetchall()
for type_val, count in results:
    print(f"  {type_val}: {count}")

# Check if there are any NULL types
print("\nChecking for NULL types:")
cur.execute("SELECT COUNT(*) FROM invoices WHERE type IS NULL;")
null_count = cur.fetchone()[0]
print(f"  NULL types: {null_count}")

# Get sample Kor invoices (if any)
print("\nSample Kor type invoices:")
cur.execute("SELECT ksef, invoice_number, seller_name, type FROM invoices WHERE type = 'Kor' LIMIT 5;")
kor_invoices = cur.fetchall()
if kor_invoices:
    for invoice in kor_invoices:
        print(f"  {invoice}")
else:
    print("  No Kor invoices found")

# Get total invoice count
cur.execute("SELECT COUNT(*) FROM invoices;")
total = cur.fetchone()[0]
print(f"\nTotal invoices in database: {total}")

con.close()
