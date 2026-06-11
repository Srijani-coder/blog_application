# -*- coding: utf-8 -*-

import os
import re
from bs4 import BeautifulSoup

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from models import Post


HF_TOKEN = os.getenv("hf_token")
HF_MODEL = "HuggingFaceH4/zephyr-7b-beta:featherless-ai"


def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    return text[:4500]


def get_blog_context(limit: int = 6) -> str:
    posts = (
        Post.query
        .order_by(Post.publish_date.desc())
        .limit(limit)
        .all()
    )

    if not posts:
        return "No blog articles available."

    blocks = []

    for post in posts:
        content = clean_html(post.content)

        blocks.append(
            f"Title: {post.title}\n"
            f"Slug: {post.slug}\n"
            f"Published: {post.publish_date}\n"
            f"Content: {content}"
        )

    return "\n\n---\n\n".join(blocks)


def generate_dual_summaries(title: str, content: str) -> dict:
    content = re.sub(r"\s+", " ", content).strip()

    sentences = re.split(r"(?<=[.!?])\s+", content)

    meaningful = []

    for sentence in sentences:
        s = sentence.strip()

        if len(s) < 60:
            continue

        if s.lower() == title.lower():
            continue

        meaningful.append(s)

    if len(meaningful) < 4:
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 35][:8]

    analytical_keywords = [
        "data",
        "financial",
        "government",
        "report",
        "statistics",
        "risk",
        "investigation",
        "money",
        "fraud",
        "case",
        "evidence",
        "number",
        "recorded",
        "company",
        "loss",
        "public"
    ]

    analytical = []

    for sentence in meaningful:
        score = sum(
            1 for keyword in analytical_keywords
            if keyword in sentence.lower()
        )

        if score > 0:
            analytical.append((score, sentence))

    analytical.sort(reverse=True, key=lambda x: x[0])

    analytical_sentences = [x[1] for x in analytical[:3]]

    if not analytical_sentences:
        analytical_sentences = meaningful[:3]

    summary_a = " ".join(analytical_sentences)

    storytelling_sentences = meaningful[:3]

    summary_b = (
        "This article turns a financial controversy into a data story. "
        "It explains how recorded numbers, missing evidence, and public reporting "
        "shape what we understand about risk, loss, and accountability. "
        + " ".join(storytelling_sentences[:2])
    )

    summary_a = summary_a[:520].strip()
    summary_b = summary_b[:520].strip()

    if summary_a and not summary_a.endswith((".", "!", "?")):
        summary_a += "..."

    if summary_b and not summary_b.endswith((".", "!", "?")):
        summary_b += "..."

    return {
        "A": summary_a,
        "B": summary_b
    }


def build_chat_model() -> ChatOpenAI:
    if not HF_TOKEN:
        raise RuntimeError("Missing Hugging Face token.")

    return ChatOpenAI(
        api_key=HF_TOKEN,
        base_url="https://router.huggingface.co/v1",
        model=HF_MODEL,
        temperature=0.4,
        max_tokens=220,
    )


def blog_chatbot_reply(user_message: str) -> str:
    msg = (user_message or "").strip()

    if not msg:
        return (
            " Hi! Ask for the latest article, "
            "a quick blog explanation, or help finding posts."
        )

    msg_lower = msg.lower()

    if any(x in msg_lower for x in [
        "find posts",
        "finding posts",
        "posts page",
        "all posts"
    ]):
        return (
            ' Explore all blog articles here:<br><br>'
            '<a href="/posts">Open Posts Page</a>'
        )

    if "latest blog article" in msg_lower or "latest post" in msg_lower:
        post = (
            Post.query
            .order_by(Post.publish_date.desc())
            .first()
        )

        if not post:
            return "No blog articles are available yet."

        content = clean_html(post.content)
        summaries = generate_dual_summaries(post.title, content)

        return (
            f"<b>{post.title}</b><br><br>"
            f"{summaries['B']}<br><br>"
            f'<a href="/post/{post.slug}">Read full article</a>'
        )

    title_match = re.search(
        r"blog titled\s+['\"]?(.*?)['\"]?$",
        msg,
        flags=re.IGNORECASE
    )

    if title_match:
        title = title_match.group(1).strip()

        post = (
            Post.query
            .filter(Post.title.ilike(f"%{title}%"))
            .order_by(Post.publish_date.desc())
            .first()
        )

        if not post:
            return (
                f"I could not find a blog titled "
                f"<b>{title}</b>.<br><br>"
                f'<a href="/posts">Browse Posts</a>'
            )

        content = clean_html(post.content)
        summaries = generate_dual_summaries(post.title, content)

        return f"""
        <b>{post.title}</b><br><br>

        <div class="summaryBox">
            <b>Summary A: Analytical</b><br>
            {summaries["A"]}
        </div>

        <br>

        <div class="summaryBox">
            <b>Summary B: Storytelling</b><br>
            {summaries["B"]}
        </div>

        <br>

        <div class="feedbackBtns">
            <button onclick="sendSummaryFeedback('{post.id}', 'A')">
                👍 Prefer A
            </button>

            <button onclick="sendSummaryFeedback('{post.id}', 'B')">
                👍 Prefer B
            </button>
        </div>

        <br>

        <a href="/post/{post.slug}">Read full article</a>
        """

    try:
        blog_context = get_blog_context(limit=4)
        chat = build_chat_model()

        system_prompt = f"""
You are JSTCon Assistant.

Rules:
1. Keep answers under 3 lines.
2. Be friendly and concise.
3. Recommend only available blog posts.
4. Never invent articles.
5. Redirect users to /posts if needed.

Available posts:
{blog_context}
"""

        response = chat.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=msg)
        ])

        return response.content.strip()

    except Exception:
        return (
            " Try asking:<br><br>"
            "• latest blog article<br>"
            "• Help me understand the blog titled ...<br>"
            '• <a href="/posts">Browse Posts</a>'
        )
