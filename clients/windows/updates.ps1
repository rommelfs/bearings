# SPDX-License-Identifier: AGPL-3.0-or-later
# Read local WUA metadata only. No online scan, download, install or policy change.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Read-Updates($installed) {
    try {
        $session = New-Object -ComObject Microsoft.Update.Session
        $session.ClientApplicationID = 'Bearings inventory'
        $searcher = $session.CreateUpdateSearcher()
        $searcher.Online = $false
        $searcher.CanAutomaticallyUpgradeService = $false
        $searcher.IncludePotentiallySupersededUpdates = $true
        $result = $searcher.Search("IsInstalled=$installed and Type='Software'")
        if ([int]$result.ResultCode -notin @(2,3)) { throw 'incomplete search' }
        $rows = @()
        $total = [int]$result.Updates.Count
        if ($total -gt 100000) { throw 'collection too large' }
        for ($i=0; $i -lt [Math]::Min($total,250); $i++) {
            $u = $result.Updates.Item($i)
            $title = [string]$u.Title -replace '[\x00-\x1f\x7f]', ' '
            # Preserve Unicode scalar boundaries when bounding localized titles.
            if ($title.Length -gt 239) {
                $title = $title.Substring(0,239)
                if ([char]::IsHighSurrogate($title[$title.Length-1])) { $title=$title.Substring(0,$title.Length-1) }
            }
            $kbs = @($u.KBArticleIDs | ForEach-Object { 'KB' + [string]$_ })
            if ($kbs.Count -gt 16) { throw 'too many KB identifiers' }
            $rows += @{id=([guid]$u.Identity.UpdateID).ToString(); revision=[int]$u.Identity.RevisionNumber; title=$title; kbs=$kbs; hidden=[bool]$u.IsHidden}
        }
        $truncated = $total -gt $rows.Count
        $status = 'ok'
        if ([int]$result.ResultCode -eq 3 -or $truncated) { $status='partial' }
        return @{status=$status; total=$total; truncated=$truncated; updates=@($rows)}
    } catch {
        return @{status='error'; total=$null; truncated=$false; updates=@()}
    }
}
$reboot = 'unknown'
try {
    $systemInfo = New-Object -ComObject Microsoft.Update.SystemInfo
    if ($systemInfo.RebootRequired) { $reboot='present' } else { $reboot='not_observed' }
} catch {}
$cacheDate = ''
try {
    # WUA documents this COM DATE as UTC; do not reinterpret it as local time.
    $auto = New-Object -ComObject Microsoft.Update.AutoUpdate
    $date = [datetime]$auto.Results.LastSearchSuccessDate
    if ($date.Year -ge 2000) { $cacheDate=[datetime]::SpecifyKind($date,[DateTimeKind]::Utc).ToString('yyyy-MM-ddTHH:mm:ssZ') }
} catch {}
@{source='windows-update-agent-cache'; cache_last_search_at=$cacheDate; reboot=$reboot;
  installed=(Read-Updates 1); pending=(Read-Updates 0)} | ConvertTo-Json -Depth 6 -Compress
