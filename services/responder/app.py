import os
import logging
import requests
from flask import Flask, request, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Dial

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Responder")

app = Flask(__name__)

# --- Configuration ---
BRANCH_NAME = os.environ.get('BRANCH_NAME', 'unknown')
ADMIN_URL = os.environ.get('ADMIN_DASHBOARD_URL', 'http://admin:5000')
PUBLIC_URL = os.environ.get('PUBLIC_URL')

def get_config():
    """Fetch settings from Admin DB."""
    try:
        r = requests.get(f"{ADMIN_URL}/api/settings/{BRANCH_NAME}", timeout=2)
        if r.status_code == 200:
            return r.json()
    except Exception:
        logger.error("Could not fetch settings from Admin")
    return {}

# --- Routes ---

@app.route('/health')
def health():
    return jsonify({"status": "online", "branch": BRANCH_NAME})

@app.route('/webhook', methods=['POST'])
def webhook():
    """1. Emergency Triggered."""
    conf = get_config()
    if not conf.get('twilio_sid'):
        return jsonify({"error": "Branch not configured"}), 500

    client = Client(conf['twilio_sid'], conf['twilio_token'])
    data = request.json or {}
    
    # Who to call?
    tech_phone = data.get('chosen_phone') or conf.get('default_tech_phone')
    description = data.get('description', 'Emergency reported')

    # Start Notification Call
    # We pass the description in the URL so TwiML can read it
    try:
        client.calls.create(
            to=tech_phone,
            from_=conf['twilio_number'],
            url=f"{PUBLIC_URL}/twiml/notify?text={description}",
            # When tech hangs up, we call back to connect
            status_callback=f"{PUBLIC_URL}/events/tech_done?tech={tech_phone}",
            status_callback_event=['completed']
        )
        return jsonify({"status": "calling_tech"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/incoming_call', methods=['POST'])
def incoming_call():
    """2. Customer Calls In -> Queue."""
    resp = VoiceResponse()
    resp.say("Please hold while we connect you to the technician.")
    # Queue name is simply the branch name (e.g. 'tuc')
    resp.enqueue(BRANCH_NAME, wait_url="[http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3](http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3)")
    return str(resp)

@app.route('/twiml/notify', methods=['POST'])
def twiml_notify():
    """Generate TwiML for Tech Notification."""
    text = request.args.get('text', '')
    resp = VoiceResponse()
    resp.pause(length=1)
    resp.say(f"Emergency Alert. {text}. Please hang up to accept the customer call.")
    return str(resp)

@app.route('/events/tech_done', methods=['POST'])
def tech_done():
    """3. Tech hung up -> Bridge to Queue."""
    tech = request.args.get('tech')
    conf = get_config()
    client = Client(conf['twilio_sid'], conf['twilio_token'])

    # Dial the Queue where customer is waiting
    twiml = f'<Response><Dial><Queue>{BRANCH_NAME}</Queue></Dial></Response>'
    
    try:
        client.calls.create(
            to=tech,
            from_=conf['twilio_number'],
            twiml=twiml
        )
        logger.info(f"Connecting {tech} to queue {BRANCH_NAME}")
    except Exception as e:
        logger.error(f"Bridge failed: {e}")

    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
