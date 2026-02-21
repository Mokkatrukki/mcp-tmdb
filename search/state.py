from typing import TypedDict


class SearchState(TypedDict, total=False):
    query: str
    # Gemini-luokittelu
    intent: str        # discover|lookup|person|similar_to|trending|low_confidence
    confidence: str    # high|low
    media_type: str    # movie|tv
    time_window: str   # day|week
    genres: list[str] | None
    keywords: list[str] | None
    year: int | None
    year_from: int | None
    year_to: int | None
    min_rating: float | None
    language: str | None
    watch_provider: str | None
    person_name: str | None
    title: str | None
    name: str | None
    reference_title: str | None
    sort_by: str
    min_votes: int
    airing_now: bool
    both_types: bool
    # Resolvoidut ajonaikaiset arvot
    reference_id: int | None
    cast_id: int | None
    reference_keywords: list[str]
    # Tulokset
    recommendations_result: str
    discover_result: str
    final_result: str
