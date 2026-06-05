import io
import os
from datetime import datetime
from flask import Flask, request, jsonify
from google import genai
from PIL import Image
import requests

app = Flask(__name__)

# =======================
# ENV VARIABLES
# =======================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BLYNK_TOKEN = os.getenv("BLYNK_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)

# =======================
# HOME
# =======================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "OK",
        "message": "Smart Farming AI Server Running"
    })

# =======================
# GEMINI ANALYSIS
# =======================
def analyze_leaf(image):

    prompt = """
You are an agricultural expert.

Analyze the uploaded plant leaf image.

Return EXACTLY in this format:

Diagnosis:
[diagnosis]

Symptoms:
[symptoms]

Cause:
[cause]

Solution:
[solution]

Confidence:
[0-100%]

Rules:
- Be concise and professional.
- Complete every section.
- Never cut off mid-sentence.
- If the leaf appears healthy, clearly state that.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[image, prompt],
        config={
            "temperature": 0.2,
            "max_output_tokens": 2048
        }
    )

    return response.text.strip()

# =======================
# ANALYZE ROUTE
# =======================
@app.route("/analyze", methods=["POST"])
def analyze():

    try:

        image_bytes = request.data

        if not image_bytes or len(image_bytes) < 100:
            return jsonify({
                "error": "No image received"
            }), 400

        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        # Current time
        scan_time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        try:

            result = analyze_leaf(image)

        except Exception as ai_error:

            print("AI ERROR:", str(ai_error))

            result = f"""
Diagnosis:
AI Analysis Unavailable

Symptoms:
Unable to analyze image.

Cause:
Gemini quota exceeded or API unavailable.

Solution:
Retry later.

Confidence:
0%
"""

        print("\n====================")
        print("SCAN TIME:", scan_time)
        print(result)
        print("====================\n")

        # =======================
        # SEND TO BLYNK
        # =======================
        if BLYNK_TOKEN:
            try:
                requests.get(
                    f"https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}&v1={result}",
                    timeout=5
                )
            except Exception as blynk_error:
                print("BLYNK ERROR:", blynk_error)

        return jsonify({
            "status": "success",
            "scan_time": scan_time,
            "result": result
        })

    except Exception as e:

        print("SERVER ERROR:", str(e))

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# =======================
# RUN
# =======================
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )