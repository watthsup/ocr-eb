You are extracting a group-insurance MEMBER CENSUS (รายชื่อผู้ขอเอาประกัน / employee roster) into the target schema below.

# Target schema (defined by business analysts — authoritative)
Scope "group" fields are reported once per member; scope "case" fields once in `case_fields`. Use the name (EN/TH), keywords and allowed values of each field to decide which column maps to it.

<<FIELD_CATALOG>>

# Conventions
- Groups = members. group_key = the member identifier column (see the id field's keywords); fallback: running number as printed, else "row-N". group_label = name if printed.
- Enum fields: output one of the allowed values, using the allowed-value labels to translate what is printed (Thai or English).
- Dates DD/MM/YYYY in AD — Thai sheets print พ.ศ. (e.g. 08/10/2528 → 08/10/1985). Ages as printed (do not compute).
- When several columns could match one field (e.g. several sum-insured columns), follow the field's keywords about which one to use; leave the others out.
- Skip total / summary rows. Numbers digits only. evidence = the raw cell text.
- Case-scope count fields = the number of member rows you output, only if the document is complete in this context.
