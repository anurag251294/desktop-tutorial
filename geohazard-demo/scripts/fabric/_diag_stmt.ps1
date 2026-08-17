$ErrorActionPreference = 'Continue'
$tok = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$ws  = "a7d0f907-bf14-4169-8d34-b8765824aa09"
$it  = "b64a14f3-fe11-4186-a27c-f8eef640a97c"
$livy = "b797f149-9d36-4417-9657-bf0307f9db32"
$app  = "application_1783008396469_0001"
$hdr = @{ Authorization = "Bearer $tok" }

$cands = @(
  "https://api.fabric.microsoft.com/v1/workspaces/$ws/notebooks/$it/livySessions/$livy",
  "https://api.fabric.microsoft.com/v1/workspaces/$ws/notebooks/$it/livySessions/$livy/statements",
  "https://api.fabric.microsoft.com/v1/workspaces/$ws/spark/livySessions/$livy",
  "https://api.fabric.microsoft.com/v1/workspaces/$ws/spark/applications/$app/driverlog",
  "https://api.fabric.microsoft.com/v1/workspaces/$ws/spark/applications/$app"
)
foreach ($c in $cands) {
  try {
    $r = Invoke-RestMethod -Headers $hdr -Uri $c
    Write-Output "==== OK $c ===="
    $r | ConvertTo-Json -Depth 10
  } catch {
    Write-Output "==== ERR $c => $($_.Exception.Response.StatusCode.value__) $($_.Exception.Message) ===="
  }
}
