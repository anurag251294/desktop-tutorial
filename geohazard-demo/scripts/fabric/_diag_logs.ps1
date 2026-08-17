$ErrorActionPreference = 'Stop'
$tok = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$ws = "a7d0f907-bf14-4169-8d34-b8765824aa09"
$it = "b64a14f3-fe11-4186-a27c-f8eef640a97c"
$hdr = @{ Authorization = "Bearer $tok" }

$r = Invoke-RestMethod -Headers $hdr -Uri "https://api.fabric.microsoft.com/v1/workspaces/$ws/spark/livySessions"
$sessions = $r.value | Where-Object { $_.item.itemId -eq $it }
Write-Output "=== silver sessions: $($sessions.Count) ==="
$sessions |
  Select-Object state, sparkApplicationId, livyId, submittedDateTime, jobInstanceId, cancellationReason |
  Sort-Object submittedDateTime -Descending |
  Format-List
