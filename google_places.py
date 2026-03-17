# ============================================================
# HangOut — Google Places Fetcher
# ============================================================
# What this script does:
#   1. Takes a list of activity types (parks, bowling, etc.)
#   2. Searches Google Places for each one near Bethesda, MD
#   3. For each result, grabs the name, address, hours, price,
#      whether it's open RIGHT NOW, and a photo
#   4. Saves everything into a clean listings.json file
#      that your website reads from
#
# Run this script every morning to keep your app up to date.
# ============================================================

import requests   # For making web requests (calling the API)
import json       # For reading/writing JSON files
import os         # For reading your API key from the environment

# ============================================================
# CONFIGURATION — change these to fit your needs
# ============================================================

# Your Google Places API key.
# IMPORTANT: Never paste your key directly into code.
# Instead, set it as an environment variable on your computer:
#   Mac/Linux: export GOOGLE_PLACES_KEY="your_key_here"
#   Windows:   set GOOGLE_PLACES_KEY=your_key_here
# Then this line reads it safely without exposing it.
API_KEY = os.environ.get("GOOGLE_PLACES_KEY")

# The center point of your search — downtown Bethesda
# You can find lat/lng for any address on Google Maps
LATITUDE  = 38.9848
LONGITUDE = -77.0947

# How far out to search, in meters. 8000m = ~5 miles
SEARCH_RADIUS = 8000

# The output file your website will read from
OUTPUT_FILE = "listings.json"

# ============================================================
# WHAT TO SEARCH FOR
# Each entry has:
#   "type"     — Google's category keyword for the search
#   "category" — what label you want to show in your app
#   "priceMax" — filter out anything more expensive than this
#                (Google uses 0=free, 1=$, 2=$$, 3=$$$, 4=$$$$)
# ============================================================

SEARCH_TARGETS = [
    { "type": "park",               "category": "Outdoors"  },
    { "type": "library",            "category": "Education" },
    { "type": "bowling_alley",      "category": "Activities"},
    { "type": "movie_theater",      "category": "Entertainment"},
    { "type": "amusement_park",     "category": "Activities"},
    { "type": "gym",                "category": "Fitness"   },
    { "type": "art_gallery",        "category": "Arts"      },
    { "type": "museum",             "category": "Arts"      },
    { "type": "skating_rink",       "category": "Activities"},
    { "type": "stadium",            "category": "Sports"    },
]

# ============================================================
# STEP 1 — SEARCH FOR PLACES
# This function asks Google for a list of places near Bethesda
# matching a specific type (like "park" or "bowling_alley")
# ============================================================

def search_places(place_type):
    """
    Calls the Google Places Nearby Search endpoint.
    Returns a list of basic place results.
    """

    # This is the URL of the Google Places API endpoint
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

    # These are the parameters we send with our request
    params = {
        "location": f"{LATITUDE},{LONGITUDE}",  # Center of search
        "radius":   SEARCH_RADIUS,              # How far to look
        "type":     place_type,                 # What to search for
        "key":      API_KEY,                    # Your API key
    }

    # Make the actual web request to Google
    response = requests.get(url, params=params)

    # Convert the response from raw text into a Python dictionary
    data = response.json()

    # "results" is the list of places Google found
    # If something went wrong, return an empty list
    return data.get("results", [])


# ============================================================
# STEP 2 — GET DETAILS FOR A SINGLE PLACE
# The search results above are basic. This function calls
# a second API endpoint to get the FULL details for one place:
# exact hours, price level, phone number, website, photos, etc.
# ============================================================

def get_place_details(place_id):
    """
    Takes a place_id (Google's unique ID for every business/location)
    and returns the full details for that place.
    """

    url = "https://maps.googleapis.com/maps/api/place/details/json"

    params = {
        "place_id": place_id,
        # "fields" tells Google exactly what info we want back.
        # Only requesting what we need saves API credits.
        "fields": (
            "name,"
            "formatted_address,"
            "formatted_phone_number,"
            "website,"
            "opening_hours,"       # Full weekly schedule
            "current_opening_hours,"  # Is it open RIGHT NOW?
            "price_level,"         # 0=free, 1=$, 2=$$, etc.
            "rating,"              # Star rating (1.0 - 5.0)
            "user_ratings_total,"  # How many reviews
            "photos,"              # Photo references
            "geometry,"            # Lat/lng coordinates
            "types,"               # Google's category tags
            "editorial_summary"    # Short description if available
        ),
        "key": API_KEY,
    }

    response = requests.get(url, params=params)
    data = response.json()

    # The actual details are nested inside a "result" key
    return data.get("result", {})


# ============================================================
# STEP 3 — BUILD A PHOTO URL
# Google Places gives you a "photo_reference" string, not a
# direct image URL. This function converts it into a real URL.
# ============================================================

def get_photo_url(photo_reference, max_width=600):
    """
    Converts a Google photo reference into a direct image URL.
    max_width controls the image size (600px is good for mobile).
    """

    if not photo_reference:
        return None  # No photo available

    return (
        f"https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth={max_width}"
        f"&photo_reference={photo_reference}"
        f"&key={API_KEY}"
    )


# ============================================================
# STEP 4 — FIGURE OUT THE PRICE LABEL
# Google uses numbers (0, 1, 2, 3, 4) for price level.
# This converts those into human-readable labels for your app.
# ============================================================

def get_price_info(price_level):
    """
    Converts Google's numeric price level into:
      - A display label ("Free", "Under $10", etc.)
      - A numeric price for sorting/filtering
      - A tier name for your filter chips
    """

    price_map = {
        None: { "label": "Free",       "tier": "free",     "max": 0   },
        0:    { "label": "Free",       "tier": "free",     "max": 0   },
        1:    { "label": "Under $10",  "tier": "cheap",    "max": 10  },
        2:    { "label": "$10 - $25",  "tier": "paid",     "max": 25  },
        3:    { "label": "$25+",       "tier": "paid",     "max": 999 },
        4:    { "label": "$50+",       "tier": "paid",     "max": 999 },
    }

    # Return the matching price info, or default to "Free" if unknown
    return price_map.get(price_level, price_map[None])


# ============================================================
# STEP 5 — FORMAT A SINGLE LISTING
# Takes the raw Google API response and shapes it into the
# clean format your listings.json file uses.
# ============================================================

def format_listing(details, category, place_id):
    """
    Takes raw Google Places data and returns a clean dictionary
    in the exact format your HangOut website expects.
    """

    # Get the price information
    price_level = details.get("price_level")
    price_info  = get_price_info(price_level)

    # Get the photo URL (use the first photo if multiple exist)
    photos        = details.get("photos", [])
    photo_ref     = photos[0].get("photo_reference") if photos else None
    photo_url     = get_photo_url(photo_ref)

    # Check if the place is open RIGHT NOW
    current_hours = details.get("current_opening_hours", {})
    is_open_now   = current_hours.get("open_now", False)

    # Get the full weekly hours schedule
    opening_hours = details.get("opening_hours", {})
    weekday_text  = opening_hours.get("weekday_text", [])
    # weekday_text looks like: ["Monday: 9:00 AM - 9:00 PM", "Tuesday: ..."]

    # Get the coordinates
    geometry = details.get("geometry", {})
    location = geometry.get("location", {})

    # Get a short description (not always available)
    editorial = details.get("editorial_summary", {})
    description = editorial.get("overview", "")

    # Build and return the final clean listing object
    return {
        # Core identity
        "id":          place_id,
        "name":        details.get("name", "Unknown"),
        "category":    category,

        # Location
        "address":     details.get("formatted_address", ""),
        "lat":         location.get("lat"),
        "lng":         location.get("lng"),

        # Contact
        "phone":       details.get("formatted_phone_number", ""),
        "website":     details.get("website", ""),

        # Hours
        "isOpenNow":   is_open_now,
        "hoursToday":  weekday_text,  # Full week schedule

        # Pricing
        "priceLevel":  price_level,
        "priceLabel":  price_info["label"],
        "priceTier":   price_info["tier"],  # "free", "cheap", or "paid"
        "priceMax":    price_info["max"],

        # Media
        "photo":       photo_url,
        "description": description,

        # Quality signals
        "rating":      details.get("rating"),
        "reviewCount": details.get("user_ratings_total", 0),
        "types":       details.get("types", []),

        # HangOut-specific fields (you control these manually)
        "featured":    False,   # Set to True for paying businesses
        "sponsored":   False,   # Set to True for paying businesses
        "sponsoredCta": None,   # e.g. "Book a room" for escape rooms
    }


# ============================================================
# STEP 6 — THE MAIN FUNCTION
# This pulls everything together. It loops through all your
# search targets, fetches the places, gets their details,
# formats them, and saves the final JSON file.
# ============================================================

def main():
    print("HangOut — Fetching listings from Google Places...")
    print(f"Searching within {SEARCH_RADIUS/1000:.0f}km of Bethesda, MD\n")

    all_listings = []        # Will hold every listing we find
    seen_place_ids = set()   # Prevents duplicate listings

    # Loop through each category we want to search
    for target in SEARCH_TARGETS:
        place_type = target["type"]
        category   = target["category"]

        print(f"Searching for: {place_type}...")

        # Get the list of places from Google
        places = search_places(place_type)
        print(f"  Found {len(places)} results")

        # Loop through each place in the results
        for place in places:
            place_id = place.get("place_id")

            # Skip if we've already processed this place
            # (some places show up in multiple category searches)
            if place_id in seen_place_ids:
                continue
            seen_place_ids.add(place_id)

            # Get the full details for this place
            details = get_place_details(place_id)

            # Skip places with very few reviews (likely low quality)
            review_count = details.get("user_ratings_total", 0)
            if review_count < 10:
                continue

            # Skip places with very low ratings
            rating = details.get("rating", 0)
            if rating and rating < 3.5:
                continue

            # Format the listing into our clean structure
            listing = format_listing(details, category, place_id)
            all_listings.append(listing)

            print(f"  + Added: {listing['name']} ({listing['priceLabel']})")

    # --------------------------------------------------------
    # Sort the listings:
    # Free things first, then cheap, then paid.
    # Within each tier, sort by rating (highest first).
    # --------------------------------------------------------
    tier_order = {"free": 0, "cheap": 1, "paid": 2}

    all_listings.sort(key=lambda x: (
        tier_order.get(x["priceTier"], 3),  # Price tier first
        -(x["rating"] or 0)                 # Then by rating (desc)
    ))

    # --------------------------------------------------------
    # Save to listings.json
    # This is the file your website reads from.
    # --------------------------------------------------------
    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_listings, f, indent=2)
        # indent=2 makes the file human-readable

    print(f"\nDone! Saved {len(all_listings)} listings to {OUTPUT_FILE}")
    print("Your app will now show updated data.")


# ============================================================
# This line means: only run main() if you run THIS file
# directly (not if another script imports it).
# It's a Python best practice.
# ============================================================
if __name__ == "__main__":
    main()
