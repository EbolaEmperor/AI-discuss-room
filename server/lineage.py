# server/lineage.py
from typing import List
from sqlalchemy.orm import Session
from server.models import Post


def lineage_of(db: Session, post: Post) -> List[Post]:
    """Return the full lineage of a proof — root proof + all revisions, in chronological (creation) order.

    Given any post in the lineage, walks parent_id back until type='proof' to find the root,
    then walks superseded_by forward to enumerate every version.
    """
    # Walk back to the root proof
    cur = post
    while cur.type == "revision" and cur.parent_id is not None:
        parent = db.query(Post).filter(Post.id == cur.parent_id).one()
        cur = parent
    root = cur

    # Walk forward via superseded_by
    chain = [root]
    while chain[-1].superseded_by is not None:
        nxt = db.query(Post).filter(Post.id == chain[-1].superseded_by).one()
        chain.append(nxt)
    return chain


def comments_for_lineage(db: Session, anchor: Post) -> List[Post]:
    """Return all comment + agree posts whose parent_id is in the lineage of `anchor`
    OR whose parent_id is a comment in this set (recursive closure). Sorted by created_at."""
    line_ids = {p.id for p in lineage_of(db, anchor)}
    out: List[Post] = []
    frontier = set(line_ids)
    seen_comment_ids: set[int] = set()
    while frontier:
        children = (db.query(Post)
                    .filter(Post.parent_id.in_(frontier),
                            Post.type.in_(("comment", "agree")))
                    .all())
        new_ids = set()
        for c in children:
            if c.id in seen_comment_ids:
                continue
            seen_comment_ids.add(c.id)
            out.append(c)
            if c.type == "comment":
                new_ids.add(c.id)
        frontier = new_ids
    out.sort(key=lambda p: p.created_at)
    return out
