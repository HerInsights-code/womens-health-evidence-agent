PER_QUERY = 5       # records per tag per source; raise once the pipeline works
MIN_CITATIONS = 0   # keep at 0 so recent papers aren't filtered out

# Keys must match the tags in data/tag_dictionary.json
TAG_QUERIES = {
    "pcos": 'PCOS OR "polycystic ovary syndrome"',
    "endometriosis": "endometriosis",
    "periods": '"menstrual health" OR "heavy menstrual bleeding" OR "menstrual pain"',
    "menopause": '"menopause" AND "hormone therapy"',
    "ppd": '"postpartum depression" OR "perinatal depression"',
    "queer mental health": '"LGBTQ mental health" OR "queer mental health"',
    "gender-affirming care": '"gender-affirming care" OR "gender affirming care"',
    "lgbtq healthcare access": '"LGBTQ healthcare access" OR "sexual minority health disparities"',
}