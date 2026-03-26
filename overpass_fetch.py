# ============================================================
# Roam — Free Listings Fetcher (Overpass API)
# ============================================================
# What this script does:
#   1. Queries the Overpass API (free, no key needed)
#      for activity spots near Bethesda, MD
#   2. Merges the results with your manually curated
#      sponsored/featured listings so they're never overwritten
#   3. Calculates isOpenNow from the hours data
#   4. Saves everything into a fresh listings.json file
#
# No API key. No billing. No account. Completely free forever.
#
# Run this script every morning via GitHub Actions to keep
# your app updated automatically.
# ============================================================

import requests
import json
import re
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================

# Center of search — downtown Bethesda
LATITUDE  = 38.9848
LONGITUDE = -77.0947

# Search radius in meters (8000m = ~5 miles)
RADIUS = 8000

# Output file your website reads from
OUTPUT_FILE = "listings.json"

# ============================================================
# SPONSORED / FEATURED LISTINGS
# These are your manually curated paid placements.
# They will ALWAYS appear in the final output and will
# NEVER be overwritten by the automated fetch.
# When a business pays you, add them here.
# ============================================================

SPONSORED_LISTINGS = [
  # Example — uncomment and fill in when you get a paying business:
  # {
  #   "id": "escape-quest-pike-rose",
  #   "name": "Escape Quest — Pike & Rose",
  #   "category": "Activities",
  #   "address": "11810 Grand Park Ave, North Bethesda, MD 20852",
  #   "lat": 39.0448,
  #   "lng": -77.1197,
  #   "phone": "(301) 881-9103",
  #   "website": "https://www.escapequest.com",
  #   "isOpenNow": True,
  #   "hoursToday": [
  #     "Monday: 12:00 PM – 10:00 PM",
  #     "Friday: 12:00 PM – 11:00 PM",
  #     "Saturday: 10:00 AM – 11:00 PM",
  #     "Sunday: 10:00 AM – 10:00 PM"
  #   ],
  #   "priceLevel": 2,
  #   "priceLabel": "From $28/person",
  #   "priceTier": "paid",
  #   "priceMax": 35,
  #   "photo": None,
  #   "description": "The only escape rooms at Pike & Rose. Book online or walk in.",
  #   "rating": 4.6,
  #   "reviewCount": 543,
  #   "types": ["amusement_park"],
  #   "featured": True,
  #   "sponsored": True,
  #   "sponsoredCta": "Book a room"
  # },
]

# ============================================================
# WHAT TO SEARCH FOR
# Each entry maps an OpenStreetMap amenity/leisure tag
# to a Roam category and price tier.
# Full tag list: https://wiki.openstreetmap.org/wiki/Map_features
# ============================================================

SEARCH_TARGETS = [
    { "tag": "leisure=park",            "category": "Outdoors",       "priceTier": "free",  "priceLabel": "Free",        "priceMax": 0  },
    { "tag": "leisure=nature_reserve",  "category": "Outdoors",       "priceTier": "free",  "priceLabel": "Free",        "priceMax": 0  },
    { "tag": "amenity=library",         "category": "Education",      "priceTier": "free",  "priceLabel": "Free",        "priceMax": 0  },
    { "tag": "tourism=museum",          "category": "Arts",           "priceTier": "free",  "priceLabel": "Free",        "priceMax": 0  },
    { "tag": "tourism=gallery",         "category": "Arts",           "priceTier": "free",  "priceLabel": "Free",        "priceMax": 0  },
    { "tag": "amenity=cinema",          "category": "Entertainment",  "priceTier": "cheap", "priceLabel": "From $10",    "priceMax": 16 },
    { "tag": "leisure=bowling_alley",   "category": "Activities",     "priceTier": "paid",  "priceLabel": "From $15",    "priceMax": 27 },
    { "tag": "leisure=trampoline_park", "category": "Activities",     "priceTier": "paid",  "priceLabel": "From $20",    "priceMax": 55 },
    { "tag": "leisure=escape_game",     "category": "Activities",     "priceTier": "paid",  "priceLabel": "From $25",    "priceMax": 35 },
    { "tag": "leisure=ice_rink",        "category": "Activities",     "priceTier": "cheap", "priceLabel": "From $8",     "priceMax": 15 },
    { "tag": "leisure=fitness_centre",  "category": "Fitness",        "priceTier": "paid",  "priceLabel": "From $15",    "priceMax": 30 },
    { "tag": "amenity=theatre",         "category": "Arts",           "priceTier": "free",  "priceLabel": "Free–$30",    "priceMax": 30 },
    { "tag": "leisure=garden",          "category": "Outdoors",       "priceTier": "free",  "priceLabel": "Free",        "priceMax": 0  },
    { "tag": "leisure=miniature_golf",  "category": "Activities",     "priceTier": "cheap", "priceLabel": "From $8",     "priceMax": 12 },
]

# ============================================================
# STEP 1 — QUERY OVERPASS API
# Overpass is a free API that queries OpenStreetMap data.
# We send it a query and it returns matching places.
# ============================================================

def fetch_overpass(tag):
    """
    Queries the Overpass API for all places matching
    a given tag within our search radius of Bethesda.
    Returns a list of elements (nodes and ways).
    """

    # Split the tag into key and value (e.g. "leisure=park")
    key, value = tag.split("=")

    # Build the Overpass query language (QL) string
    # This asks for both nodes (points) and ways (polygons)
    # within our radius around Bethesda
    query = f"""
    [out:json][timeout:25];
    (
      node["{key}"="{value}"](around:{RADIUS},{LATITUDE},{LONGITUDE});
      way["{key}"="{value}"](around:{RADIUS},{LATITUDE},{LONGITUDE});
    );
    out center tags;
    """

    # The public Overpass API endpoint — completely free
    url = "https://overpass-api.de/api/interpreter"

    try:
        response = requests.post(url, data={"data": query}, timeout=30)
        data = response.json()
        return data.get("elements", [])
    except Exception as e:
        print(f"  Warning: Overpass query failed for {tag}: {e}")
        return []


# ============================================================
# STEP 2 — PARSE OPENING HOURS
# OpenStreetMap stores hours in a compact format like:
#   "Mo-Fr 09:00-17:00; Sa 10:00-14:00"
# This function converts that into the human-readable
# weekday list your app expects, and checks if open now.
# ============================================================

def parse_hours(hours_string):
    """
    Converts OSM opening_hours string into a list of
    readable strings like ["Monday: 9:00 AM – 5:00 PM", ...]
    Returns (weekday_text_list, is_open_now)
    """

    if not hours_string:
        return [], None

    # Day mapping from OSM abbreviations to full names
    day_map = {
        "Mo": "Monday", "Tu": "Tuesday", "We": "Wednesday",
        "Th": "Thursday", "Fr": "Friday", "Sa": "Saturday", "Su": "Sunday"
    }
    day_order = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    day_full = ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"]

    # Build a schedule dict: {"Monday": "9:00 AM – 5:00 PM", ...}
    schedule = {}

    # Handle "24/7" special case
    if hours_string.strip() == "24/7":
        for full in day_full:
            schedule[full] = "Open 24 hours"
        is_open_now = True
        return [f"{d}: {schedule[d]}" for d in day_full], is_open_now

    # Split by semicolons to get each rule
    rules = [r.strip() for r in hours_string.split(";") if r.strip()]

    for rule in rules:
        # Try to extract day range and time
        # Pattern: "Mo-Fr 09:00-17:00" or "Sa 10:00-14:00"
        match = re.match(
            r'^([A-Za-z,\-]+)\s+(\d{2}:\d{2})-(\d{2}:\d{2})$', rule.strip()
        )
        if not match:
            continue

        days_part  = match.group(1)
        start_time = match.group(2)
        end_time   = match.group(3)

        # Convert 24hr to 12hr format
        def to12(t):
            h, m = map(int, t.split(":"))
            period = "AM" if h < 12 else "PM"
            h = h % 12 or 12
            return f"{h}:{m:02d} {period}"

        time_str = f"{to12(start_time)} – {to12(end_time)}"

        # Expand day ranges like "Mo-Fr" into individual days
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
            full_name = day_map.get(d, d)
            schedule[full_name] = time_str

    # Build the final list in correct day order
    result = []
    for full in day_full:
        if full in schedule:
            result.append(f"{full}: {schedule[full]}")
        else:
            result.append(f"{full}: Closed")

    # Check if open right now
    now = datetime.now()
    today_name = day_full[now.weekday()]  # Monday=0
    is_open_now = False

    if today_name in schedule:
        time_str = schedule[today_name]
        if time_str == "Open 24 hours":
            is_open_now = True
        else:
            try:
                # Parse the formatted time back to compare
                parts = time_str.split(" – ")
                if len(parts) == 2:
                    def parse12(t):
                        return datetime.strptime(t.strip(), "%I:%M %p").replace(
                            year=now.year, month=now.month, day=now.day
                        )
                    open_t  = parse12(parts[0])
                    close_t = parse12(parts[1])
                    is_open_now = open_t <= now <= close_t
            except:
                pass

    return result, is_open_now


# ============================================================
# STEP 3 — GENERATE A CLEAN ID
# Converts "Cabin John Regional Park" → "cabin-john-regional-park"
# ============================================================

def make_id(name):
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s-]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    return name[:60]


# ============================================================
# STEP 4 — FORMAT A SINGLE ELEMENT
# Takes a raw Overpass element and formats it into
# the clean listing object your website expects.
# ============================================================

def format_element(element, target):
    tags = element.get("tags", {})

    # Get coordinates — ways have a "center", nodes are direct
    if element["type"] == "way":
        center = element.get("center", {})
        lat = center.get("lat")
        lng = center.get("lon")
    else:
        lat = element.get("lat")
        lng = element.get("lon")

    # Skip if no name or coordinates
    name = tags.get("name") or tags.get("official_name")
    if not name or not lat or not lng:
        return None

    # Parse hours
    hours_raw = tags.get("opening_hours", "")
    hours_list, is_open_now = parse_hours(hours_raw)

    # If no hours data, default to assuming open
    if is_open_now is None:
        is_open_now = True

    # Build address from OSM address tags
    house   = tags.get("addr:housenumber", "")
    street  = tags.get("addr:street", "")
    city    = tags.get("addr:city", "")
    state   = tags.get("addr:state", "MD")
    address = f"{house} {street}, {city}, {state}".strip(", ")
    if not address or address == ", , MD":
        address = f"Near Bethesda, MD"

    return {
        "id":           make_id(name),
        "name":         name,
        "category":     target["category"],
        "address":      address,
        "lat":          lat,
        "lng":          lng,
        "phone":        tags.get("phone", tags.get("contact:phone", "")),
        "website":      tags.get("website", tags.get("contact:website", "")),
        "isOpenNow":    is_open_now,
        "hoursToday":   hours_list,
        "priceLevel":   None,
        "priceLabel":   target["priceLabel"],
        "priceTier":    target["priceTier"],
        "priceMax":     target["priceMax"],
        "photo":        None,
        "description":  tags.get("description", ""),
        "rating":       None,
        "reviewCount":  0,
        "types":        [target["tag"].split("=")[0]],
        "featured":     False,
        "sponsored":    False,
        "sponsoredCta": None,
    }


# ============================================================
# STEP 5 — MAIN FUNCTION
# Ties everything together and writes listings.json
# ============================================================

def main():
    print("Roam — Fetching listings from Overpass API (free)...")
    print(f"Searching within {RADIUS/1000:.0f}km of Bethesda, MD\n")

    all_listings = []
    seen_ids = set()

    # Start with sponsored listings — they always come first
    # and are never overwritten
    for listing in SPONSORED_LISTINGS:
        all_listings.append(listing)
        seen_ids.add(listing["id"])
        print(f"  ★ Sponsored: {listing['name']}")

    # Fetch each category from Overpass
    for target in SEARCH_TARGETS:
        tag = target["tag"]
        print(f"Fetching: {tag}...")

        elements = fetch_overpass(tag)
        print(f"  Found {len(elements)} raw results")

        added = 0
        for element in elements:
            listing = format_element(element, target)
            if not listing:
                continue

            # Skip duplicates
            if listing["id"] in seen_ids:
                continue
            seen_ids.add(listing["id"])

            all_listings.append(listing)
            added += 1

        print(f"  Added {added} listings")

    # ── SORT ──
    # Sponsored first, then by price tier, then alphabetically
    tier_order = {"free": 0, "cheap": 1, "paid": 2}

    sponsored   = [l for l in all_listings if l["sponsored"]]
    unsponsored = [l for l in all_listings if not l["sponsored"]]

    unsponsored.sort(key=lambda x: (
        tier_order.get(x["priceTier"], 3),
        x["name"]
    ))

    final = sponsored + unsponsored

    # ── SAVE ──
    with open(OUTPUT_FILE, "w") as f:
        json.dump(final, f, indent=2)

    open_count = sum(1 for l in final if l["isOpenNow"])
    print(f"\nDone! Saved {len(final)} listings ({open_count} open now) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
