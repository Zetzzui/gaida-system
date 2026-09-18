"""
text_prep.py
------------
Shared text normalization for the GAIDA ML layer.

Handles Taglish/English noise so the TF-IDF classifiers see
clean, stable tokens:

  * lowercasing + collapsing repeated characters (soooo -> so)
  * normalizing unicode quotes
  * expanding common English/Taglish contractions
    (im -> i am, di -> hindi) so the same concept maps to one token
  * removing punctuation leftovers
  * dropping curated English + Filipino function words

We deliberately keep negation words ("not", "hindi", "na", "pa") and
crisis-relevant pronouns ("myself", "yourself") in the vocabulary --
removing them would hurt suicidal/self-harm detection.
"""

import re

_CONTRACTION_MAP = {
    # English contractions (post-lowercasing, apostrophe retained)
    "i'm": "i am",
    "i've": "i have",
    "i'll": "i will",
    "i'd": "i would",
    "you're": "you are",
    "you've": "you have",
    "you'll": "you will",
    "you'd": "you would",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "we're": "we are",
    "we've": "we have",
    "we'll": "we will",
    "we'd": "we would",
    "they're": "they are",
    "they've": "they have",
    "they'll": "they will",
    "there's": "there is",
    "there're": "there are",
    "that's": "that is",
    "what's": "what is",
    "who's": "who is",
    "where's": "where is",
    "how's": "how is",
    "let's": "let us",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "can't": "cannot",
    "couldn't": "could not",
    "wouldn't": "would not",
    "shouldn't": "should not",
    "won't": "will not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "might've": "might have",
    "must've": "must have",
    # Taglish / informal Filipino
    "di": "hindi",
    "diko": "hindi ko",
    "hnd": "hindi",
    "hndi": "hindi",
    "ayoko": "ayaw ko",
    "ayawko": "ayaw ko",
    "gsto": "gusto",
    "gto": "gusto",
    "kc": "kasi",
    "kzb": "kasi",
}

# Curated English function words. Omitted on purpose: negation words
# (not/no/nor), and self-referential pronouns (myself/yourself/oneself).
_ENG_STOPWORDS = {
    "a", "about", "again", "all", "also", "am", "an", "and", "any",
    "are", "as", "at", "be", "because", "been", "before", "being",
    "but", "by", "can", "could", "did", "do", "does", "doing", "down",
    "each", "for", "from", "had", "has", "have", "having", "he", "her",
    "here", "hers", "him", "his", "how", "i", "if", "in", "into", "is",
    "it", "its", "me", "more", "most", "my", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "with", "would", "you", "your",
    "yours",
}

# Conservative Filipino function words. Kept out on purpose: "na"/"pa"
# carry "anymore"/"still" connotations that matter for crisis cues.
_FIL_STOPWORDS = {
    "ang", "at", "ay", "ba", "bakit", "daw", "din", "eh", "ha", "ho",
    "ikaw", "ka", "kay", "kina", "ko", "lamang", "lang", "mo",
    "naman", "ng", "nina", "opo", "para", "po", "raw", "rin",
    "sa", "si", "sina", "mga", "yung",
}

STOPWORDS = _ENG_STOPWORDS | _FIL_STOPWORDS


def normalize_raw(text: str) -> str:
    """Basic noise cleanup — keeps apostrophes so contractions expand."""
    text = (text or "").lower()
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    text = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", text)
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def expand_contractions(text: str) -> str:
    text = " " + text + " "
    for short, long in _CONTRACTION_MAP.items():
        text = re.sub(r"\b" + re.escape(short) + r"\b", long, text)
    return text.strip()


def preprocess(text: str) -> str:
    """Full normalization pipeline used as the TF-IDF preprocessor."""
    text = normalize_raw(text)
    text = expand_contractions(text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text