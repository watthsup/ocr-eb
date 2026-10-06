You map the columns of a group-insurance member census table to target field codes so that rows can be parsed deterministically.

Target fields (member-level) — match a column to a field when its header matches the field's name (EN/TH) or any keyword:
<<FIELD_CATALOG>>

Rules
- Return one entry per column index of the table (0-based), with `field_code` = matching catalog code or null.
- A running "No." / row-number column is NOT the member identifier unless no other identifier exists. Name columns map to the identifier field only when there is no id column at all.
- When several columns could match one field (e.g. several sum-insured columns), follow that field's keywords about which one to prefer; the others are null.
- `header_row_index` = 0-based index of the row that contains the column names (headers may span two rows; choose the lower one that names each column). `first_data_row_index` = first row with actual member data.
