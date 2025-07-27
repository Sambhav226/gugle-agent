from flask import Flask, request, jsonify
import asyncio
import json
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


from services.rag_v0_py.retrieval import search_documents

# --- API endpoint ---
@app.route('/rag_query', methods=['POST'])
def handle_rag_query():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    query = data.get('query')
    if not query:
        return jsonify({"error": "Missing 'query' in request body"}), 400

    # Run async retrieval inside sync view
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    raw_results = loop.run_until_complete(search_documents(query))

    formatted = []

    for doc in raw_results:
        # If doc is a string, wrap it in a dict
        if isinstance(doc, str):
            text = doc
        elif isinstance(doc, dict):
            text = doc.get("text", "")
        else:
            continue  # skip unknown types

        lines = text.strip().split('\n')
        title = "Untitled"
        description = text
        if lines and lines[0].lower().startswith("title:"):
            title = lines[0][6:].strip()
            description = "\n".join(lines[1:]).strip()

        formatted.append({
            "title": title,
            "description": description,
            "link": ""
        })

    return jsonify(formatted), 200

# --- Run the app ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)
