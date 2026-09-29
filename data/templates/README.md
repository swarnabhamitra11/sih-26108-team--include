# CSV Seed Templates – Data Entry Guide

This directory contains **template CSV files** showing the required headers and column formats for data entry.

**Rules for humans filling these sheets:**
1. **Never enter database IDs** (no `id`, `family_id`, `standard_id`, etc.). All cross-references use natural keys:
   - Standards are identified by `(is_number, part)`.
   - Editions are identified by `(is_number, part, edition_year)`.
2. **Leave verification lifecycle columns at their defaults**:
   - `verification_status` defaults to `'entered'`. Do not include or edit this column.
   - `verified` (in certification rules) defaults to `FALSE`. Someone else verifies these later.
3. **Format conventions**:
   - `part` must be a bare number or label (e.g. `1`, `2`) or empty for single-part standards. Do not include `Part` or `(Part 1)`.
   - `is_number` must be the base designation (e.g. `IS 0000`, `IS 0001`, `IS/ISO 0000`). It must NOT include years (`:2015`) or `Part`.
   - `keywords` are comma-separated in a single cell (aim for at least 5 keywords).
   - `source_url` is required on every row.

---

## File Reference & Column Specifications

### 1. `standards.csv`
Primary record for each Indian Standard.

| Column | Type | Allowed Values / Format | Description |
|---|---|---|---|
| `is_number` | text | `IS <number>` or `IS/ISO <number>` (e.g. `IS 0000`) | Base standard number. Required. |
| `part` | text | Digits or bare string (e.g. `1`), or empty | Part designation. Empty if standard has no parts. |
| `title` | text | Non-empty text | Title of the standard. Required. |
| `product_group` | text | `Cement`, `Steel`, `Cables`, `Pipes`, `Pumps` | Product group name. |
| `category` | text | `material`, `method`, `code`, `specification` | Functional category. |
| `scope_text` | text | Non-empty text (ideally <= 600 chars) | Summary of the standard scope. Required. |
| `keywords` | text | Comma-separated strings | Search keywords (e.g. `"pipe, steel, water, pressure, joint"`). |
| `status` | enum | `current`, `superseded`, `withdrawn` | Standard status. Default is `current`. |
| `superseded_by_is_number` | text | Valid `is_number` from standards.csv, or empty | Target standard base number. Required if status is `superseded`; must be empty otherwise. |
| `superseded_by_part` | text | Valid `part` from standards.csv, or empty | Target standard part. Required if status is `superseded`; must be empty otherwise. |
| `source_url` | text | Valid URL (e.g. `https://standards.bis.gov.in/...`) | Official BIS source reference URL. Required. |
| `source_note` | text | Free text or empty | Context note about source verification. |

### 2. `standard_editions.csv`
Published revision years for each standard.

| Column | Type | Allowed Values / Format | Description |
|---|---|---|---|
| `is_number` | text | References `standards.is_number` | Standard base number. Required. |
| `part` | text | References `standards.part` | Standard part, or empty. |
| `edition_year` | integer | `1900` to `current year + 1` | 4-digit publication year. Required. |
| `is_latest` | boolean | `TRUE`, `true`, `1` / `FALSE`, `false`, `0` | Exactly one edition per standard should be `TRUE`. Required. |
| `notes` | text | Free text or empty | Notes on the edition. |

### 3. `standard_amendments.csv`
Formal amendments issued against specific editions.

| Column | Type | Allowed Values / Format | Description |
|---|---|---|---|
| `is_number` | text | References `standards.is_number` | Standard base number. Required. |
| `part` | text | References `standards.part` | Standard part, or empty. |
| `edition_year` | integer | References `standard_editions.edition_year` | Edition year this amendment applies to. Required. |
| `amendment_no` | integer | Integer >= 1 | Amendment number (1, 2, 3...). Required. |
| `year` | integer | `1900` to `current year + 1` or empty | Year amendment was published. |
| `notes` | text | Free text or empty | Short description of changes. |

### 4. `standard_relations.csv`
Relationships/cross-references between standards (graph edges).

| Column | Type | Allowed Values / Format | Description |
|---|---|---|---|
| `from_is_number` | text | References `standards.is_number` | Origin standard base number. Required. |
| `from_part` | text | References `standards.part` | Origin standard part, or empty. |
| `to_is_number` | text | References `standards.is_number` | Target standard base number. Required. (Cannot equal origin). |
| `to_part` | text | References `standards.part` | Target standard part, or empty. |
| `relation_type` | enum | `normative_ref`, `test_method`, `terminology`, `safety`, `installation`, `product` | Type of relationship. |
| `notes` | text | Free text or empty | Context note on the reference. |

### 5. `certification_rules.csv` (Optional Seed)
Quality Control Orders (QCO) and BIS certification status.

| Column | Type | Allowed Values / Format | Description |
|---|---|---|---|
| `is_number` | text | References `standards.is_number` | Standard base number. Required. |
| `part` | text | References `standards.part` | Standard part, or empty. |
| `status` | enum | `mandatory`, `voluntary`, `needs_review` | Certification status. Required. |
| `order_reference` | text | Free text | QCO gazette / ministry order reference. |
| `source_note` | text | Non-empty if status is `mandatory` | Source documentation citation. |
| `product_scope_text` | text | Free text or empty | Exact product scope covered under QCO. |
| `scope_keywords` | text | Comma-separated strings | Specific product keywords under certification. |

### 6. `benchmark_rows.csv` & `benchmark_expected.csv` (Optional Seed)
Evaluation benchmarks for search and retrieval testing.

- **`benchmark_rows.csv`**:
  - `query`: The search prompt text.
  - `language`: Query language (e.g. `en`, `hi`).
  - `kind`: `normal` (must have >= 1 primary expected standard) or `abstain` (must have 0 expected standards).
  - Note: `verification_status` defaults to `entered`. A row may only be marked `verified` if all its referenced standards in `benchmark_expected` are already `verified`.
- **`benchmark_expected.csv`**:
  - `query`: Exact match to `benchmark_rows.query`.
  - `is_number`: References `standards.is_number`.
  - `part`: References `standards.part`, or empty.
  - `role`: `primary` (direct answer) or `allied` (secondary/supporting standard).
