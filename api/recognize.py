"""
Vercel Serverless Function: AI 识别代理
解决浏览器直接调用 AI API 的 CORS 问题
"""
import json
import urllib.request
import urllib.error


def handler(req):
    """处理 AI 识别请求"""
    try:
        body = json.loads(req.get('body', '{}'))
    except Exception:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': '请求体格式错误'})
        }

    provider = body.get('provider', '')
    api_key = body.get('api_key', '')
    base_url = body.get('base_url', '')
    model = body.get('model', '')
    prompt = body.get('prompt', '')
    image_b64 = body.get('image', '')

    if not provider or not api_key or not model or not base_url:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'AI 配置不完整'})
        }

    if not image_b64:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': '缺少图片数据'})
        }

    # 规范化 base_url
    if base_url.endswith('/v1'):
        base = base_url
    elif base_url.endswith('/'):
        base = base_url + 'v1'
    else:
        base = base_url + '/v1'

    try:
        if provider == 'anthropic':
            result = _call_anthropic(base, api_key, model, prompt, image_b64)
        else:
            result = _call_openai_compat(base, api_key, model, prompt, image_b64)

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'success': True, 'text': result})
        }
    except urllib.error.HTTPError as e:
        err_body = ''
        try:
            err_body = e.read().decode('utf-8')[:500]
        except Exception:
            pass
        return {
            'statusCode': 502,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'AI 服务返回错误: ' + str(e.code),
                'detail': err_body
            })
        }
    except urllib.error.URLError as e:
        return {
            'statusCode': 502,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'AI 服务连接失败: ' + str(e.reason)})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': '服务器内部错误: ' + str(e)})
        }


def _call_anthropic(base, api_key, model, prompt, image_b64):
    """调用 Anthropic Claude API"""
    url = base + '/messages'
    payload = json.dumps({
        'model': model,
        'max_tokens': 1024,
        'messages': [{
            'role': 'user',
            'content': [
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': 'image/jpeg',
                        'data': image_b64
                    }
                },
                {'type': 'text', 'text': prompt}
            ]
        }]
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, method='POST')
    req.add_header('x-api-key', api_key)
    req.add_header('anthropic-version', '2023-06-01')
    req.add_header('Content-Type', 'application/json')

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        blocks = data.get('content', [])
        return ''.join(b.get('text', '') for b in blocks if b.get('type') == 'text')


def _call_openai_compat(base, api_key, model, prompt, image_b64):
    """调用 OpenAI 兼容接口（OpenAI / 阿里云百炼 / OpenRouter 等）"""
    url = base + '/chat/completions'
    payload = json.dumps({
        'model': model,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {
                    'type': 'image_url',
                    'image_url': {'url': 'data:image/jpeg;base64,' + image_b64}
                }
            ]
        }],
        'max_tokens': 1024
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, method='POST')
    req.add_header('Authorization', 'Bearer ' + api_key)
    req.add_header('Content-Type', 'application/json')

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        return data['choices'][0]['message']['content']
