import io
import os
from flask import Flask, request, jsonify
from google import genai
from PIL import Image
import requests

app = Flask(__name__)

# =======================
# ENV VARIABLES (RENDER)
# =======================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BLYNK_TOKEN = os.getenv("BLYNK_TOKEN")

# Safety check
if not GEMINI_API_KEY:
    raise Exception("Missing GEMINI_API_KEY in Render environment variables")

client = genai.Client(api_key=GEMINI_API_KEY)


# =======================
# ROOT ROUTE (FIX FOR 404)
# =======================
@app.route('/', methods=['GET', 'HEAD'])
def home():
    return jsonify({
        "status": "OK",
        "message": "Smart Farming AI Server Running"
    })


# =======================
# AI ANALYSIS ROUTE
# =======================
@app.route('/analyze', methods=['POST'])
def analyze():

    try:
        image_bytes = request.data

        # validate image
        if not image_bytes or len(image_bytes) < 100:
            return jsonify({"error": "Invalid image"}), 400

        # decode image
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            return jsonify({
                "error": "Image decode failed",
                "details": str(e)
            }), 400

        # AI prompt
        prompt = (
            "Analyze this plant leaf. Identify nutrient deficiency "
            "(N, P, K, Mg, Fe) or disease. "
            "Give 1-sentence diagnosis and 1-sentence solution."
        )

        # Gemini AI call
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, prompt]
        )

        result = response.text.strip()[:200]

        print("AI RESULT:", result)

        # =======================
        # BLYNK UPDATE (OPTIONAL)
        # =======================
        if BLYNK_TOKEN:
            try:
                url = f"https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}&v1={result}"
                requests.get(url, timeout=5)
            except Exception as e:
                print("Blynk error:", e)

        return jsonify({
            "status": "success",
            "result": result
        })

    except Exception as e:
        print("SERVER ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# =======================
# LOCAL RUN (IGNORED BY RENDER)
# =======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)