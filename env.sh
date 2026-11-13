# Project-only secrets, read from macOS Keychain. Usage: source env.sh
export APIFY_TOKEN=$(security find-generic-password -a "$USER" -s "APIFY_TOKEN" -w 2>/dev/null)
export FEATHERLESS_API_KEY=$(security find-generic-password -a "$USER" -s "FEATHERLESS_API_KEY" -w 2>/dev/null)
export SUPABASE_ACCESS_TOKEN=$(security find-generic-password -a "$USER" -s "SUPABASE_ACCESS_TOKEN" -w 2>/dev/null)
