"""Turn a research question into the informative terms keyword search APIs need.

"Does sleep deprivation affect working memory in students?" -> sleep, deprivation, working,
memory, students. Question words, function words and generic research verbs ("affect",
"impact", "study") are dropped because they match almost every paper.
"""

import re

ENGLISH_STOPWORDS = frozenset(
    """
    a an the of and or but if then than to in on at by for from with without into onto over
    under about between among during before after above below up down out off again further
    is are was were be been being am do does did doing have has had having can could will
    would shall should may might must not no nor only own same so too very just also
    i me my we our you your he him his she her it its they them their this that these those
    what which who whom whose why how when where whether there here all any both each few more
    most other some such
    affect affects affected effect effects impact impacts influence influences role roles
    relationship relation association associated study studies research paper evidence
    use used using based new approach method methods analysis really
    """.split()
)

HEBREW_STOPWORDS = frozenset(
    """
    של על את עם אל אם או גם לא כן זה זו זאת אלה הוא היא הם הן אני אנחנו אתה את מה מי איך
    למה מדוע האם כמה כל בין יש אין היה היו יהיה אשר כי אבל רק עוד כבר מאוד יותר פחות לפי
    בתוך תוך אחרי לפני השפעה השפעת משפיע משפיעה משפיעים קשר מחקר מחקרים
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-]*|[א-ת][א-ת\"'׳״]*", re.I)
MIN_LENGTH = 2


def keywords(text: str, limit: int = 8) -> list[str]:
    terms: list[str] = []
    for raw in _TOKEN.findall(text.lower()):
        token = raw.strip("-\"'")
        if len(token) < MIN_LENGTH or token in ENGLISH_STOPWORDS or token in HEBREW_STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:limit]


def keyword_query(text: str, limit: int = 8) -> str:
    """Keywords as a plain search string; falls back to the text when nothing is left."""
    return " ".join(keywords(text, limit)) or text.strip()
