param(
    [string] $ExpectedPoBCommit
)

$ErrorActionPreference = 'Stop'
$site = 'https://timelesscalc.com'
$release = Invoke-RestMethod "$site/data/engine-manifest.json" -TimeoutSec 15
$entry = $release.zorathAscendancies.Assassin
if ($entry.format -ne 'zorath-ascendancy' -or $entry.encoding -ne 'gzip-binary' -or
    $entry.seedMin -gt 6696 -or $entry.seedMax -lt 6696 -or $entry.path -notlike '/data/chunks/*') {
    throw 'Unexpected Assassin data format in the TimelessCalc manifest.'
}

$download = Invoke-WebRequest -UseBasicParsing "$site$($entry.path)" -TimeoutSec 15
$compressed = $download.RawContentStream.ToArray()
$hash = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($compressed)).ToLowerInvariant()
if ($hash -ne $entry.sha256) {
    throw 'The Assassin data does not match the TimelessCalc manifest checksum.'
}

$memory = [System.IO.MemoryStream]::new($compressed)
$decoded = [System.IO.Compression.GZipStream]::new($memory, [System.IO.Compression.CompressionMode]::Decompress)
$reader = [System.IO.BinaryReader]::new($decoded)
try {
    $selected = @(for ($seed = $entry.seedMin; $seed -le $entry.seedMax; $seed++) {
        $count = $reader.ReadByte()
        for ($index = 0; $index -lt $count; $index++) {
            $nodeId = $reader.ReadUInt16()
            if ($seed -eq 6696) { $nodeId }
        }
    })
    if ($reader.BaseStream.ReadByte() -ne -1) { throw 'Unexpected bytes after the Assassin seed data.' }
} finally {
    $reader.Dispose()
}

Write-Output "TimelessCalc $($release.dataVersion), tree $($release.treeVersion), PoB $($release.pobCommit)"
Write-Output "Assassin seed 6696 selects node $($selected -join ', '), expected 19083 (Opportunistic)."
if ($ExpectedPoBCommit -and $release.pobCommit -ne $ExpectedPoBCommit) {
    throw 'The site has not published the requested PoB revision.'
}
if ($selected.Count -ne 1 -or $selected[0] -ne 19083) {
    throw 'TimelessCalc still differs from the in-game result in PoB issue #10584.'
}
