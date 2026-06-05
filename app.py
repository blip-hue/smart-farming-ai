import io
import os
import json
from flask import Flask, request, jsonify, render_template
from google import genai
from PIL import Image
import requests
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# =======================
# ENV VARIABLES (RENDER)
# =======================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BLYNK_TOKEN = os.getenv("BLYNK_TOKEN")

if not GEMINI_API_KEY:
    raise Exception("Missing GEMINI_API_KEY in Render environment variables")

client = genai.Client(api_key=GEMINI_API_KEY)

# =======================
# DATA STORAGE FILE
# =======================
DATA_FILE = "data/logs.json"


# =======================
# HOME ROUTE (API CHECK)
# =======================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK", "message": "Smart Farming AI Running"})


# =======================
# DASHBOARD ROUTE (NEW)
# =======================
@app.route("/dashboard", methods=["GET"])
def dashboard():
    try:
        with open(DATA_FILE, "r") as f:
            logs = json.load(f)
    except:
        logs = []

    return render_template("dashboard.html", logs=logs)


# =======================
# MAIN AI ANALYSIS
# =======================
@app.route("/analyze", methods=["POST"])
def analyze():

    try:
        image_bytes = request.data

        if not image_bytes or len(image_bytes) < 100:
            return jsonify({"error": "No image received"}), 400

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        prompt = """
You are an agricultural expert.

Analyze the plant leaf image.

Return:
Diagnosis:
Cause:
Symptoms:
Solution:

Keep response clear and structured.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, prompt],
            config={
                "temperature": 0.2,
                "max_output_tokens": 2048
            }
        )

        result = response.text.strip()

        # =======================
        # MALAYSIA TIMESTAMP FIX
        # =======================
        malaysia_time = timezone(timedelta(hours=8))
        scan_time = datetime.now(malaysia_time).strftime("%Y-%m-%d %H:%M:%S")

        # =======================
        # SIMPLE CONFIDENCE SCORE
        # =======================
        confidence = "90%" if len(result) > 100 else "75%"

        # =======================
        # SAVE TO JSON DATABASE
        # =======================
        entry = {
            "time": scan_time,
            "result": result,
            "confidence": confidence
        }

        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        except:
            data = []

        data.append(entry)

        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)

        # =======================
        # OPTIONAL: BLYNK UPDATE
        # =======================
        if BLYNK_TOKEN:
            try:
                url = f"https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}&v1={result}"
                requests.get(url, timeout=5)
            except Exception as e:
                print("Blynk error:", e)

        return jsonify({
            "status": "success",
            "result": result,
            "scan_time": scan_time,
            "confidence": confidence
        })

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# =======================
# RUN SERVER
# =======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)