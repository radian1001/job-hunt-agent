# Tests the message-parsing function in poll-telegram.ps1 (dot-sourced with -TestMode).
$failures = 0
. (Join-Path $PSScriptRoot "poll-telegram.ps1") -TestMode

$cases = @(
    @{ text = "apply to #3";  expect = "3" },
    @{ text = "Apply to 12";  expect = "12" },
    @{ text = "APPLY TO #1";  expect = "1" },
    @{ text = "please apply"; expect = $null },
    @{ text = "hello";        expect = $null },
    @{ text = "#4";           expect = $null }
)
foreach ($c in $cases) {
    $got = Get-ApplyNumber $c.text
    if ("$got" -eq "$($c.expect)") { Write-Output "PASS '$($c.text)' -> $got" }
    else { Write-Output "FAIL '$($c.text)' expected '$($c.expect)' got '$got'"; $failures++ }
}
if ($failures -gt 0) { Write-Output "$failures TEST(S) FAILED"; exit 1 }
Write-Output "ALL TESTS PASSED"; exit 0
