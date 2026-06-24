import io
import os
import json
from flask import Flask, request, jsonify, render_template, send_from_directory
from google import genai
from PIL import Image
from datetime import datetime
from supabase import create_client

app = Flask(__name__)

# ================= ENV =================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ================= SAFE INIT =================
client = None
supabase = None

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("⚠ WARNING: GEMINI_API_KEY missing (AI disabled)")

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("⚠ WARNING: Supabase credentials missing (DB disabled)")

# ================= STORAGE =================
IMAGE_FOLDER = "data/images"
os.makedirs(IMAGE_FOLDER, exist_ok=True)

# ================= HOME =================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK", "project": "Smart Farming AI"})


# ================= DASHBOARD =================
@app.route("/dashboard", methods=["GET"])
def dashboard():

    if supabase:
        try:
            response = (
                supabase.table("scans")
                .select("*")
                .order("time", desc=True)   # FIXED (safer than id)
                .execute()
            )
            logs = response.data or []
        except Exception as e:
            print("Supabase fetch error:", e)
            logs = []
    else:
        logs = [
            {
                "time": "2026-06-24 14:00:00",
                "result": json.dumps({
                    "status": "deficiency",
                    "diagnosis": "Iron deficiency",
                    "cause": "Low soil iron",
                    "solution": "Add iron fertilizer"
                }),
                "image": "test.jpg"
            }
        ]

    return render_template("dashboard.html", logs=logs)


# ================= IMAGE =================
@app.route("/image/<filename>")
def get_image(filename):
    return send_from_directory(IMAGE_FOLDER, filename)


# ================= ANALYZE =================
@app.route("/analyze", methods=["POST"])
def analyze():

    try:
        image_bytes = request.data

        if not image_bytes:
            return jsonify({"status": "error", "message": "No image"}), 400

        device_type = request.headers.get("X-Device-Type", "leaf")

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
        image_path = os.path.join(IMAGE_FOLDER, filename)
        image.save(image_path)

        # ================= PROMPT =================
        if device_type == "chili_cam":
            prompt = """
Analyze this chili fruit image.

Return ONLY valid JSON:
{
  "status": "healthy" or "disease",
  "diagnosis": "short disease name or healthy",
  "cause": "short cause",
  "solution": "short solution"
}
"""
        else:
            prompt = """
Analyze this plant leaf image.

Return ONLY valid JSON:
{
  "status": "healthy" or "deficiency",
  "diagnosis": "short deficiency name or healthy",
  "cause": "short cause",
  "solution": "short solution"
}
"""

        # ================= GEMINI =================
        if client:
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[image, prompt]
                )

                raw = response.text.strip()

                try:
                    result_json = json.loads(raw)
                except json.JSONDecodeError:
                    result_json = {
                        "status": "unknown",
                        "diagnosis": raw,
                        "cause": "",
                        "solution": ""
                    }

            except Exception as e:
                print("Gemini Error:", e)
                result_json = {
                    "status": "error",
                    "diagnosis": "AI failed",
                    "cause": "",
                    "solution": ""
                }
        else:
            result_json = {
                "status": "debug",
                "diagnosis": "No Gemini key (test mode)",
                "cause": "",
                "solution": ""
            }

        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            "time": time_now,
            "result": json.dumps(result_json),
            "status": result_json.get("status", "unknown"),
            "diagnosis": result_json.get("diagnosis", ""),
            "image": filename,
            "device_type": device_type
        }

        if supabase:
            try:
                supabase.table("scans").insert(entry).execute()
            except Exception as e:
                print("Supabase Insert Error:", e)

        print(f"Saved Scan [{device_type}] : {filename}")

        return jsonify({
            "status": "success",
            "device_type": device_type,
            "result": result_json,
            "image": filename,
            "time": time_now
        })

    except Exception as e:
        print("SERVER ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


# ================= RUN (RENDER FIX) =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)