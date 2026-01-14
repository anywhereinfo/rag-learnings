# Test Playbook with Intentional Conflicts and Duplicates
# This is a test file to demonstrate the validation script

## 🚨 CRITICAL (Violated in >75% of generations)

### Rule: operationId Naming Convention
- Use snake_case for operationId naming
- operationId must use camelCase format
- Always use camelCase for operationId (e.g., getGateway, not get_gateway)

### Rule: Component Schema Naming
- Component schemas should be PascalCase
- Use PascalCase for all component schema names

## ⚠️ MODERATE (Violated in 25-75% of generations)

### Rule: ETag Header Usage
- Include ETag header on all GET responses
- ETag header should only be included on single-resource GET responses, not collections
- Never include ETag on collection endpoints

### Rule: DELETE Response Bodies
- DELETE operations should return 200 with a success message
- DELETE operations must return 204 with no response body
- Use 204 No Content for successful DELETE operations

## ✅ PRE-SUBMISSION CHECKLIST
- All operationId values are camelCase
- All operationId values use snake_case format
- All component schemas are PascalCase
- DELETE operations return 204 with no body
- DELETE operations include a response body with status message
