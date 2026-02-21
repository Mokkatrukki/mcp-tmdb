from langgraph.graph import StateGraph, END

from .state import SearchState
from .nodes import (
    classify_intent,
    resolve_reference,
    resolve_person,
    fetch_keywords,
    fetch_recommendations,
    execute_discover,
    execute_both_types,
    execute_lookup,
    execute_person,
    execute_trending,
    merge_similar,
    handle_low_confidence,
    _load_keyword_data,
)


def route_after_classify(state: SearchState) -> str:
    if state.get("confidence") == "low":
        return "handle_low_confidence"
    intent = state.get("intent", "discover")
    if intent == "trending":
        return "execute_trending"
    if intent == "person":
        return "execute_person"
    if intent == "lookup":
        return "execute_lookup"
    if intent == "similar_to":
        return "resolve_reference"
    # discover (+ both_types)
    person_name = state.get("person_name")
    if person_name:
        return "resolve_person"
    if state.get("both_types"):
        return "execute_both_types"
    return "execute_discover"


def route_after_resolve_person(state: SearchState) -> str:
    if state.get("both_types"):
        return "execute_both_types"
    return "execute_discover"


def route_after_fetch_recommendations(state: SearchState) -> str:
    return "execute_discover"


def route_after_execute_discover(state: SearchState) -> str:
    intent = state.get("intent", "discover")
    if intent == "similar_to":
        return "merge_similar"
    return END


def route_after_resolve_reference(state: SearchState) -> str:
    # Jos resolve_reference asetti final_result, virhe
    if state.get("final_result"):
        return END
    return "fetch_keywords"


def build_graph():
    _load_keyword_data()

    builder = StateGraph(SearchState)

    builder.add_node("classify_intent", classify_intent)
    builder.add_node("resolve_reference", resolve_reference)
    builder.add_node("resolve_person", resolve_person)
    builder.add_node("fetch_keywords", fetch_keywords)
    builder.add_node("fetch_recommendations", fetch_recommendations)
    builder.add_node("execute_discover", execute_discover)
    builder.add_node("execute_both_types", execute_both_types)
    builder.add_node("execute_lookup", execute_lookup)
    builder.add_node("execute_person", execute_person)
    builder.add_node("execute_trending", execute_trending)
    builder.add_node("merge_similar", merge_similar)
    builder.add_node("handle_low_confidence", handle_low_confidence)

    builder.set_entry_point("classify_intent")

    builder.add_conditional_edges("classify_intent", route_after_classify)
    builder.add_conditional_edges("resolve_reference", route_after_resolve_reference)
    builder.add_edge("fetch_keywords", "fetch_recommendations")
    builder.add_conditional_edges("fetch_recommendations", route_after_fetch_recommendations)
    builder.add_conditional_edges("resolve_person", route_after_resolve_person)
    builder.add_conditional_edges("execute_discover", route_after_execute_discover)

    builder.add_edge("execute_both_types", END)
    builder.add_edge("execute_lookup", END)
    builder.add_edge("execute_person", END)
    builder.add_edge("execute_trending", END)
    builder.add_edge("merge_similar", END)
    builder.add_edge("handle_low_confidence", END)

    return builder.compile()
