"""
RAG agent using langchain.agents.create_agent (current non-deprecated API).

LLM is auto-selected based on api_config.provider:
  - 'deepseek'          → ChatDeepSeek
  - 'openai' / others   → ChatOpenAI (also handles openai_compatible via base_url)

Streaming: agent.astream(stream_mode="messages", version="v2")
  Each chunk is a StreamPart dict {"type", "data", "ns"}.
  type=="messages" → data==(token, metadata)
  We yield token.content_blocks entries where type=="text", skipping tool calls.
"""
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.tools import tool
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from .ingest import get_vectorstore

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

    # Default: OpenAI or OpenAI-compatible (Ollama, Together, etc.)
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

def _make_retrieve_tool(provider):
    """Build a retrieve_context tool bound to this provider's Qdrant collection."""
    vectorstore = get_vectorstore(provider)

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


# ── agent builder ─────────────────────────────────────────────────────────────

def build_agent(api_config, provider):
    llm   = _make_llm(api_config)
    tools = [_make_retrieve_tool(provider)]

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
      {"type": "text", "text": "..."}        ← yield these
      {"type": "tool_call_chunk", ...}       ← skip these
    """
    agent = build_agent(api_config, provider)

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