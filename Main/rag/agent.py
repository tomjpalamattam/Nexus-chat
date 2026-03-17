from typing import AsyncIterator

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.agents import create_agent          # current, non-deprecated API
from langgraph.checkpoint.memory import MemorySaver

from .ingest import get_vectorstore

# Shared checkpointer — keeps per-thread history across WebSocket reconnects
_checkpointer = MemorySaver()


def _make_retrieve_tool(provider):
    """
    Build a retrieve_context tool bound to a specific provider's Qdrant collection.
    Constructed dynamically so the vectorstore is provider-scoped.
    """
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


def _make_llm(api_config):
    kwargs = {
        'model':     api_config.model_name,
        'api_key':   api_config.api_key,
        'streaming': True,
    }
    if api_config.base_url:
        kwargs['base_url'] = api_config.base_url
    return ChatOpenAI(**kwargs)


def build_agent(api_config, provider):
    """
    Build a create_agent graph for a given api_config + provider.
    MemorySaver checkpointer persists conversation history across
    WebSocket reconnects as long as thread_id is stable.
    """
    llm   = _make_llm(api_config)
    tools = [_make_retrieve_tool(provider)]

    system_prompt = (
        f'You are a helpful assistant for {provider.username}. '
        'You have access to a retrieval tool that searches through documents '
        'uploaded by the provider. '
        'Use the tool whenever the user asks something that could be answered '
        'from those documents. '
        'If the documents contain no relevant information, answer from your '
        'general knowledge and say so clearly.'
    )

    return create_agent(
        llm,
        tools,
        system_prompt=system_prompt,
        checkpointer=_checkpointer,
    )


async def stream_agent_response(
    api_config,
    provider,
    history: list,
    user_message: str,
    system_prompt: str,
    thread_id: str,
) -> AsyncIterator[str]:
    """
    Async generator — yields plain text chunks from the agent's final AI response.

    Uses astream(stream_mode="messages", version="v2") per current docs:
      - Each chunk is a StreamPart dict: {"type": ..., "data": ..., "ns": ...}
      - chunk["type"] == "messages"  →  chunk["data"] == (token, metadata)
      - We filter token.content_blocks for {"type": "text"} entries,
        skipping tool_call_chunk blocks so only final prose is sent to the WS.
    """
    agent = build_agent(api_config, provider)

    # Rebuild message list (history already excludes the current message)
    messages: list = []

    # Include conversation-level system prompt if non-default
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
        # v2 format: every chunk is a StreamPart dict
        if chunk.get('type') != 'messages':
            continue

        token, metadata = chunk['data']

        # content_blocks is the normalized list per current LangChain docs
        # Each block is {"type": "text", "text": "..."} or a tool_call_chunk dict
        for block in getattr(token, 'content_blocks', []):
            if isinstance(block, dict) and block.get('type') == 'text':
                text = block.get('text', '')
                if text:
                    yield text