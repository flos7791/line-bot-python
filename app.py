import os
import sys

# 確保在 Windows 控制台輸出中文不發生編碼錯誤
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from google import genai
from google.genai import types

# 載入 .env 環境變數
load_dotenv()

app = Flask(__name__)

CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    print("錯誤: 請在 .env 檔案中填寫 LINE_CHANNEL_SECRET 與 LINE_CHANNEL_ACCESS_TOKEN！")
    sys.exit(1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

def get_ai_response(prompt: str) -> str:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key or gemini_key.strip() == "" or gemini_key == "your_gemini_api_key_here":
        return "⚠️ 尚未在 .env 中填寫 GEMINI_API_KEY！\n請前往 https://aistudio.google.com/app/apikey 免費申請金鑰。"

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    try:
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="你是一個友善、聰明且樂於助人的 LINE 繁體中文 AI 智慧助理。請用繁體中文（台灣習慣用語）親切且簡明扼要地回覆使用者的問題。"
            )
        )
        return response.text.strip() if response.text else "抱歉，我目前無法理解這則訊息。"
    except Exception as e:
        app.logger.warning(f"嘗試使用 {model_name} 失敗: {e}，切換備用模型 gemini-2.0-flash...")
        try:
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            return response.text.strip() if response.text else "抱歉，我目前無法理解這則訊息。"
        except Exception as e2:
            app.logger.error(f"Gemini API 呼叫均失敗: {e2}")
            return f"AI 處理時發生問題：{e2}"

@app.route("/", methods=['GET'])
def home():
    return "LINE Bot 伺服器運作中！"

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭值以進行簽章驗證
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        app.logger.warning("缺少 X-Line-Signature 標頭")
        abort(400)

    body = request.get_data(as_text=True)

    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("無效的簽章，請檢查 Channel Secret 是否正確。")
        abort(400)

    return 'OK'

# 處理收到的文字訊息 (使用 Gemini AI 進行智慧回覆)
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text
    print(f"收到使用者訊息: {user_text}")

    # 取得 AI 智慧回覆
    ai_reply = get_ai_response(user_text)
    print(f"AI 回覆內容: {ai_reply}")

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=ai_reply)]
            )
        )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"本地伺服器啟動於 http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)

