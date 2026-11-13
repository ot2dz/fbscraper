# -*- coding: utf-8 -*-
"""Sorting and filtering helpers for scraped posts."""

SORT_FIELDS = {
    "comments": "comment_rendering_instance.comments.total_count",
    "likes": "reaction_count.count",
    "shares": "share_count.count",
    "date": "time",
    "views": "video_view_count",
}

SORT_LABELS = {
    "comments": "التعليقات",
    "likes": "الإعجابات",
    "shares": "المشاركات",
    "date": "التاريخ",
    "views": "المشاهدات",
}


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def sort_and_filter(posts, sort="comments", order="desc", min_comments=0, query=""):
    """Return posts sorted by a metric and optionally filtered."""
    field = SORT_FIELDS.get(sort, SORT_FIELDS["comments"])
    result = list(posts or [])

    if min_comments:
        result = [
            post
            for post in result
            if _number(post.get(SORT_FIELDS["comments"])) >= min_comments
        ]

    query = (query or "").strip().lower()
    if query:
        result = [
            post
            for post in result
            if query in str(post.get("context") or "").lower()
            or query in str(post.get("post_id") or "").lower()
        ]

    result.sort(key=lambda post: _number(post.get(field)), reverse=(order != "asc"))
    return result
