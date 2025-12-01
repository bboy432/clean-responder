import os
import logging
from flask import Flask, request, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Dial

# Configure logging for Docker/Portainer visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration ---
# Load config directly from environment (Best for Portainer)
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
PUBLIC_URL = os.environ.get('PUBLIC_URL')
# Operational Mode: 'NORMAL' or 'TESTING'
OPERATING_MODE = os.environ.get('OPERATING_MODE', 'NORMAL')

# Validate Config
if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_NUMBER, PUBLIC_URL]):
    logger.critical("Missing required environment variables. Check your .env file.")

client = Client(TWILIO_SID, TWILIO_TOKEN)

# --- State Management ---
# Simple in-memory state. For high-scale, use Redis.
active_emergency = {
    "id": None,
    "tech_number": None,
    "customer_waiting": False
}

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "mode": OPERATING_MODE}), 200

# --- 1. Webhook Trigger ---
@app.route('/webhook', methods=['POST'])
def trigger_emergency():
    data = request.json or {}
    logger.info(f"Trigger received: {data}")

    if OPERATING_MODE == 'TESTING':
        return jsonify({"status": "TEST_MODE", "message": "Trigger logged."}), 200

    active_emergency['id'] = "emergency-active"
    active_emergency['tech_number'] = data.get('technician_phone')
    active_emergency['customer_waiting'] = False
    
    details = data.get('description', 'An emergency has been reported.')
    address = data.get('incident_address', 'Unknown location')

    # Message to speak to the technician
    tts_message = f"New Emergency Alert. Address: {address}. Issue: {details}. Please listen to these details, then hang up. You will be called back immediately to connect with the customer."

    try:
        # Call #1: The Notification
        call = client.calls.create(
            to=active_emergency['tech_number'],
            from_=TWILIO_NUMBER,
            twiml=f'<Response><Pause length="1"/><Say>{tts_message}</Say><Pause length="1"/><Say>Repeating. {tts_message}</Say></Response>',
            # Callback when Tech hangs up
            status_callback=f"{PUBLIC_URL}/events/tech_notification_ended",
            status_callback_event=['completed']
        )
        logger.info(f"Notification call started: {call.sid}")
        return jsonify({"status": "Technician notified", "call_sid": call.sid}), 200
    except Exception as e:
        logger.error(f"Failed to call technician: {e}")
        return jsonify({"error": str(e)}), 500

# --- 2. Customer Inbound Call ---
@app.route('/incoming_call', methods=['POST'])
def incoming_call():
    logger.info("Customer calling in...")
    resp = VoiceResponse()

    if OPERATING_MODE == 'TESTING':
        resp.say("This is a test of the emergency system. Goodbye.")
        return str(resp)

    # If there is an active emergency, queue them
    if active_emergency['id']:
        active_emergency['customer_waiting'] = True
        logger.info("Customer placed in Queue.")
        
        resp.say("Please hold while we connect you to the technician.")
        resp.play("http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3")
        # Put customer in the specific queue
        resp.enqueue(active_emergency['id'])
    else:
        resp.say("No active emergency is currently reported. Goodbye.")
        resp.hangup()

    return str(resp)

# --- 3. The Warm Transfer Connection ---
@app.route('/events/tech_notification_ended', methods=['POST'])
def tech_notification_ended():
    logger.info("Technician notification call ended.")
    
    if OPERATING_MODE == 'TESTING':
        return '', 200

    # Only call back if a customer is actually waiting
    if active_emergency['id'] and active_emergency['customer_waiting']:
        logger.info("Customer is waiting. Initiating bridge call to Technician.")
        
        # TwiML to Dial the Queue (Connects Tech -> Customer)
        connect_twiml = f'''
        <Response>
            <Say>Connecting you to the customer now.</Say>
            <Dial>
                <Queue>{active_emergency['id']}</Queue>
            </Dial>
        </Response>
        '''
        
        try:
            # Call #2: The Connection
            client.calls.create(
                to=active_emergency['tech_number'],
                from_=TWILIO_NUMBER,
                twiml=connect_twiml
            )
        except Exception as e:
            logger.error(f"Failed to bridge call: {e}")
    else:
        logger.info("No customer waiting. Emergency workflow ended.")
        # Reset state
        active_emergency['id'] = None
        
    return '', 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
