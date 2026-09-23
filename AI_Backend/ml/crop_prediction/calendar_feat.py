"""Turn the dataset's `sowing_month` into an honest farmer-supplied month.

`sowing_month` is stored as a crop-level window such as "April-May".  With
only ten distinct windows, five of them identify a single crop outright, so
feeding the raw string to the model lets it read the label off the calendar.

A farmer does not supply a window - they supply the one month they intend to
sow in.  Expanding each window to its constituent months and drawing one per
row produces a 12-value feature that several crops legitimately share, which
is what the farmer actually knows at prediction time.
"""
import numpy as np

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
_IDX = {m: i for i, m in enumerate(MONTHS)}


def window_to_months(window):
    """'August-October' -> ['August', 'September', 'October']."""
    window = str(window).strip()
    if "-" not in window:
        return [window] if window in _IDX else MONTHS
    start, end = [p.strip() for p in window.split("-", 1)]
    if start not in _IDX or end not in _IDX:
        return MONTHS
    i, j = _IDX[start], _IDX[end]
    span = (j - i) % 12
    return [MONTHS[(i + k) % 12] for k in range(span + 1)]


def assign_sowing_month(df, seed=42):
    """Draw one concrete sowing month per row from that crop's window."""
    rng = np.random.default_rng(seed)
    months = []
    for w in df["sowing_month"]:
        choices = window_to_months(w)
        months.append(choices[rng.integers(len(choices))])
    return months
