# Microsoft Fabric Capacity - Administration Field Validation Test

**Date:** 2026-01-21
**API Version:** 2023-11-01

---

## Summary

The `administration` field (capacity admin) is **REQUIRED** at the REST API level, even though it may be marked as optional in Terraform/CLI. Deployments without at least one capacity administrator will fail with HTTP 400.

---

## Test 1: REST API - WITHOUT administration field

### Request
```bash
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Fabric/capacities/<capacity-name>?api-version=2023-11-01" \
  --body '{
    "location": "<location>",
    "sku": {
      "name": "F2",
      "tier": "Fabric"
    },
    "properties": {}
  }'
```

### Response
```json
{
  "error": {
    "code": "BadRequest",
    "subCode": 12,
    "message": "At least one capacity administrator is required",
    "httpStatusCode": 400
  }
}
```

**Result:** HTTP 400 Bad Request - Administration field is required

---

## Test 2: REST API - WITH administration field

### Request
```bash
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Fabric/capacities/<capacity-name>?api-version=2023-11-01" \
  --body '{
    "location": "<location>",
    "sku": {
      "name": "F2",
      "tier": "Fabric"
    },
    "properties": {
      "administration": {
        "members": ["<admin-email>"]
      }
    }
  }'
```

### Response
```json
{
  "error": {
    "code": "Unauthorized",
    "message": "Unable to authorize with Azure Active Directory.",
    "httpStatusCode": 401
  }
}
```

**Result:** HTTP 401 - Passed validation, failed on AAD authorization (user lacks Fabric Administrator role)

---

## Test 3: Azure CLI - WITHOUT administration flag

### Request
```bash
az fabric capacity create \
  --resource-group <resource-group> \
  --capacity-name <capacity-name> \
  --sku "{name:F2,tier:Fabric}" \
  --location <location>
```

### Response
```
ERROR: (BadRequest) At least one capacity administrator is required
Code: BadRequest
Message: At least one capacity administrator is required
```

**Result:** HTTP 400 Bad Request - Same error as REST API

---

## Test 4: Azure CLI - WITH administration flag

### Request
```bash
az fabric capacity create \
  --resource-group <resource-group> \
  --capacity-name <capacity-name> \
  --sku "{name:F2,tier:Fabric}" \
  --location <location> \
  --administration "{members:[<admin-email>]}"
```

### Response
```
ERROR: (Unauthorized) Unable to authorize with Azure Active Directory.
Code: Unauthorized
Message: Unable to authorize with Azure Active Directory.
```

**Result:** HTTP 401 - Passed validation, failed on AAD authorization

---

## Conclusions

### 1. Administration Field is Required
Despite being marked as **optional** in:
- Azure CLI (`az fabric capacity create --help` shows `--administration` without `[Required]`)
- Terraform azurerm provider (`administration_members` is optional)

The underlying **REST API requires at least one capacity administrator**. Omitting this field results in:
```
HTTP 400 Bad Request
"At least one capacity administrator is required"
```

### 2. Terraform Implications
Terraform deployments that leave `administration_members` blank will **fail at apply time** with the same 400 error. This is likely a schema inconsistency in the Terraform provider.

### 3. Documentation Reference
- REST API Spec: https://learn.microsoft.com/en-us/rest/api/microsoftfabric/fabric-capacities/create-or-update
- The spec shows `properties.administration` as **Required: True**

---

## Recommendation

Treat `administration_members` as a **mandatory field** in Terraform configurations, regardless of what the provider schema indicates. The API will reject requests without it.

### Example Terraform Configuration
```hcl
resource "azurerm_fabric_capacity" "example" {
  name                = "examplecapacity"
  resource_group_name = azurerm_resource_group.example.name
  location            = "eastus"

  sku {
    name = "F2"
    tier = "Fabric"
  }

  # REQUIRED - despite being marked optional in provider
  administration_members = ["admin@contoso.com"]
}
```

---

## Who Can Manage Capacity After Creation

Based on documentation:
1. **Fabric Administrator** (tenant-level role) - Can create/delete capacities
2. **Capacity Admin** (assigned in administration_members) - Can manage capacity settings
3. **Azure RBAC Owner/Contributor** on the capacity resource - Can manage via ARM/Terraform
