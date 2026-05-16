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

    return text[:2200]


def get_blog_context(limit: int = 6) -> str:
    posts = (
        Post.query
        .order_by(Post.publish_date.desc())
        .limit(limit)
        .all()
    )

    if not posts:
        return "No blog articles are available yet."

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


def build_chat_model() -> ChatOpenAI:
    if not HF_TOKEN:
        raise RuntimeError(
            "Missing Hugging Face token. Set hf_token in .env or Render environment variables."
        )

    return ChatOpenAI(
        api_key=HF_TOKEN,
        base_url="https://router.huggingface.co/v1",
        model=HF_MODEL,
        temperature=0.5,
        max_tokens=450,
    )


def blog_chatbot_reply(user_message: str) -> str:
    msg = (user_message or "").strip()

    if not msg:
        return "✨ Hi! Ask me for the latest article, a blog summary, or help finding posts."

    # 1. Redirect to posts page
    if any(x in msg.lower() for x in ["find posts", "finding posts", "all posts", "posts page"]):
        return 'You can explore every article here: <a href="/posts">Open the Posts page</a>'

    # 2. Latest blog article
    if "latest blog article" in msg.lower() or "latest post" in msg.lower():
        post = Post.query.order_by(Post.publish_date.desc()).first()

        if not post:
            return "No blog articles are available yet."

        summary = clean_html(post.content)[:350]

        return (
            f"<b>{post.title}</b><br>"
            f"Published: {post.publish_date}<br>"
            f"{summary}...<br>"
            f'<a href="/article/{post.slug}">Read the article</a>'
        )

    # 3. Explain specific titled blog
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
                f"I could not find a blog titled <b>{title}</b>. "
                'Please check the title or visit <a href="/posts">Posts</a>.'
            )

        content = clean_html(post.content)

        chat = build_chat_model()

        system_prompt = """
You are JSTCon Assistant.
Summarise the given blog in simple, attractive English.
Use only the blog text provided.
Keep it concise: 3 short lines maximum.
Do not invent facts.
"""

        response = chat.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Title: {post.title}\n\nBlog text:\n{content}")
        ])

        return (
            f"<b>{post.title}</b><br>"
            f"{response.content.strip()}<br>"
            f'<a href="/article/{post.slug}">Read full article</a>'
        )

    # 4. Friendly fallback
    return (
        "I can help with three things: "
        "<b>latest blog article</b>, "
        "<b>Help me understand the blog titled ...</b>, "
        'or <a href="/posts">finding posts</a>.'
    )