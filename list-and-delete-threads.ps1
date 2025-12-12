# PowerShell script to list and delete all threads

Write-Host "=== Listing All Threads ===" -ForegroundColor Green
$listResponse = Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/agent/threads' -Method Get
$listResponse | ConvertTo-Json -Depth 5

# Extract thread IDs
$threadIds = @()
if ($listResponse.data.threads) {
    foreach ($thread in $listResponse.data.threads) {
        if ($thread.thread_id) {
            $threadIds += $thread.thread_id
        }
    }
}

Write-Host "`n=== Found $($threadIds.Count) Thread(s) ===" -ForegroundColor Yellow
if ($threadIds.Count -gt 0) {
    Write-Host "Thread IDs:" -ForegroundColor Cyan
    $threadIds | ForEach-Object { Write-Host "  - $_" -ForegroundColor White }
    
    Write-Host "`n=== Deleting All Threads ===" -ForegroundColor Red
    
    # Option 1: Bulk delete (if available)
    if ($threadIds.Count -gt 0) {
        $bulkBody = @{
            thread_ids = $threadIds
        } | ConvertTo-Json
        
        try {
            $bulkResponse = Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/agent/threads/bulk' -Method Delete -Body $bulkBody -ContentType 'application/json'
            Write-Host "Bulk Delete Result:" -ForegroundColor Green
            $bulkResponse | ConvertTo-Json -Depth 5
        } catch {
            Write-Host "Bulk delete failed, trying individual deletes..." -ForegroundColor Yellow
            
            # Option 2: Delete individually
            $successCount = 0
            $failCount = 0
            
            foreach ($threadId in $threadIds) {
                try {
                    $deleteResponse = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/agent/threads/$threadId" -Method Delete
                    Write-Host "  ✓ Deleted: $threadId" -ForegroundColor Green
                    $successCount++
                } catch {
                    Write-Host "  ✗ Failed: $threadId - $($_.Exception.Message)" -ForegroundColor Red
                    $failCount++
                }
            }
            
            Write-Host "`n=== Summary ===" -ForegroundColor Cyan
            Write-Host "  Successfully deleted: $successCount" -ForegroundColor Green
            Write-Host "  Failed: $failCount" -ForegroundColor Red
        }
    }
} else {
    Write-Host "No threads found to delete." -ForegroundColor Yellow
}






