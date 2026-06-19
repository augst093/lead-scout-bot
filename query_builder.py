import re

# Niche-specific search query templates
# `{city}` is a placeholder that will be filled dynamically.
# If no city is provided, the `{city}` parameter will be removed from the queries cleanly.

FITNESS_TEMPLATES = [
    'site:instagram.com "personal trainer" "DM to book" "{city}"',
    'site:instagram.com "personal trainer" "book a call" "{city}"',
    'site:instagram.com "online fitness coach" "apply now" "{city}"',
    'site:instagram.com "body recomposition coach" "link in bio" "{city}"',
    'site:instagram.com "fitness coach" "book a call" "{city}"',
    'site:instagram.com "transformation coach" "apply now" "{city}"',
    'site:instagram.com "fitness coach" "clients" "{city}"',
    'site:instagram.com "personal trainer" "link in bio" "{city}"'
]

NAILS_TEMPLATES = [
    'site:instagram.com "nail artist" "book now" "{city}"',
    'site:instagram.com "nail tech" "DM to book" "{city}"',
    'site:instagram.com "nail artist" "appointments" "{city}"',
    'site:instagram.com "BIAB nails" "booking" "{city}"',
    'site:instagram.com "luxury nails" "appointments" "{city}"',
    'site:instagram.com "beauty studio" "book now" "{city}"',
    'site:instagram.com "nail tech" "clients" "{city}"',
    'site:instagram.com "nail artist" "link in bio" "{city}"'
]

CREATORS_TEMPLATES = [
    'site:instagram.com "UGC creator" "portfolio" "email" "{city}"',
    'site:instagram.com "lifestyle creator" "brand partnerships" "{city}"',
    'site:instagram.com "content creator" "media kit" "{city}"',
    'site:instagram.com "micro influencer" "collabs" "{city}"',
    'site:instagram.com "creator" "brand" "{city}"',
    'site:instagram.com "brand partnerships" "media kit" "{city}"',
    'site:instagram.com "UGC creator" "collab" "{city}"',
    'site:instagram.com "content creator" "link in bio" "{city}"'
]

def build_queries(niche: str, city: str = None) -> list:
    """
    Builds a list of search queries based on the niche and city.
    If city is None or empty, the "{city}" placeholder is stripped out.
    Returns a list of dicts: [{"query": query_str, "niche": niche_name}]
    """
    niche = niche.lower().strip()
    
    # We want to associate each template with its corresponding niche.
    templated_niches = [] # list of tuples: (template_str, niche_name)
    
    if niche == "fitness":
        templated_niches = [(t, "fitness") for t in FITNESS_TEMPLATES]
    elif niche in ("nails", "beauty"):
        templated_niches = [(t, "nails") for t in NAILS_TEMPLATES]
    elif niche in ("creators", "creator"):
        templated_niches = [(t, "creators") for t in CREATORS_TEMPLATES]
    elif niche == "all":
        # Interleave templates: Fitness, Nails, Creators
        max_len = max(len(FITNESS_TEMPLATES), len(NAILS_TEMPLATES), len(CREATORS_TEMPLATES))
        for i in range(max_len):
            if i < len(FITNESS_TEMPLATES):
                templated_niches.append((FITNESS_TEMPLATES[i], "fitness"))
            if i < len(NAILS_TEMPLATES):
                templated_niches.append((NAILS_TEMPLATES[i], "nails"))
            if i < len(CREATORS_TEMPLATES):
                templated_niches.append((CREATORS_TEMPLATES[i], "creators"))
    else:
        # Fallback to combined / generic
        templated_niches = (
            [(t, "fitness") for t in FITNESS_TEMPLATES] +
            [(t, "nails") for t in NAILS_TEMPLATES] +
            [(t, "creators") for t in CREATORS_TEMPLATES]
        )

    queries = []
    for template, q_niche in templated_niches:
        if city:
            # Clean up city name
            cleaned_city = city.strip()
            query = template.format(city=cleaned_city)
        else:
            # If no city is specified, remove "{city}" and clean up double spacing
            query = template.replace('"{city}"', '').replace('{city}', '')
            
        # Clean double spaces and strip trailing/leading spaces
        query = re.sub(r'\s+', ' ', query).strip()
        queries.append({"query": query, "niche": q_niche})
        
    return queries
