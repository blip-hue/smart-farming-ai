import io
from flask import Flask, request, jsonify
from google import genai
from PIL import Image
import requests

app = Flask(__name__)

# Gemini AI
client = genai.Client(api_key="AIzaSyDiDJDnEJGc2WR68U2VbThSX5KLcwK_Nqc")

# Blynk token (FIXED)
BLYNK_TOKEN = "4Wy25cLl9FLN66Ckkey9gK804tXyu3So"


@app.route('/analyze', methods=['POST'])
def analyze_image():

    try:
        # ESP32 sends RAW JPEG bytes
        image_bytes = request.data

        if not image_bytes:
            return jsonify({"error": "No image received"}), 400

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        prompt = (
            "Analyze this plant leaf. Identify nutrient deficiency "
            "(N, P, K, Mg, Fe) or disease. "
            "Give 1-sentence diagnosis and 1-sentence solution."
        )

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )

        result = response.text[:150]

        print("AI RESULT:", result)

        # Send to Blynk
        blynk_url = f"https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}&v1={result}"
        requests.get(blynk_url)

        return jsonify({
            "status": "success",
            "result": result
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)