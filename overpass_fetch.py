# ============================================================
# Roam — Daily Listings Refresh (Free — No API Key Needed)
# ============================================================
# What this script does:
#   1. Reads your existing hand-picked listings.json
#   2. For each listing, queries the Overpass API to find
#      fresh opening hours
#   3. Updates ONLY the hours + isOpenNow fields
#   4. Never adds new listings, never removes existing ones
#
# Your curated listings are always preserved exactly as-is.
# ============================================================

import requests
import json
import re
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================

# The file your website reads from
OUTPUT_FILE = "listings.json"

# ============================================================
# STEP 1 — PARSE OPENING HOURS
# OpenStreetMap stores hours in a compact format like:
#   "Mo-Fr 09:00-17:00; Sa 10:00-14:00"
# This converts that into the human-readable weekday list
# your app expects, and checks if the place is open right now.
# ============================================================

def parse_hours(hours_string):
    """
    Converts an OSM opening_hours string into a list of
    readable strings like ["Monday: 9:00 AM – 5:00 PM", ...]
    Returns (weekday_text_list, is_open_now)
    """

    if not hours_string:
        return None, None

    day_map = {
        "Mo": "Monday", "Tu": "Tuesday", "We": "Wednesday",
        "Th": "Thursday", "Fr": "Friday", "Sa": "Saturday", "Su": "Sunday"
    }
    day_order = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    day_full  = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]

    schedule = {}

    # Handle "24/7" special case
    if hours_string.strip() == "24/7":
        for full in day_full:
            schedule[full] = "Open 24 hours"
        return [f"{d}: Open 24 hours" for d in day_full], True

    # Split by semicolons to get each rule
    rules = [r.strip() for r in hours_string.split(";") if r.strip()]

    for rule in rules:
        match = re.match(
            r'^([A-Za-z,\-]+)\s+(\d{2}:\d{2})-(\d{2}:\d{2})$', rule.strip()
        )
        if not match:
            continue

        days_part  = match.group(1)
        start_time = match.group(2)
        end_time   = match.group(3)

        def to12(t):
            h, m = map(int, t.split(":"))
            period = "AM" if h < 12 else "PM"
            h = h % 12 or 12
            return f"{h}:{m:02d} {period}"

        time_str = f"{to12(start_time)} – {to12(end_time)}"

        expanded_days = []
        for part in days_part.split(","):
            part = part.strip()
            if "-" in part:
                start_d, end_d = part.split("-")
                if start_d in day_order and end_d in day_order:
                    s = day_order.index(start_d)
                    e = day_order.index(end_d)
                    expanded_days += day_order[s:e+1]
            elif part in day_order:
                expanded_days.append(part)

        for d in expanded_days:
            schedule[day_map.get(d, d)] = time_str

    result = []
    for full in day_full:
        result.append(f"{full}: {schedule[full]}" if full in schedule else f"{full}: Closed")

    # Check if open right now
    now = datetime.now()
    today_name = day_full[now.weekday()]
    is_open_now = False

    if today_name in schedule:
        time_str = schedule[today_name]
        if time_str == "Open 24 hours":
            is_open_now = True
        else:
            try:
                parts = time_str.split(" – ")
                if len(parts) == 2:
                    def parse12(t):
                        return datetime.strptime(t.strip(), "%I:%M %p").replace(
                            year=now.year, month=now.month, day=now.day
                        )
                    is_open_now = parse12(parts[0]) <= now <= parse12(parts[1])
            except:
                pass

    return result, is_open_now


# ============================================================
# STEP 2 — LOOK UP A SINGLE LISTING ON OVERPASS
# Searches for a place by name near its known coordinates.
# Returns fresh opening_hours if found, otherwise None.
# ============================================================

def fetch_hours_for_listing(listing):
    """
    Queries Overpass for a place matching this listing's name
    near its lat/lng. Returns an opening_hours string or None.
    """

    name = listing["name"]
    lat  = listing["lat"]
    lng  = listing["lng"]

    # Search within 500m of the listing's known coordinates
    query = f"""
    [out:json][timeout:25];
    (
      node["name"~"{re.escape(name)}",i](around:500,{lat},{lng});
      way["name"~"{re.escape(name)}",i](around:500,{lat},{lng});
    );
    out center tags;
    """

    url = "https://overpass-api.de/api/interpreter"

    try:
        response = requests.post(url, data={"data": query}, timeout=30)
        elements = response.json().get("elements", [])

        for el in elements:
            hours = el.get("tags", {}).get("opening_hours")
            if hours:
                return hours

    except Exception as e:
        print(f"  Warning: Overpass lookup failed for '{name}': {e}")

    return None


# ============================================================
# STEP 3 — MAIN
# Reads existing listings.json, refreshes hours for each
# entry, and writes the updated file back out.
# ============================================================

def main():
    print("Roam — Refreshing hours for existing listings...\n")

    # Load the current hand-picked listings
    with open(OUTPUT_FILE, "r") as f:
        listings = json.load(f)

    print(f"Loaded {len(listings)} listings from {OUTPUT_FILE}\n")

    updated_count = 0

    for listing in listings:
        name = listing["name"]
        print(f"Checking: {name}")

        # Skip listings that have no real-world location to look up
        # (e.g. activity ideas that span a whole area)
        if not listing.get("lat") or not listing.get("lng"):
            print(f"  Skipped — no coordinates")
            continue

        # Try to fetch fresh hours from Overpass
        hours_raw = fetch_hours_for_listing(listing)

        if hours_raw:
            hours_list, is_open_now = parse_hours(hours_raw)
            if hours_list:
                listing["hoursToday"] = hours_list
                listing["isOpenNow"]  = is_open_now if is_open_now is not None else listing.get("isOpenNow", True)
                print(f"  ✓ Updated hours")
                updated_count += 1
            else:
                print(f"  — Hours found but couldn't parse: {hours_raw}")
        else:
            # No Overpass data — just refresh isOpenNow from existing hours
            existing_hours = listing.get("hoursToday", [])
            if existing_hours:
                now = datetime.now()
                today_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][now.weekday()]
                for entry in existing_hours:
                    if entry.startswith(today_name):
                        time_part = entry.split(": ", 1)[-1]
                        if "Closed" in time_part:
                            listing["isOpenNow"] = False
                        elif "24 hours" in time_part or "Open 24" in time_part:
                            listing["isOpenNow"] = True
                        else:
                            try:
                                parts = time_part.split(" – ")
                                def parse12(t):
                                    return datetime.strptime(t.strip(), "%I:%M %p").replace(
                                        year=now.year, month=now.month, day=now.day
                                    )
                                listing["isOpenNow"] = parse12(parts[0]) <= now <= parse12(parts[1])
                            except:
                                pass
                        break
            print(f"  — No Overpass data, kept existing hours")

    # Write the updated listings back out
    with open(OUTPUT_FILE, "w") as f:
        json.dump(listings, f, indent=2)

    print(f"\nDone! Updated hours for {updated_count} listings. Total: {len(listings)} listings saved.")


if __name__ == "__main__":
    main()
