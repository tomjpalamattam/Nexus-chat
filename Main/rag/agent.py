"""
RAG agent using langchain.agents.create_agent (current non-deprecated API).

The key async-safety rule:
  All Django ORM calls must happen via database_sync_to_async BEFORE
  entering the async agent streaming loop.

  build_agent() is therefore async — it fetches the embedding config
  from the DB using sync_to_async, builds the vectorstore, then
  constructs the agent. No ORM calls happen inside the streaming loop.
"""
from typing import AsyncIterator

from channels.db import database_sync_to_async
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.tools import tool
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from .ingest import get_vectorstore, _get_embedding_cfg

_checkpointer = MemorySaver()


# ── LLM factory ───────────────────────────────────────────────────────────────

def _make_llm(api_config):
    provider = getattr(api_config, 'provider', 'openai')

    if provider == 'deepseek':
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model=api_config.model_name or 'deepseek-chat',
            api_key=api_config.api_key,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
        )

    from langchain_openai import ChatOpenAI
    kwargs = {
        'model':     api_config.model_name,
        'api_key':   api_config.api_key,
        'streaming': True,
    }
    if getattr(api_config, 'base_url', None):
        kwargs['base_url'] = api_config.base_url
    return ChatOpenAI(**kwargs)


# ── tool factory ──────────────────────────────────────────────────────────────

def _make_retrieve_tool(vectorstore):
    """
    Build a retrieve_context tool from an already-constructed vectorstore.
    No DB access happens here — vectorstore was built before entering async.
    """
    @tool(response_format='content_and_artifact')
    def retrieve_context(query: str):
        """
        Retrieve relevant passages from the provider's document knowledge base.
        Call this whenever the user asks something that may be answered
        from the uploaded documents.
        """
        retrieved_docs = vectorstore.similarity_search(query, k=4)
        serialized = '\n\n'.join(
            f'Source: {doc.metadata.get("original_name", "unknown")} '
            f'(page {doc.metadata.get("page", "?")})\n'
            f'Content: {doc.page_content}'
            for doc in retrieved_docs
        )
        return serialized, retrieved_docs

    return retrieve_context


# ── async agent builder ───────────────────────────────────────────────────────

async def build_agent(api_config, provider):
    """
    Async agent builder — fetches embedding config from DB via
    database_sync_to_async, builds the vectorstore synchronously,
    then constructs the create_agent graph.

    Must be async so the consumer can await it safely inside the
    WebSocket receive handler.
    """
    # DB fetch — must use sync_to_async inside async context
    cfg = await database_sync_to_async(_get_embedding_cfg)(provider)

    # vectorstore construction is CPU/IO but not Django ORM — safe to call directly
    vectorstore = get_vectorstore(cfg, provider)

    llm   = _make_llm(api_config)
    tools = [_make_retrieve_tool(vectorstore)]

    system_prompt = (
        f'You are a helpful assistant for {provider.username}. '
        'You have access to a retrieval tool that searches documents '
        'uploaded by the provider. '
        'Use it whenever the user asks something that could be answered '
        'from those documents. '
        'If the documents contain no relevant information, answer from '
        'your general knowledge and say so clearly.'
    )

    return create_agent(
        llm,
        tools,
        system_prompt=system_prompt,
        checkpointer=_checkpointer,
    )


# ── streaming entry point ─────────────────────────────────────────────────────

async def stream_agent_response(
    api_config,
    provider,
    history: list,
    user_message: str,
    system_prompt: str,
    thread_id: str,
) -> AsyncIterator[str]:
    """
    Async generator — yields plain text chunks from the agent's final response.

    Uses astream(stream_mode="messages", version="v2") per current docs:
      chunk["type"] == "messages"  →  chunk["data"] == (token, metadata)
      token.content_blocks         →  list of typed dicts
      {"type": "text", "text": "..."}   ← yield these
      {"type": "tool_call_chunk", ...}  ← skip these
    """
    agent = await build_agent(api_config, provider)

    messages: list = []
    if system_prompt and system_prompt.strip() != 'You are a helpful assistant.':
        messages.append(SystemMessage(content=system_prompt))

    for msg in history:
        if msg['role'] == 'user':
            messages.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            messages.append(AIMessage(content=msg['content']))

    messages.append(HumanMessage(content=user_message))

    config = {'configurable': {'thread_id': thread_id}}

    async for chunk in agent.astream(
        {'messages': messages},
        config,
        stream_mode='messages',
        version='v2',
    ):
        if chunk.get('type') != 'messages':
            continue

        token, _metadata = chunk['data']

        for block in getattr(token, 'content_blocks', []):
            if isinstance(block, dict) and block.get('type') == 'text':
                text = block.get('text', '')
                if text:
                    yield text