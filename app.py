import io
import os
import re
import json
import base64
import uuid
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, render_template, redirect
from groq import Groq
from PIL import Image
from supabase import create_client

app = Flask(__name__)

# ================= TIMEZONE =================
MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")

# ================= ENV =================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = "scan-images"

# ================= SAFE INIT =================
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

if not client:
    print("WARNING: GROQ_API_KEY missing (AI disabled)")
if not supabase:
    print("WARNING: Supabase credentials missing (DB disabled)")

# ================= LOCAL FALLBACK =================
IMAGE_FOLDER = "data/images"
os.makedirs(IMAGE_FOLDER, exist_ok=True)


# ================= HELPERS =================

def extract_json(text):
    if not text:
        return None

    text = text.strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    return None


def upload_image_to_supabase(image_bytes, filename):
    if not supabase:
        return None
    try:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            path=filename,
            file=image_bytes,
            file_options={"content-type": "image/jpeg", "upsert": "true"}
        )
        return supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
    except Exception as e:
        print("Supabase upload failed:", e)
        traceback.print_exc()
        return None


# ================= PROMPT (FIXED) =================
def get_prompt():
    return """
You are an agricultural vision expert.

STEP 1:
Check if a real plant/leaf/fruit/crop is visible.

If NO plant is detected:
Return ONLY this JSON:
{
  "status": "no_plant",
  "diagnosis": "No plant detected",
  "cause": "Image does not contain a plant or crop",
  "solution": "Capture a clear image of a leaf or plant",
  "confidence": "0%"
}

STEP 2:
If plant IS visible:
Analyze health and return ONLY JSON:
{
  "status": "healthy or disease or deficiency",
  "diagnosis": "short name",
  "cause": "short cause",
  "solution": "short solution",
  "confidence": "90%"
}
"""


# ================= DASHBOARD HELPERS (UNCHANGED) =================

def fetch_all_scans():
    all_logs = []
    page_size = 1000
    start = 0
    while True:
        response = (
            supabase.table("scans")
            .select("*")
            .order("id", desc=True)
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = response.data or []
        all_logs.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return all_logs


def parse_result(result):
    if isinstance(result, dict):
        return result
    parsed = extract_json(result)
    if parsed:
        return parsed
    return {
        "status": "unknown",
        "diagnosis": str(result),
        "cause": "",
        "solution": "",
        "confidence": "--"
    }


def prepare_log(log):
    result_raw = log.get("Result") or log.get("result") or ""
    result_data = parse_result(result_raw)

    device_type = log.get("device_type") or "leaf_cam"

    prepared = dict(log)
    prepared["result_data"] = result_data
    prepared["status"] = result_data.get("status", "unknown")
    prepared["diagnosis"] = result_data.get("diagnosis", "")
    prepared["cause"] = result_data.get("cause", "")
    prepared["solution"] = result_data.get("solution", "")
    prepared["confidence"] = result_data.get("confidence", "--")

    image_url = log.get("image_url")
    if not image_url and log.get("image"):
        image_url = f"/image/{log['image']}"
    prepared["image_url"] = image_url or ""

    return prepared


def latest_for(logs, device_type):
    for log in logs:
        if log.get("device_type") == device_type:
            return log
    return None


def is_problem(log):
    status = (log.get("status") or "").lower()
    return status in ["disease", "deficiency", "warning", "critical", "problem"]


# ================= ROUTES =================

@app.route("/", methods=["GET"])
def home():
    return redirect("/dashboard")


@app.route("/dashboard", methods=["GET"])
def dashboard():
    logs = []
    if supabase:
        try:
            logs = fetch_all_scans()
        except Exception as e:
            print("Supabase fetch error:", e)
            traceback.print_exc()

    logs = [prepare_log(log) for log in logs]

    latest_chili = latest_for(logs, "chili_cam")
    latest_leaf = latest_for(logs, "leaf_cam")

    chili_logs = [l for l in logs if l.get("device_type") == "chili_cam"]
    leaf_logs = [l for l in logs if l.get("device_type") == "leaf_cam"]

    chili_issues = sum(1 for l in chili_logs if is_problem(l))
    leaf_issues = sum(1 for l in leaf_logs if is_problem(l))
    healthy_count = sum(1 for l in logs if (l.get("status") or "").lower() == "healthy")

    return render_template(
        "dashboard.html",
        logs=logs,
        latest_chili=latest_chili,
        latest_leaf=latest_leaf,
        total_scans=len(logs),
        chili_issues=chili_issues,
        leaf_issues=leaf_issues,
        healthy_count=healthy_count,
    )


@app.route("/image/<filename>")
def get_image(filename):
    from flask import send_from_directory
    return send_from_directory(IMAGE_FOLDER, filename)


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        image_bytes = request.data
        if not image_bytes:
            return "error: No image data", 400

        raw_device_type = request.headers.get("X-Device-Type", "leaf_cam")
        device_id = request.headers.get("X-Device-ID", "unknown")

        device_type = "chili_cam" if "chili" in raw_device_type.lower() else "leaf_cam"

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        prefix = "chili" if device_type == "chili_cam" else "leaf"
        filename = f"{prefix}_{datetime.now(MY_TZ).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"

        img_buffer = io.BytesIO()
        image.save(img_buffer, format="JPEG", quality=85)
        img_bytes = img_buffer.getvalue()

        image_url = upload_image_to_supabase(img_bytes, filename)

        if not image_url:
            local_path = os.path.join(IMAGE_FOLDER, filename)
            with open(local_path, "wb") as f:
                f.write(img_bytes)
            image_url = f"/image/{filename}"

        result_json = None

        if client:
            try:
                base64_image = base64.b64encode(img_bytes).decode("utf-8")

                response = client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": get_prompt()},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    temperature=0.2
                )

                raw = response.choices[0].message.content
                result_json = extract_json(raw)

                if not result_json:
                    raise ValueError("Invalid JSON from AI")

            except Exception as e:
                print("Groq error:", e)
                traceback.print_exc()
                result_json = {
                    "status": "error",
                    "diagnosis": "AI failed",
                    "cause": str(e),
                    "solution": "Check API or model",
                    "confidence": "--"
                }

        else:
            result_json = {
                "status": "debug",
                "diagnosis": "No API key",
                "cause": "",
                "solution": "",
                "confidence": "--"
            }

        entry = {
            "Time": datetime.now(MY_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "Result": json.dumps(result_json),
            "Confidence": result_json.get("confidence", "--"),
            "image": filename,
            "image_url": image_url,
            "device_type": device_type,
            "device_id": device_id,
        }

        if supabase:
            supabase.table("scans").insert(entry).execute()

        return json.dumps(result_json), 200

    except Exception as e:
        print("SERVER ERROR:", e)
        traceback.print_exc()
        return f"error: {str(e)}", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
