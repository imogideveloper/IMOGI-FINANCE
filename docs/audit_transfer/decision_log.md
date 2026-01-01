# Transfer Application Decision Log

- **Environment constraint:** Bench/site context is unavailable in the container, so database-level duplicate checks could not be executed. Proceeded based on codebase inventory and native ERPNext expectations.
- **Existing options evaluated:**
  - *Administrative Payment Voucher* posts Payment Entries and enforces accounting flows → rejected for transfer-instruction use to avoid mixing with posting logic.
  - *Customer Receipt* and other receipt/tax doctypes are inbound or compliance-oriented → not applicable to outbound transfer instructions.
- **Decision (latest scan 2026-01-01):** The app already contains the **Transfer Application** DocType, workflow, print format, settings, and Payment Entry/Bank Transaction linkages. Continue using this module as the canonical non-accounting transfer instruction document rather than introducing any new “transfer” doctypes.
- **Reuse plan:**
  - Leverage native Payment Entry for actual postings; Transfer Application will only orchestrate and link.
  - Reuse native Bank Transaction for evidence-based matching; add lightweight custom fields for linkage and match confidence.
  - Keep optional settings in a Single DocType to control matching and auto-PE creation.
