"""Only model construction path: Portkey, PORTKEY_API_KEY, fixed gpt-6-luna."""
import json
import os
import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from .settings import MODEL_NAME, PORTKEY_URL


async def enforce_gateway(request: httpx.Request):
    if request.url.scheme != 'https' or request.url.host != 'api.portkey.ai':
        raise RuntimeError('Model traffic must go through Portkey')
    if request.url.path != '/v1/chat/completions':
        raise RuntimeError('Only the configured chat-completions endpoint is allowed')
    body = json.loads(request.content)
    if body.get('model') != MODEL_NAME:
        raise RuntimeError('Only gpt-6-luna is allowed')


def create_model() -> OpenAIChatModel:
    key = os.environ.get('PORTKEY_API_KEY', '').strip()
    if not key:
        raise RuntimeError('PORTKEY_API_KEY is required; no alternate credentials or provider fallback')
    headers = {'x-portkey-api-key':key, 'x-portkey-provider':'openai'}
    # A virtual key selects the classroom's stored provider credentials, not a different model.
    if os.environ.get('PORTKEY_VIRTUAL_KEY'):
        headers['x-portkey-virtual-key'] = os.environ['PORTKEY_VIRTUAL_KEY']
    http = httpx.AsyncClient(timeout=30, follow_redirects=False, event_hooks={'request':[enforce_gateway]})
    client = AsyncOpenAI(api_key=key, base_url=PORTKEY_URL, default_headers=headers,
                         max_retries=0, http_client=http)
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def safe_configuration() -> str:
    """Presence/configuration only, evaluated inside the actual requesting process."""
    return (f'PORTKEY_API_KEY_present={bool(os.environ.get("PORTKEY_API_KEY", "").strip())}; '
            f'virtual_key_present={bool(os.environ.get("PORTKEY_VIRTUAL_KEY"))}; '
            f'base_url={PORTKEY_URL}; model={MODEL_NAME}; provider_header=openai; '
            'reasoning_effort=none; transport=chat/completions')


def safe_http_failure(exc: Exception) -> str:
    """Never persist raw provider messages, response bodies, headers or credentials."""
    from pydantic_ai.exceptions import ModelHTTPError
    if isinstance(exc, ModelHTTPError):
        categories = {400:'invalid_request',401:'authentication',403:'permission',404:'not_found',
                      408:'timeout',429:'rate_limit'}
        category = categories.get(exc.status_code, 'provider_server_error' if exc.status_code >= 500 else 'http_error')
        return f'ModelHTTPError; HTTP {exc.status_code}; category={category}; model={MODEL_NAME}'
    return f'{type(exc).__name__}; inspect safe audit events'


def safe_validation_diagnostics(exc: Exception) -> str:
    """Retain exception categories/validation locations, never input values or reasoning."""
    import re
    from pydantic import ValidationError
    parts=[];seen=set();current=exc
    allowed={'query_shop','delegate_task','final_result'}
    while current is not None and id(current) not in seen:
        seen.add(id(current));parts.append(type(current).__name__)
        match=re.fullmatch(r"Tool '([a-z_]+)' exceeded max retries count of ([0-9]+)",str(current))
        if match and match[1] in allowed:parts.append(f'tool={match[1]}; retries={match[2]}')
        if isinstance(current,ValidationError):
            for e in current.errors(include_input=False,include_context=False,include_url=False)[:8]:
                loc='.'.join(str(x) for x in e['loc'])
                if re.fullmatch(r'[A-Za-z0-9_.]{0,100}',loc):parts.append(f'{loc}:{e["type"]}')
        current=current.__cause__ or current.__context__
    return '; '.join(parts)[:1000]
