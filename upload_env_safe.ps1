$envContent = Get-Content .env
foreach ($line in $envContent) {
    if ($line -match '^\s*([^#\s=]+)\s*=\s*(.*)$') {
        $key = $matches[1]
        $val = $matches[2].Trim()
        
        # Remove surrounding quotes if they exist
        if ($val -match '^"(.*)"$') {
            $val = $matches[1]
        } elseif ($val -match "^'(.*)'$") {
            $val = $matches[1]
        }
        
        if ($val) {
            Write-Host "Adding $key"
            $val | npx vercel env add $key production
        }
    }
}
Write-Host "Done adding env variables."
