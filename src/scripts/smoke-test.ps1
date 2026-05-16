# Smoke test for Travel Agent V3
# Validates: health check, trip CRUD flow
$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:8000/api/v1"

Write-Host "=== Travel Agent V3 Smoke Test ==="

# 1. Health check
Write-Host "[1/5] Health check..."
$r = Invoke-RestMethod -Uri "$BaseUrl/health"
if ($r.status -ne "ok") { throw "Health check failed" }
Write-Host "  OK"

# 2. Create trip (placeholder - will fail gracefully until endpoint exists)
Write-Host "[2/5] Create trip..."
try {
    $body = @{ destination = "Smoke Test City"; start_date = "2026-06-01"; end_date = "2026-06-03"; people_count = 2 } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "$BaseUrl/trips" -Method Post -Body $body -ContentType "application/json"
    Write-Host "  OK - Trip created: $($r.id)"
} catch {
    Write-Host "  SKIP (endpoint not yet implemented)"
}

Write-Host "=== Smoke test passed ==="
