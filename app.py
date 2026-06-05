import io
import os
import uuid
from datetime import datetime

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

client = genai.Client(api_key=GEMINI_API_KEY)

# =======================
# SAVE FOLDER (Render safe)
# =======================
SAVE_DIR = "saved_images"
os.makedirs(SAVE_DIR, exist_ok=True)


# =======================
# HOME ROUTE
# =======================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "OK",
        "message": "Smart Farming AI Server Running"
    })


# =======================
# CONFIDENCE ESTIMATION
# (simple heuristic)
# =======================
def estimate_confidence(text: str) -> int:
    text_lower = text.lower()

    score = 70  # base confidence

    keywords = ["deficiency", "chlorosis", "disease", "nutrient"]
    if any(k in text_lower for k in keywords):
        score += 15

    if "uncertain" in text_lower or "difficult" in text_lower:
        score -= 20

    if len(text) > 120:
        score += 10

    return max(40, min(score, 98))


# =======================
# ANALYZE ROUTE
# =======================
@app.route("/analyze", methods=["POST"])
def analyze():

    try:
        image_bytes = request.data

        if not image_bytes or len(image_bytes) < 100:
            return jsonify({"error": "No image received"}), 400

        # =======================
        # TIMESTAMP
        # =======================
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # =======================
        # SAVE IMAGE (FYP PROOF)
        # =======================
        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = os.path.join(SAVE_DIR, filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        # Decode image for AI
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        prompt = """
You are an agricultural expert.

Analyze the plant leaf image.

Return:
Diagnosis:
Symptoms:
Cause:
Solution:

Be clear and structured.
"""

        # =======================
        # GEMINI CALL
        # =======================
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, prompt],
            config={
                "temperature": 0.2,
                "max_output_tokens": 1024
            }
        )

        result = response.text.strip()

        # =======================
        # CONFIDENCE SCORE
        # =======================
        confidence = estimate_confidence(result)

        print("AI RESULT:", result)

        # =======================
        # BLYNK (OPTIONAL)
        # =======================
        if BLYNK_TOKEN:
            try:
                url = f"https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}&v1={result}"
                requests.get(url, timeout=5)
            except:
                pass

        # =======================
        # RESPONSE
        # =======================
        return jsonify({
            "status": "success",
            "scan_time": scan_time,
            "confidence": f"{confidence}%",
            "result": result,
            "image_saved_as": filename
        })

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# =======================
# RUN
# =======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)