# ChatGPT Plugin Bridge

SmartPost AI uses the user's ChatGPT plugin. It does not call the OpenAI API and does not require an API key.

## Read pending requests

`GET http://127.0.0.1:8765/api/ai/requests`

Each request contains:

- `job`: product name, product link, Shop ID, Product ID and status
- `prompt`: the finished Thai generation prompt
- `image_urls`: localhost URLs for the original product images
- `provider`: `chatgpt_plugin`
- `requires_api_key`: `false`

If a manually pasted Shopee short link does not expose product images, select the Product Job in the Windows app and click `เพิ่มรูปสินค้า`. The files are copied into the Job's `original` folder and immediately appear in the plugin request as localhost image URLs.

## Return a result

`POST http://127.0.0.1:8765/api/ai/result`

```json
{
  "job_id": "JOB-20260825-XXXXXX",
  "caption_short": "แคปชั่นขายสั้น",
  "hashtags": ["#ของดีบอกต่อ"],
  "image_prompt": "พรอมต์รูปสินค้า",
  "video_prompt": "พรอมต์วิดีโอ Google Flow",
  "spoken_script": "สคริปต์พูดขาย",
  "warnings": [],
  "generated_images": []
}
```

`generated_images` may contain base64 PNG data. The bridge stores generated images, captions and prompts in the matching Product Job folder.

AI result payloads support up to 30 MB so portrait PNG images can be returned in base64. Product-import payloads remain limited to 2 MB.

## Security

- Bound to `127.0.0.1` only
- Chrome-extension CORS only
- No cookies or Shopee passwords are transferred
- No OpenAI or ChatGPT API key is requested or stored
- Job paths are validated before local file access
