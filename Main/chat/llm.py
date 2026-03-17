"""
Plain (non-RAG) LLM streaming.
Supports:
  - OpenAI / OpenAI-compatible  (api_config.provider == 'openai' | 'openai_compatible')
  - DeepSeek                    (api_config.provider == 'deepseek')
"""
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


def get_llm(api_config):
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


def build_messages(system_prompt, history, user_message):
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    for msg in history:
        if msg['role'] == 'user':
            messages.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            messages.append(AIMessage(content=msg['content']))
    messages.append(HumanMessage(content=user_message))
    return messages


async def stream_response(api_config, history, user_message, system_prompt):
    llm = get_llm(api_config)
    messages = build_messages(system_prompt, history, user_message)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content