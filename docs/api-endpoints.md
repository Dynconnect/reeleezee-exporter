# Reeleezee API Endpoints

This document lists all known Reeleezee REST API endpoints discovered through
exploration and the OData metadata endpoint.

**Base URL**: `https://portal.reeleezee.nl/api/v1/`

**Authentication**: HTTP Basic Auth

**Format**: OData v4 JSON (`{"value": [...], "@odata.nextLink": "..."}`)

**Concurrency**: Only one active session per account is allowed.

---

## Global Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `Administrations` | List all administrations |
| GET | `Administrations/{id}` | Get administration details |
| GET | `AdministrationExportInfoTypes` | Available export type definitions |
| GET | `$metadata` | OData metadata (XML) - lists all entity types |

## Administration-Scoped Endpoints

All endpoints below are prefixed with `{adminId}/`.

### Financial Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `SalesInvoices` | List all sales invoices |
| GET | `SalesInvoices/{id}` | Get full sales invoice detail (43+ fields) |
| GET | `SalesInvoices/{id}/Lines` | Get invoice line items |
| GET | `SalesInvoices/{id}/Download` | Download sales invoice PDF |
| GET | `PurchaseInvoices` | List all purchase invoices |
| GET | `PurchaseInvoices/{id}` | Get full purchase invoice detail |
| GET | `Offerings` | List all offerings/quotes |
| GET | `Offerings/{id}` | Get offering detail |
| GET | `Offerings/{id}/Download` | Download offering PDF |

### Relations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `Customers` | List all customers |
| GET | `Vendors` | List all vendors |
| GET | `Relations` | List all relations (customers + vendors) |
| GET | `Addresses` | List all addresses |

### Products & Accounts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `Products` | List all products |
| GET | `Accounts` | List all ledger accounts |

### Banking

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `BankImports` | List all bank import files |
| GET | `BankStatements` | List all bank statements |

### Documents & Files

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `Documents` | List all documents |
| GET | `PurchaseInvoiceScans` | List purchase invoice scan metadata |
| GET | `Files/{id}/Download` | Download a file by ID (scans, attachments) |

### Administration Exports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `AdministrationExports` | List available export types for this admin |
| GET | `AdministrationExports/{id}` | Get export type details |
| GET | `AdministrationExports/{id}/Download?selectedYear={year}` | Download export file for a year |

---

## Pagination

All list endpoints support OData pagination:

- Default page size is 1000 items
- `@odata.nextLink` in the response provides the URL for the next page
- Follow `@odata.nextLink` until it is absent (last page)
- The next link URL may use a different hostname than the base URL

Example:
```json
{
  "value": [{"id": "..."}, ...],
  "@odata.nextLink": "https://apiservice202548c1.reeleezee.nl/api/v1/..."
}
```

## Query Parameters

Standard OData query parameters are supported on list endpoints:

| Parameter | Example | Description |
|-----------|---------|-------------|
| `$top` | `?$top=5` | Limit number of results |
| `$filter` | `?$filter=Date gt '2024-01-01'` | Filter results |
| `selectedYear` | `?selectedYear=2024` | For export downloads |

## File Types

Purchase invoice scans have a `PhysicalFileType` field:

| Value | Extension |
|-------|-----------|
| 3 | .jpg |
| 4 | .pdf |
| 30 | .png |

## Rate Limits

- Only one active session per account
- No explicit rate limit documented, but large exports should be spaced
- Export file downloads may take up to 60 seconds for large files

## References

- [Reeleezee Developer Documentation](https://www.exact.com/nl/software/exact-reeleezee/developer-documentation)
- [API Help Page](https://portal.reeleezee.nl/api/v1/help)
- [Login & Authentication](https://www.exact.com/nl/software/exact-reeleezee/developer-documentation/login-authentication)
