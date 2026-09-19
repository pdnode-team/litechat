import json
import re
from typing import Annotated, List, Optional
from litestar import Controller, get, post, put, delete, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException, NotFoundException
from litestar.params import PathParameter, QueryParameter
from sqlalchemy import select, or_, func
from app.db.session import async_session_factory
from app.models.faq_item import FaqItem
from app.schemas.faq import (
    FaqItemCreate,
    FaqItemUpdate,
    FaqItemResponse,
    FaqQueryRequest,
    FaqQueryResponse,
)
from app.schemas.pagination import DEFAULT_PAGE_SIZE, LimitParam, OffsetParam, Page
from app.controllers.auth import get_current_user_from_request
from app.services import events as event_bus

# Words that carry no signal and would otherwise match almost any article.
STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "your", "with", "this", "that",
    "how", "what", "why", "when", "where", "who", "can", "could", "would", "should",
    "does", "did", "has", "have", "was", "were", "will", "its", "it's", "from", "about",
    "into", "out", "get", "got", "any", "all", "some", "please", "help", "issue",
    "problem", "there", "here", "they", "them", "his", "her", "our", "been", "being",
}


def _tokenize(text: str) -> List[str]:
    """Split into lowercase word tokens, dropping noise words and 1-2 char fragments."""
    return [
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]

def faq_to_response(item: FaqItem) -> FaqItemResponse:
    replies = []
    if item.quick_replies_json:
        try:
            replies = json.loads(item.quick_replies_json)
        except Exception:
            replies = []
    return FaqItemResponse(
        id=item.id,
        category=item.category,
        question=item.question,
        answer=item.answer,
        keywords=item.keywords or "",
        quick_replies=replies,
        sort_order=item.sort_order,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )

class FaqController(Controller):
    path = "/api/faq"

    @get("/")
    async def list_faq(
        self,
        request: Request,
        category: Annotated[Optional[str], QueryParameter()] = None,
        search: Annotated[Optional[str], QueryParameter()] = None,
        active_only: Annotated[Optional[bool], QueryParameter()] = None,
        limit: LimitParam = DEFAULT_PAGE_SIZE,
        offset: OffsetParam = 0,
    ) -> Page[FaqItemResponse]:
        async with async_session_factory() as session:
            filters = []
            if active_only:
                filters.append(FaqItem.is_active.is_(True))
            if category:
                filters.append(FaqItem.category == category)
            if search:
                term = f"%{search.strip().lower()}%"
                filters.append(
                    or_(
                        FaqItem.question.ilike(term),
                        FaqItem.answer.ilike(term),
                        FaqItem.keywords.ilike(term),
                    )
                )

            total = (
                await session.execute(select(func.count()).select_from(FaqItem).where(*filters))
            ).scalar_one()

            stmt = (
                select(FaqItem)
                .where(*filters)
                .order_by(FaqItem.sort_order.asc(), FaqItem.id.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            items = [faq_to_response(i) for i in result.scalars().all()]
            return Page[FaqItemResponse](items=items, total=total, limit=limit, offset=offset)

    @post("/query")
    async def query_faq_engine(self, data: FaqQueryRequest) -> FaqQueryResponse:
        query_str = data.query.strip().lower()
        query_words = _tokenize(query_str)

        # The whole-query bonus is only meaningful when the query carries at
        # least one significant token, and it must match on word boundaries.
        # Without both guards a one-letter or stopword-only query ("a", "can")
        # scores +10 against every article, because it is a raw substring of
        # words like "cancel".
        phrase_pattern = (
            re.compile(rf"\b{re.escape(query_str)}\b") if query_words else None
        )

        async with async_session_factory() as session:
            stmt = select(FaqItem).where(FaqItem.is_active.is_(True))
            if data.category:
                stmt = stmt.where(FaqItem.category == data.category)
            result = await session.execute(stmt)
            all_faqs = result.scalars().all()

            # Rank by token overlap. Matching is word-based and requires a minimum
            # score, so an unrelated question returns nothing instead of the
            # nearest article (substring scoring used to match "can" inside
            # "cancel" and even a single letter inside any answer body).
            matches = []
            for item in all_faqs:
                q_tokens = set(_tokenize(item.question))
                kw_tokens = set(_tokenize(item.keywords or ""))
                ans_tokens = set(_tokenize(item.answer))

                score = 0
                if phrase_pattern and phrase_pattern.search(item.question.lower()):
                    score += 10
                if phrase_pattern and phrase_pattern.search((item.keywords or "").lower()):
                    score += 8

                for word in query_words:
                    # Tolerate simple plurals without a full stemmer: a query of
                    # "refunds" should reach an article keyworded "refund", and
                    # vice versa. Each field scores at most once per word.
                    variants = {word}
                    if len(word) > 3:
                        variants.add(word[:-1] if word.endswith("s") else f"{word}s")

                    if variants & q_tokens:
                        score += 4
                    if variants & kw_tokens:
                        score += 4
                    if variants & ans_tokens:
                        score += 1

                if score > 0:
                    matches.append((score, item))

            matches.sort(key=lambda pair: (-pair[0], pair[1].sort_order, pair[1].id))

            # An empty query (browsing) shows the recommended articles; a real
            # query must clear MIN_RELEVANCE_SCORE to be considered a match.
            MIN_RELEVANCE_SCORE = 3
            if query_str:
                matches = [pair for pair in matches if pair[0] >= MIN_RELEVANCE_SCORE]

            top_items = [faq_to_response(item) for score, item in matches[:5]]

            # Collect quick options from top matches
            quick_options = []
            for item in top_items:
                if item.quick_replies:
                    for opt in item.quick_replies:
                        if opt not in quick_options:
                            quick_options.append(opt)

            suggested_reply = (
                top_items[0].answer if top_items else "I couldn't find an exact solution for your query. You can connect with our human engineering support below."
            )

            return FaqQueryResponse(
                matches=top_items,
                suggested_reply=suggested_reply,
                quick_options=quick_options[:6],
                can_escalate_ticket=True,
            )

    @post("/")
    async def create_faq(self, request: Request, data: FaqItemCreate) -> FaqItemResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can create FAQ entries.")

        async with async_session_factory() as session:
            replies_json = json.dumps(data.quick_replies) if data.quick_replies else "[]"
            new_faq = FaqItem(
                category=data.category.strip().lower(),
                question=data.question.strip(),
                answer=data.answer.strip(),
                keywords=data.keywords.strip() if data.keywords else "",
                quick_replies_json=replies_json,
                sort_order=data.sort_order,
                is_active=data.is_active,
            )
            session.add(new_faq)
            await session.commit()
            await session.refresh(new_faq)
            await event_bus.publish_catalog_change("faq", "created", actor_name=current_user.full_name)
            return faq_to_response(new_faq)

    @put("/{faq_id:int}")
    async def update_faq(self, request: Request, faq_id: Annotated[int, PathParameter()], data: FaqItemUpdate) -> FaqItemResponse:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can update FAQ entries.")

        async with async_session_factory() as session:
            item = await session.get(FaqItem, faq_id)
            if not item:
                raise NotFoundException("FAQ item not found.")

            if data.category is not None:
                item.category = data.category.strip().lower()
            if data.question is not None:
                item.question = data.question.strip()
            if data.answer is not None:
                item.answer = data.answer.strip()
            if data.keywords is not None:
                item.keywords = data.keywords.strip()
            if data.quick_replies is not None:
                item.quick_replies_json = json.dumps(data.quick_replies)
            if data.sort_order is not None:
                item.sort_order = data.sort_order
            if data.is_active is not None:
                item.is_active = data.is_active

            await session.commit()
            await session.refresh(item)
            await event_bus.publish_catalog_change("faq", "updated", actor_name=current_user.full_name)
            return faq_to_response(item)

    @delete("/{faq_id:int}")
    async def delete_faq(self, request: Request, faq_id: Annotated[int, PathParameter()]) -> None:
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Only administrators can delete FAQ entries.")

        async with async_session_factory() as session:
            item = await session.get(FaqItem, faq_id)
            if not item:
                raise NotFoundException("FAQ item not found.")
            await session.delete(item)
            await session.commit()

        await event_bus.publish_catalog_change("faq", "deleted", actor_name=current_user.full_name)
