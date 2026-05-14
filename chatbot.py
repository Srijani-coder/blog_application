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
    if not user_message or not user_message.strip():
        return (
            "Hi! I'm your blog assistant. Ask me about the latest articles, "
            "topics, insights, or which post you should read first."
        )

    blog_context = get_blog_context()
    chat = build_chat_model()

    system_prompt = f"""
You are JSTCon AI Assistant, a warm PR chatbot for Srijani Chakrabarti's data blog.

Your job:
1. Greet visitors nicely.
2. Explain blog articles in simple, attractive English when user will ask you.
3. Recommend relevant blog posts only from the context.
4. Show the latest post according to date when asked
5. Never invent articles, authors, links, or claims.
6. If information is unavailable, politely say so.
6. Keep answers friendly, concise, and visitor-focused and in just 2-3 lines.

Available blog articles:
{blog_context}
"""

    try:
        response = chat.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message.strip())
        ])

        return response.content.strip()

    except Exception as e:
        print(f"Chatbot error: {e}")
        return (
            "Sorry, the assistant is temporarily unavailable. "
            "Please explore the latest articles from the homepage."
        )