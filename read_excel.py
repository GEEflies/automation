import openpyxl
import os

file_path = '[Social Growth Engineers] Education & Productivity Hooks Dataset.xlsx'

if not os.path.exists(file_path):
    print(f"File not found: {file_path}")
    exit(1)

try:
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    print("--- SCANNING FIRST 20 ROWS ---")
    for i, row in enumerate(ws.iter_rows(max_row=20, values_only=True)):
        # Check if row has any content
        if any(row):
            print(f"Row {i+1}: {row}")
except Exception as e:
    print(f"Error: {e}")
