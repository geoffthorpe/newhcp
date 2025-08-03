# This will generate a glob-compatible wildcard string for any ekpubhash
# inputs that are less than 32 bytes (64 hex characters).
def ekpubhash2path(ekpubhash):
    if len(ekpubhash) < 2:
        return f"/example/db/{ekpubhash[0:2]}*/*/*"
    if len(ekpubhash) < 4:
        return f"/example/db/{ekpubhash[0:2]}/{ekpubhash[0:4]}*/*"
    if len(ekpubhash) < 64:
        return f"/example/db/{ekpubhash[0:2]}/{ekpubhash[0:4]}/{ekpubhash}*"
    if len(ekpubhash) > 64:
        raise Exception('ekpubhash greater than 64 characters')
    return f"/example/db/{ekpubhash[0:2]}/{ekpubhash[0:4]}/{ekpubhash}"
