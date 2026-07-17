$ErrorActionPreference = 'Continue'

$workDir = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('RDpcR2l0aHViXGppcmEtY2xhdWRlLXBsdWdpbg=='))
$sessionName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('6rWs7ZiE'))
$prompt = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('7Yag7YGwIOu2gOyhseycvOuhnCDsnbTsoIQg7J6R7JeF7J20IOykkeuLqOuQmOyXiOuLpOuptCDtmITsnqwg7KCA7J6l7IaM7JmAIOq4sOyhtCDshLjshZjsnZgg7KeE7ZaJIOyDge2ZqeydhCDtmZXsnbjtlZjqs6Ag7KSR64uo65CcIOyngOygkOu2gO2EsCDsnbTslrTshJwg7KeE7ZaJ7ZWY6528LiDquLDsobQg6rOE7ZqN7JeQIOuCqOydgCDsnpHsl4XsnYAg67OE64+EIOyKueyduCDsl4bsnbQg6rOE7IaNIOyEpOqzhMK36rWs7ZiE7ZWY6rOgLCDtlYTsmpTtlZwg66y47IScIOyekeyEseqzvCDthYzsiqTtirjCt+qygOymneq5jOyngCDsmYTro4ztlZjrnbwuIOyZhOujjOuQnCDsnpHsl4XsnYAg7J2Y66+4IOyeiOuKlCDri6jsnITroZwg7Luk67CL7ZWY6rOgIO2YhOyerCDruIzrnpzsuZjsl5Ag7ZG47Iuc7ZWY6528LiDsnbTrr7gg7JmE66OM65CcIOyekeyXheydhCDrsJjrs7XtlZjsp4Ag66eQ6rOgIOuCqOydgCDsnpHsl4XsnbQg7JeG64uk66m0IOyVhOustOqyg+uPhCDrs4Dqsr3tlZjsp4Ag66eQ6rOgIOyiheujjO2VmOudvC4='))
$logPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('RDpcR2l0aHViXGppcmEtY2xhdWRlLXBsdWdpblxjbGF1ZGUtc2NoZWR1bGVkLmxvZw=='))
$claudeExe = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('QzpcVXNlcnNcdXNlclwubG9jYWxcYmluXGNsYXVkZS5leGU='))
$skipPermissions = [bool]::Parse('True')

Set-Location -LiteralPath $workDir

"==== START $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) : $sessionName ====" |
  Out-File -FilePath $logPath -Append -Encoding utf8

$claudeArgs = @(
  '-r', $sessionName,
  '-p', $prompt
)

if ($skipPermissions) {
  $claudeArgs += '--dangerously-skip-permissions'
}

& $claudeExe @claudeArgs *>> $logPath

"
==== END $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) : EXIT $LASTEXITCODE ====
" |
  Out-File -FilePath $logPath -Append -Encoding utf8

exit $LASTEXITCODE
