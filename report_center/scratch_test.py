import frappe
from report_center.report_center.report.general_ledger_audit.general_ledger_audit import execute

def test():
    filters = {
        'account': [],
        'categorize_by': 'Categorize by Voucher (Consolidated)',
        'company': 'K.G. Overseas Private Limited',
        'cost_center': [],
        'from_date': '2026-07-06',
        'include_default_book_entries': 1,
        'include_dimensions': 1,
        'location': [],
        'party': [],
        'project': [],
        'to_date': '2026-08-06',
        'presentation_currency': 'INR',
        'company_fb': None
    }
    
    print("Testing report execution...")
    try:
        columns, data = execute(filters)
        print(f"Success! Fetched {len(data)} rows.")
        # print first row to check columns
        if data:
            print("Sample row:", data[1] if len(data) > 1 else data[0])
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
