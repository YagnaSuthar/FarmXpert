"""Region filtering.

`region` lists the states a variety is recommended for.  It is a crop
attribute, not a measurement, and for a given farmer it is constant - so it
is useless as a model *feature* and belongs in the filter instead.  Applying
it before scoring removes crops that cannot be grown locally at all.
"""


def matches_region(region_str, user_region):
    if not user_region:
        return True
    if region_str is None:
        return False
    hay = str(region_str).lower()
    return (user_region.lower() in hay) or ("all india" in hay)


def filter_profiles(profiles, user_region):
    """Restrict the variety table to those recommended for `user_region`."""
    if not user_region:
        return profiles
    mask = profiles["region"].apply(lambda r: matches_region(r, user_region))
    return profiles[mask].reset_index(drop=True)


def filter_rows(df, user_region):
    if not user_region:
        return df
    mask = df["region"].apply(lambda r: matches_region(r, user_region))
    return df[mask].reset_index(drop=True)


def filter_prepared(prepared, user_region):
    """Same filter, applied to the prepared list of dicts."""
    if not user_region:
        return prepared
    return [p for p in prepared if matches_region(p.get("region"), user_region)]


def known_regions(profiles):
    """Every state named in the variety table, title-cased and deduplicated.

    `region` is free text ("Rajasthan, Gujarat, All India"), so this splits on
    commas.  It exists so the serving layer can reject a region nobody grows
    anything in, instead of silently returning "nothing is suitable".
    """
    names = set()
    values = (profiles["region"] if hasattr(profiles, "columns")
              else (p.get("region") for p in profiles))
    for value in values:
        if value is None:
            continue
        for part in str(value).split(","):
            part = part.strip()
            if part:
                names.add(part)
    return names
