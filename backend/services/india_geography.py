"""Complete India geography registry: all 28 states, 8 Union Territories, Metro & Tier-2 city mappings."""

from typing import Dict, Optional, Tuple

INDIAN_STATES: list[str] = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]

INDIAN_UNION_TERRITORIES: list[str] = [
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
]

ALL_INDIA_STATES_AND_UTS: list[str] = INDIAN_STATES + INDIAN_UNION_TERRITORIES

STATE_ABBREVIATIONS: Dict[str, str] = {
    "ap": "Andhra Pradesh",
    "ar": "Arunachal Pradesh",
    "as": "Assam",
    "br": "Bihar",
    "cg": "Chhattisgarh",
    "ct": "Chhattisgarh",
    "ga": "Goa",
    "gj": "Gujarat",
    "hr": "Haryana",
    "hp": "Himachal Pradesh",
    "jh": "Jharkhand",
    "ka": "Karnataka",
    "kl": "Kerala",
    "mp": "Madhya Pradesh",
    "mh": "Maharashtra",
    "mn": "Manipur",
    "ml": "Meghalaya",
    "mz": "Mizoram",
    "nl": "Nagaland",
    "od": "Odisha",
    "or": "Odisha",
    "pb": "Punjab",
    "rj": "Rajasthan",
    "sk": "Sikkim",
    "tn": "Tamil Nadu",
    "tg": "Telangana",
    "ts": "Telangana",
    "tr": "Tripura",
    "up": "Uttar Pradesh",
    "uk": "Uttarakhand",
    "ut": "Uttarakhand",
    "wb": "West Bengal",
    "an": "Andaman and Nicobar Islands",
    "ch": "Chandigarh",
    "dn": "Dadra and Nagar Haveli and Daman and Diu",
    "dd": "Dadra and Nagar Haveli and Daman and Diu",
    "dl": "Delhi",
    "jk": "Jammu and Kashmir",
    "la": "Ladakh",
    "ld": "Lakshadweep",
    "py": "Puducherry",
}

METRO_CITIES = {
    "Hyderabad",
    "Bangalore",
    "Chennai",
    "Mumbai",
    "Delhi",
    "New Delhi",
    "Pune",
    "Kolkata",
    "Ahmedabad",
    "Noida",
    "Gurugram",
}

# Canonical city -> (Normalized City Name, State/UT, City Tier)
INDIA_CITY_MAP: Dict[str, Tuple[str, str, str]] = {
    # Andhra Pradesh
    "visakhapatnam": ("Visakhapatnam", "Andhra Pradesh", "Tier-2"),
    "vizag": ("Visakhapatnam", "Andhra Pradesh", "Tier-2"),
    "vijayawada": ("Vijayawada", "Andhra Pradesh", "Tier-2"),
    "guntur": ("Guntur", "Andhra Pradesh", "Tier-2"),
    "tirupati": ("Tirupati", "Andhra Pradesh", "Tier-2"),
    "amaravati": ("Amaravati", "Andhra Pradesh", "Tier-2"),
    "kakinada": ("Kakinada", "Andhra Pradesh", "Tier-2"),
    "nellore": ("Nellore", "Andhra Pradesh", "Tier-2"),
    # Arunachal Pradesh
    "itanagar": ("Itanagar", "Arunachal Pradesh", "Other"),
    # Assam
    "guwahati": ("Guwahati", "Assam", "Tier-2"),
    "silchar": ("Silchar", "Assam", "Other"),
    "dibrugarh": ("Dibrugarh", "Assam", "Other"),
    # Bihar
    "patna": ("Patna", "Bihar", "Tier-2"),
    "gaya": ("Gaya", "Bihar", "Other"),
    "muzaffarpur": ("Muzaffarpur", "Bihar", "Other"),
    # Chhattisgarh
    "raipur": ("Raipur", "Chhattisgarh", "Tier-2"),
    "bhilai": ("Bhilai", "Chhattisgarh", "Tier-2"),
    "bilaspur": ("Bilaspur", "Chhattisgarh", "Other"),
    # Goa
    "panaji": ("Panaji", "Goa", "Tier-2"),
    "margao": ("Margao", "Goa", "Other"),
    "goa": ("Panaji", "Goa", "Tier-2"),
    # Gujarat
    "ahmedabad": ("Ahmedabad", "Gujarat", "Metro"),
    "surat": ("Surat", "Gujarat", "Tier-2"),
    "vadodara": ("Vadodara", "Gujarat", "Tier-2"),
    "rajkot": ("Rajkot", "Gujarat", "Tier-2"),
    "gandhinagar": ("Gandhinagar", "Gujarat", "Tier-2"),
    # Haryana
    "gurugram": ("Gurugram", "Haryana", "Metro"),
    "gurgaon": ("Gurugram", "Haryana", "Metro"),
    "faridabad": ("Faridabad", "Haryana", "Tier-2"),
    "panchkula": ("Panchkula", "Haryana", "Tier-2"),
    "ambala": ("Ambala", "Haryana", "Other"),
    # Himachal Pradesh
    "shimla": ("Shimla", "Himachal Pradesh", "Other"),
    "dharamshala": ("Dharamshala", "Himachal Pradesh", "Other"),
    "solan": ("Solan", "Himachal Pradesh", "Other"),
    # Jharkhand
    "ranchi": ("Ranchi", "Jharkhand", "Tier-2"),
    "jamshedpur": ("Jamshedpur", "Jharkhand", "Tier-2"),
    "dhanbad": ("Dhanbad", "Jharkhand", "Tier-2"),
    # Karnataka
    "bangalore": ("Bangalore", "Karnataka", "Metro"),
    "bengaluru": ("Bangalore", "Karnataka", "Metro"),
    "mysuru": ("Mysuru", "Karnataka", "Tier-2"),
    "mysore": ("Mysuru", "Karnataka", "Tier-2"),
    "mangaluru": ("Mangaluru", "Karnataka", "Tier-2"),
    "mangalore": ("Mangaluru", "Karnataka", "Tier-2"),
    "hubballi": ("Hubballi", "Karnataka", "Tier-2"),
    "hubli": ("Hubballi", "Karnataka", "Tier-2"),
    "belagavi": ("Belagavi", "Karnataka", "Tier-2"),
    # Kerala
    "kochi": ("Kochi", "Kerala", "Tier-2"),
    "cochin": ("Kochi", "Kerala", "Tier-2"),
    "thiruvananthapuram": ("Thiruvananthapuram", "Kerala", "Tier-2"),
    "trivandrum": ("Thiruvananthapuram", "Kerala", "Tier-2"),
    "kozhikode": ("Kozhikode", "Kerala", "Tier-2"),
    "thrissur": ("Thrissur", "Kerala", "Tier-2"),
    # Madhya Pradesh
    "indore": ("Indore", "Madhya Pradesh", "Tier-2"),
    "bhopal": ("Bhopal", "Madhya Pradesh", "Tier-2"),
    "jabalpur": ("Jabalpur", "Madhya Pradesh", "Tier-2"),
    "gwalior": ("Gwalior", "Madhya Pradesh", "Tier-2"),
    # Maharashtra
    "mumbai": ("Mumbai", "Maharashtra", "Metro"),
    "navi mumbai": ("Navi Mumbai", "Maharashtra", "Metro"),
    "thane": ("Thane", "Maharashtra", "Metro"),
    "pune": ("Pune", "Maharashtra", "Metro"),
    "chakan": ("Pune", "Maharashtra", "Metro"),
    "kurli": ("Pune", "Maharashtra", "Metro"),
    "nagpur": ("Nagpur", "Maharashtra", "Tier-2"),
    "nashik": ("Nashik", "Maharashtra", "Tier-2"),
    "aurangabad": ("Aurangabad", "Maharashtra", "Tier-2"),
    # Manipur
    "imphal": ("Imphal", "Manipur", "Other"),
    # Meghalaya
    "shillong": ("Shillong", "Meghalaya", "Other"),
    # Mizoram
    "aizawl": ("Aizawl", "Mizoram", "Other"),
    # Nagaland
    "kohima": ("Kohima", "Nagaland", "Other"),
    "dimapur": ("Dimapur", "Nagaland", "Other"),
    # Odisha
    "bhubaneswar": ("Bhubaneswar", "Odisha", "Tier-2"),
    "cuttack": ("Cuttack", "Odisha", "Tier-2"),
    "rourkela": ("Rourkela", "Odisha", "Tier-2"),
    # Punjab
    "ludhiana": ("Ludhiana", "Punjab", "Tier-2"),
    "amritsar": ("Amritsar", "Punjab", "Tier-2"),
    "mohali": ("Mohali", "Punjab", "Tier-2"),
    "jalandhar": ("Jalandhar", "Punjab", "Tier-2"),
    # Rajasthan
    "jaipur": ("Jaipur", "Rajasthan", "Tier-2"),
    "udaipur": ("Udaipur", "Rajasthan", "Tier-2"),
    "jodhpur": ("Jodhpur", "Rajasthan", "Tier-2"),
    "kota": ("Kota", "Rajasthan", "Tier-2"),
    # Sikkim
    "gangtok": ("Gangtok", "Sikkim", "Other"),
    # Tamil Nadu
    "chennai": ("Chennai", "Tamil Nadu", "Metro"),
    "coimbatore": ("Coimbatore", "Tamil Nadu", "Tier-2"),
    "madurai": ("Madurai", "Tamil Nadu", "Tier-2"),
    "tiruchirappalli": ("Tiruchirappalli", "Tamil Nadu", "Tier-2"),
    "trichy": ("Tiruchirappalli", "Tamil Nadu", "Tier-2"),
    "salem": ("Salem", "Tamil Nadu", "Tier-2"),
    # Telangana
    "hyderabad": ("Hyderabad", "Telangana", "Metro"),
    "warangal": ("Warangal", "Telangana", "Tier-2"),
    "nizamabad": ("Nizamabad", "Telangana", "Other"),
    "secunderabad": ("Hyderabad", "Telangana", "Metro"),
    # Tripura
    "agartala": ("Agartala", "Tripura", "Other"),
    # Uttar Pradesh
    "noida": ("Noida", "Uttar Pradesh", "Metro"),
    "greater noida": ("Noida", "Uttar Pradesh", "Metro"),
    "lucknow": ("Lucknow", "Uttar Pradesh", "Tier-2"),
    "kanpur": ("Kanpur", "Uttar Pradesh", "Tier-2"),
    "varanasi": ("Varanasi", "Uttar Pradesh", "Tier-2"),
    "ghaziabad": ("Ghaziabad", "Uttar Pradesh", "Tier-2"),
    "agra": ("Agra", "Uttar Pradesh", "Tier-2"),
    "prayagraj": ("Prayagraj", "Uttar Pradesh", "Tier-2"),
    # Uttarakhand
    "dehradun": ("Dehradun", "Uttarakhand", "Tier-2"),
    "haridwar": ("Haridwar", "Uttarakhand", "Other"),
    "roorkee": ("Roorkee", "Uttarakhand", "Other"),
    # West Bengal
    "kolkata": ("Kolkata", "West Bengal", "Metro"),
    "siliguri": ("Siliguri", "West Bengal", "Tier-2"),
    "durgapur": ("Durgapur", "West Bengal", "Tier-2"),
    # Union Territories
    "port blair": ("Port Blair", "Andaman and Nicobar Islands", "Other"),
    "chandigarh": ("Chandigarh", "Chandigarh", "Tier-2"),
    "silvassa": ("Silvassa", "Dadra and Nagar Haveli and Daman and Diu", "Other"),
    "daman": ("Daman", "Dadra and Nagar Haveli and Daman and Diu", "Other"),
    "delhi": ("Delhi", "Delhi", "Metro"),
    "new delhi": ("New Delhi", "Delhi", "Metro"),
    "ncr": ("Delhi", "Delhi", "Metro"),
    "srinagar": ("Srinagar", "Jammu and Kashmir", "Tier-2"),
    "jammu": ("Jammu", "Jammu and Kashmir", "Tier-2"),
    "leh": ("Leh", "Ladakh", "Other"),
    "kavaratti": ("Kavaratti", "Lakshadweep", "Other"),
    "puducherry": ("Puducherry", "Puducherry", "Tier-2"),
    "pondicherry": ("Puducherry", "Puducherry", "Tier-2"),
}

GLOBAL_CITY_MAP: Dict[str, Tuple[str, str]] = {
    # United States
    "san francisco": ("San Francisco", "United States"),
    "new york": ("New York", "United States"),
    "seattle": ("Seattle", "United States"),
    "austin": ("Austin", "United States"),
    "boston": ("Boston", "United States"),
    "chicago": ("Chicago", "United States"),
    "los angeles": ("Los Angeles", "United States"),
    "washington, d.c.": ("Washington, D.C.", "United States"),
    "washington, dc": ("Washington, D.C.", "United States"),
    "denver": ("Denver", "United States"),
    "atlanta": ("Atlanta", "United States"),
    "dallas": ("Dallas", "United States"),
    "houston": ("Houston", "United States"),
    "miami": ("Miami", "United States"),
    "pittsburgh": ("Pittsburgh", "United States"),
    "san jose": ("San Jose", "United States"),
    "mountain view": ("Mountain View", "United States"),
    "palo alto": ("Palo Alto", "United States"),
    "menlo park": ("Menlo Park", "United States"),
    "redmond": ("Redmond", "United States"),
    "raleigh": ("Raleigh", "United States"),
    "bellevue": ("Bellevue", "United States"),
    "sunnyvale": ("Sunnyvale", "United States"),
    "san diego": ("San Diego", "United States"),
    "cambridge, ma": ("Cambridge", "United States"),
    "philadelphia": ("Philadelphia", "United States"),
    # Canada
    "toronto": ("Toronto", "Canada"),
    "vancouver": ("Vancouver", "Canada"),
    "montreal": ("Montreal", "Canada"),
    "montréal": ("Montreal", "Canada"),
    "ottawa": ("Ottawa", "Canada"),
    "calgary": ("Calgary", "Canada"),
    "waterloo": ("Waterloo", "Canada"),
    "kitchener": ("Kitchener", "Canada"),
    "edmonton": ("Edmonton", "Canada"),
    "mississauga": ("Mississauga", "Canada"),
    "winnipeg": ("Winnipeg", "Canada"),
    "halifax": ("Halifax", "Canada"),
    "quebec": ("Quebec", "Canada"),
    # United Kingdom & Ireland
    "london": ("London", "United Kingdom"),
    "manchester": ("Manchester", "United Kingdom"),
    "edinburgh": ("Edinburgh", "United Kingdom"),
    "bristol": ("Bristol", "United Kingdom"),
    "cambridge, uk": ("Cambridge", "United Kingdom"),
    "dublin": ("Dublin", "Ireland"),
    # Continental Europe
    "paris": ("Paris", "France"),
    "berlin": ("Berlin", "Germany"),
    "munich": ("Munich", "Germany"),
    "frankfurt": ("Frankfurt", "Germany"),
    "hamburg": ("Hamburg", "Germany"),
    "stuttgart": ("Stuttgart", "Germany"),
    "amsterdam": ("Amsterdam", "Netherlands"),
    "rotterdam": ("Rotterdam", "Netherlands"),
    "barcelona": ("Barcelona", "Spain"),
    "madrid": ("Madrid", "Spain"),
    "warsaw": ("Warsaw", "Poland"),
    "krakow": ("Krakow", "Poland"),
    "zurich": ("Zurich", "Switzerland"),
    "stockholm": ("Stockholm", "Sweden"),
    "lisbon": ("Lisbon", "Portugal"),
    "milan": ("Milan", "Italy"),
    # APAC & LATAM
    "singapore": ("Singapore", "Singapore"),
    "tokyo": ("Tokyo", "Japan"),
    "seoul": ("Seoul", "South Korea"),
    "sydney": ("Sydney", "Australia"),
    "melbourne": ("Melbourne", "Australia"),
    "brisbane": ("Brisbane", "Australia"),
    "tel aviv": ("Tel Aviv", "Israel"),
    "sao paulo": ("Sao Paulo", "Brazil"),
    "são paulo": ("Sao Paulo", "Brazil"),
    "mexico city": ("Mexico City", "Mexico"),
}


def resolve_geography(
    location: str,
    region_hint: Optional[str] = None,
    city_hint: Optional[str] = None,
    country_hint: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return (city, state_or_ut, country, city_tier) from location and ATS hints."""
    loc = (location or "").strip()
    loc_l = loc.lower()
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    city_tier: Optional[str] = None

    # 1. Check India cities
    probe_text = f"{city_hint or ''} {loc}".lower()
    for key, (norm_city, norm_state, tier) in INDIA_CITY_MAP.items():
        if key in probe_text:
            city = norm_city
            state = norm_state
            country = "India"
            city_tier = tier
            break

    # 2. Check full Indian state / UT names
    if state is None:
        for st_name in ALL_INDIA_STATES_AND_UTS:
            if st_name.lower() in loc_l:
                state = st_name
                country = "India"
                break

    # 3. Check Indian state abbreviation hint (e.g. 'MH', 'KA') when country is India
    if state is None and region_hint:
        reg = region_hint.strip().lower()
        c_hint_l = (country_hint or "").strip().lower()
        if c_hint_l in ("in", "india") or "india" in loc_l:
            if reg in STATE_ABBREVIATIONS:
                state = STATE_ABBREVIATIONS[reg]
                country = "India"

    if country is None:
        c_hint_l = (country_hint or "").strip().lower()
        if c_hint_l in ("in", "india") or "india" in loc_l:
            country = "India"

    if country == "India" and city is None and city_hint:
        city = city_hint.strip().title()
        if city in METRO_CITIES:
            city_tier = "Metro"
        else:
            city_tier = "Tier-2"

    # 4. Global fallback
    c_hint_norm = (country_hint or "").strip().lower()
    if country is None and c_hint_norm in ("ca", "can", "canada"):
        country = "Canada"
    elif country is None and c_hint_norm in ("us", "usa", "united states"):
        country = "United States"
    elif country is None and c_hint_norm in ("gb", "uk", "united kingdom"):
        country = "United Kingdom"

    if country is None:
        for g_key, (g_city, g_country) in GLOBAL_CITY_MAP.items():
            if g_key in loc_l:
                city = g_city
                country = g_country
                break

    if country is None:
        if any(k in loc_l for k in ("canada", ", on", ", bc", ", qc", ", ab", "ontario", "british columbia", "alberta", "quebec")):
            country = "Canada"
        elif any(k in loc_l for k in ("united states", "usa", "u.s.", "us only", "remote - us", "remote, us", ", ca", ", ny", ", wa", ", tx", ", ma", ", il", ", co", ", ga", ", fl")):
            country = "United States"
        elif "united kingdom" in loc_l or ", uk" in loc_l or "remote - uk" in loc_l:
            country = "United Kingdom"
        elif "ireland" in loc_l:
            country = "Ireland"
        elif "germany" in loc_l or "deutschland" in loc_l:
            country = "Germany"
        elif "france" in loc_l:
            country = "France"
        elif "netherlands" in loc_l or "holland" in loc_l:
            country = "Netherlands"
        elif "australia" in loc_l:
            country = "Australia"
        elif "japan" in loc_l:
            country = "Japan"
        elif "south korea" in loc_l or "korea" in loc_l:
            country = "South Korea"
        elif "singapore" in loc_l:
            country = "Singapore"
        elif "spain" in loc_l:
            country = "Spain"
        elif "poland" in loc_l:
            country = "Poland"
        elif "brazil" in loc_l:
            country = "Brazil"
        elif "mexico" in loc_l:
            country = "Mexico"
        elif "switzerland" in loc_l:
            country = "Switzerland"
        elif "israel" in loc_l:
            country = "Israel"
        elif any(k in loc_l for k in ("remote", "worldwide", "anywhere", "global", "distributed", "home based", "home-based", "apac", "emea", "latam", "americas", "europe")):
            country = "Remote / Global"

    return city, state, country, city_tier
