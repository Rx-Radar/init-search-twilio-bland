import functions_framework
from flask import jsonify, request
from firebase_admin import credentials, firestore, auth, initialize_app
from packages import util
import twilio
from twilio.rest import Client
import json


# Initialize Firebase Admin SDK with the service account key
cred = credentials.Certificate("firebase_creds.json")  # Update with your service account key file 
initialize_app(cred)
db = firestore.client() # set firestore client

# initialize twilio client for SMS
ACCOUNT_SID = 'AC3d433258fe9b280b01ba83afe272f438'
AUTH_TOKEN = '2cc106ae7b360c99a7be11cc4ea77c07'
twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)


# USED FOR TESTING PURPOSES 
NUMBER_OF_CALLS = 1 # global var for number of pharmacies we will call 

"""
{
    "user_session_token": "12345abcde",
    "phone_number": "+12032248444",
    "user_location": "Troy, NY",
    "prescription": {
        "name": "Focalin",
        "dosage": "10mg",
        "brand_or_generic": "Generic",
        "quantity": "30 tablets",
        "type": "Extended Release"
    }
}
"""
@functions_framework.http
def main(request):
    
    # # Set CORS headers for the preflight request
    # if request.method == "OPTIONS":
    #     # Allows GET requests from any origin with the Content-Type
    #     # header and caches preflight response for an 3600s
    #     headers = {
    #         "Access-Control-Allow-Origin": "*", # change from "*" to "https://rx-radar.com" for production
    #         "Access-Control-Allow-Methods": "POST, OPTIONS",
    #         "Access-Control-Allow-Headers": "Content-Type",
    #         "Access-Control-Max-Age": "3600",
    #     }

    #     return ("", 204, headers)

    # # Set CORS headers for the main request
    headers = {"Access-Control-Allow-Origin": "*"} # change from "*" to "https://rx-radar.com" for production

    # begin the actual medication_request
        
    # Get the JSON data from the request
    request_data = request.get_json(silent=True)

    # If the token is valid, proceed with the request processing
    success, out, code = util.validate_request(request_data)
    if not success:
        return out, code, headers


    verification_token = "test"
    # # Verify the user session token
    # user_session_token = request_data["user_session_token"]
    # verification_token = util.verify_user_token(token=user_session_token)
    # if not verification_token:
    #     # If the user session token is incorrect, return a 401 Unauthorized response
    #     return jsonify({'error': 'Unauthorized'}), 401, headers

    # Push new search to db
    res, search_request_uuid, exc = util.db_add_search(request_data, verification_token, db, NUMBER_OF_CALLS)
    if not res:
        return jsonify({"error": "Internal posting error", "exception": str(exc)}), 500, headers
    
    # calls pharmacies
    prescription = request_data["prescription"]
    success, out, exc = util.call_all_pharmacies(db, twilio_client, search_request_uuid, prescription)
    if not success:
        return jsonify({'error': 'Calling pharmacies Failed', 'exception': str(exc)}), 500, headers

    # return success message
    return jsonify({'message': 'Request is valid'}), 200, headers





        