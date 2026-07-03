# Report Center

A custom Frappe/ERPNext application designed to provide audit-ready, upgrade-safe financial reports and query tools.

## Features

### 1. General Ledger Audit Script Report
A custom script report that inherits all filters, functions, and behaviors of the standard ERPNext **General Ledger** report, with the following additions:
- **Created On Column**: Adds a `Created On` (`creation` datetime) column fetched directly from the `GL Entry` table, placed next to the `Posting Date`.
- **Posting Date Audit Highlight**: Automatically highlights rows in **red** (soft red background with bold red text) if the `Posting Date` differs from the date portion of the `Created On` timestamp.
- **Dynamic Filter Inheritance**: Synchronously inherits all filters (including dynamic Accounting Dimensions) from the standard General Ledger report.

## Directory Structure

```
report_center/
    report_center/
        report/
            general_ledger_audit/
                general_ledger_audit.json   # Report Definition
                general_ledger_audit.py     # Python wrap logic (fetch & insert columns)
                general_ledger_audit.js     # JS Formatter & Row Colorizer
```

## Installation & Setup

1. Get the app from the GitHub repository:
   ```bash
   bench get-app https://github.com/Somilvaishya/report_center.git
   ```

2. Install the app on your site:
   ```bash
   bench --site [your-site-name] install-app report_center
   ```

3. Clear cache and build assets:
   ```bash
   bench clear-cache
   ```

## License

MIT License
