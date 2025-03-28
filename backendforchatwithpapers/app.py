from flask import Flask, request, jsonify
from flask_cors import CORS
from chat_with_paper import ChatWithPaper
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api.log')
    ]
)

app = Flask(__name__)

# Configure CORS to allow all origins with additional headers
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["OPTIONS", "POST", "GET"],
        "allow_headers": ["*"],
        "expose_headers": ["*"]
    }
})

chat_service = ChatWithPaper()

@app.before_request
def log_request_info():
    """Log details of incoming requests"""
    if request.path.startswith('/api/'):
        logging.info(f"Incoming Request: {request.method} {request.path}")
        logging.info(f"Headers: {dict(request.headers)}")
        if request.method == 'POST':
            try:
                logging.info(f"Request Body: {request.get_data(as_text=True)}")
            except:
                logging.warning("Could not log request body")

@app.after_request
def log_response_info(response):
    """Log details of outgoing responses"""
    if request.path.startswith('/api/'):
        logging.info(f"Outgoing Response: {response.status}")
        logging.info(f"Response Data: {response.get_data(as_text=True)}")
        response.headers['X-Request-Time'] = datetime.utcnow().isoformat()
    return response

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def chat():
    """Handle chat requests with paper content"""
    try:
        if request.method == 'OPTIONS':
            return _build_cors_preflight_response()
        
        data = request.get_json()
        logging.info(f"Chat request data: {data}")
        
        if not data or not all(k in data for k in ['pdf_url', 'title', 'question']):
            logging.error("Missing required fields in chat request")
            return jsonify({"error": "Missing required fields (pdf_url, title, question)"}), 400
        
        result = chat_service.chat_with_paper(
            pdf_url=data['pdf_url'],
            title=data['title'],
            question=data['question']
        )
        
        status_code = 400 if "error" in result else 200
        return _corsify_actual_response(jsonify(result)), status_code
        
    except Exception as e:
        logging.error(f"Chat error: {str(e)}", exc_info=True)
        return _corsify_actual_response(jsonify({"error": "Internal server error"})), 500

@app.route('/api/generate-questions', methods=['POST', 'OPTIONS'])
def generate_questions():
    """Generate practice questions from paper content"""
    try:
        if request.method == 'OPTIONS':
            return _build_cors_preflight_response()
            
        data = request.get_json()
        logging.info(f"Question generation request data: {data}")
        
        if not data:
            logging.error("No data received in question generation request")
            return jsonify({"error": "No data received"}), 400
            
        if 'pdf_url' not in data or 'title' not in data:
            logging.error("Missing required fields in question generation request")
            return jsonify({"error": "Missing required fields (pdf_url, title)"}), 400
        
        questions = chat_service.generate_practice_questions(
            pdf_url=data['pdf_url'],
            title=data['title'],
            num_questions=data.get('num_questions', 5),
            difficulty=data.get('difficulty', 'medium'),
            question_type=data.get('question_type', 'mixed'),
            description=data.get('description', '')
        )
        
        logging.info(f"Generated {len(questions.get('questions', []))} questions")
        return _corsify_actual_response(jsonify(questions))
        
    except Exception as e:
        logging.error(f"Question generation error: {str(e)}", exc_info=True)
        return _corsify_actual_response(jsonify({"error": str(e)})), 500
    
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify API status"""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200

def _build_cors_preflight_response():
    """Handle CORS preflight requests"""
    response = jsonify({"message": "Preflight Request"})
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "*")
    response.headers.add("Access-Control-Allow-Methods", "*")
    response.headers.add("Access-Control-Max-Age", "86400")  # 24 hours
    return response

def _corsify_actual_response(response):
    """Add CORS headers to actual responses"""
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Expose-Headers", "*")
    response.headers.add("X-API-Version", "1.0")
    return response

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    logging.warning(f"404 Error: {request.url}")
    return _corsify_actual_response(jsonify({"error": "Endpoint not found"})), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logging.error(f"500 Error: {str(error)}")
    return _corsify_actual_response(jsonify({"error": "Internal server error"})), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)