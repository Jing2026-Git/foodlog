/**
 * Vercel Serverless Function: AI 识别代理
 * 解决浏览器直接调用 AI API 的 CORS 问题
 * 支持 OpenAI 兼容接口 / Anthropic / OpenRouter / 阿里云百炼
 */

export default async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  if (req.method !== 'POST') {
    return res.status(405).json({ error: '只支持 POST 请求' });
  }

  const { provider, api_key, base_url, model, prompt, image, test } = req.body || {};

  if (!provider || !api_key || !model || !base_url) {
    return res.status(400).json({ error: 'AI 配置不完整（需要 provider/api_key/model/base_url）' });
  }

  // 测试模式：只做一次纯文本调用验证连通性，不需要图片
  if (test) {
    try {
      let ok;
      if (provider === 'anthropic') {
        ok = await testAnthropic(normalizeBase(base_url), api_key, model);
      } else {
        ok = await testOpenAICompat(normalizeBase(base_url), api_key, model);
      }
      if (ok) return res.status(200).json({ success: true, text: 'OK' });
      return res.status(502).json({ error: 'AI 服务返回非预期结果' });
    } catch (e) {
      return res.status(502).json({ error: e.message || 'AI 连接测试失败', detail: e.detail || '' });
    }
  }

  if (!image) {
    return res.status(400).json({ error: '缺少图片数据' });
  }

  const base = normalizeBase(base_url);

  try {
    let result;
    if (provider === 'anthropic') {
      result = await callAnthropic(base, api_key, model, prompt, image);
    } else {
      result = await callOpenAICompat(base, api_key, model, prompt, image);
    }
    return res.status(200).json({ success: true, text: result });
  } catch (e) {
    return res.status(502).json({
      error: e.message || 'AI 服务调用失败',
      detail: (typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail || '')).slice(0, 500),
    });
  }
}

/** 规范化 base_url，确保以 /v1 结尾（不带尾部斜杠） */
function normalizeBase(baseUrl) {
  let b = baseUrl.replace(/\/+$/, ''); // 去掉尾部斜杠
  if (b.endsWith('/v1')) return b;
  return b + '/v1';
}

async function callAnthropic(base, apiKey, model, prompt, imageB64) {
  const url = base + '/messages';
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: 1024,
      messages: [{
        role: 'user',
        content: [
          {
            type: 'image',
            source: { type: 'base64', media_type: 'image/jpeg', data: imageB64 },
          },
          { type: 'text', text: prompt },
        ],
      }],
    }),
  });

  if (!resp.ok) {
    const body = await resp.text();
    const e = new Error('AI 服务返回错误: ' + resp.status);
    e.detail = body;
    throw e;
  }

  const data = await resp.json();
  const blocks = data.content || [];
  return blocks.filter(b => b.type === 'text').map(b => b.text || '').join('');
}

async function callOpenAICompat(base, apiKey, model, prompt, imageB64) {
  const url = base + '/chat/completions';
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages: [{
        role: 'user',
        content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + imageB64 } },
        ],
      }],
      max_tokens: 1024,
    }),
  });

  if (!resp.ok) {
    const body = await resp.text();
    const e = new Error('AI 服务返回错误: ' + resp.status);
    e.detail = body;
    throw e;
  }

  const data = await resp.json();
  return data.choices[0].message.content;
}

async function testAnthropic(base, apiKey, model) {
  const resp = await fetch(base + '/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: 16,
      messages: [{ role: 'user', content: [{ type: 'text', text: '请回复OK' }] }],
    }),
  });
  if (resp.status === 401 || resp.status === 403) {
    const e = new Error('API密钥无效或权限不足');
    throw e;
  }
  if (!resp.ok) {
    const body = await resp.text();
    const e = new Error('AI 服务返回错误: ' + resp.status);
    e.detail = body;
    throw e;
  }
  return true;
}

async function testOpenAICompat(base, apiKey, model) {
  const resp = await fetch(base + '/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: 16,
      messages: [{ role: 'user', content: '请回复OK' }],
    }),
  });
  if (resp.status === 401 || resp.status === 403) {
    const e = new Error('API密钥无效或权限不足');
    throw e;
  }
  if (!resp.ok) {
    const body = await resp.text();
    const e = new Error('AI 服务返回错误: ' + resp.status);
    e.detail = body;
    throw e;
  }
  return true;
}
