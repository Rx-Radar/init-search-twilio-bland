
import functions_framework
from cloudevents.http import CloudEvent
from flask import jsonify
from firebase_admin import credentials, firestore, initialize_app
from packages import util
from twilio.rest import Client
import functions_framework
from google.cloud.firestore import firestore as gfirestore
import yaml
import os

def load_yaml_file(filepath):
    with open(filepath, 'r') as file:
        data = yaml.safe_load(file)
    return data

# Use the function to load the configuration
config = load_yaml_file('config.yaml')

env = os.getenv("deployment_env")

TWILIO_ACCOUNT_SID = config[env]["twilio"]["account_sid"] 
TWILIO_AUTH_TOKEN = config[env]["twilio"]["auth_token"] 

# Initialize Firebase Admin SDK with the service account key
cred = credentials.Certificate("firebase_creds.json")  # Update with your service account key file 
initialize_app(cred)
db = firestore.client() # set firestore client

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

"""
{
    "user_session_token": "12345abcde",
    "phone_number": "+12032248444",
    "user_location": "Troy, NY",
    "prescription": {
        "name": "Focalin",
        "dosage": "10",
        "brand_or_generic": "Generic",
        "quantity": "30",
        "type": "Extended%20Release"
    }
}
"""
@functions_framework.http
def main(data, context):
    
    
    print(data)
    print(context)
    
    return jsonify({'message': 'Request is valid'}), 200
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

    # Begin the actual medication_request
        
    # Get the JSON data from the request
    request_data = request.get_json(silent=True)

    # If the token is valid, proceed with the request processing
    success, out, code = util.validate_request(request_data)
    if not success:
        return out, code, headers

    # # verify the user session token
    # user_session_token = request_data["user_session_token"]
    # verification_token = util.verify_user_token(token=user_session_token)
    # if not verification_token:
    #     # If the user session token is incorrect, return a 401 Unauthorized response
    #     return jsonify({'error': 'Unauthorized'}), 401, headers


    
    verification_token = "testttttt"
    
    # checks that the user is valid to place calls 
    phone_number = request_data["phone_number"]
    # user_can_search = util.can_user_search(db, phone_number)
    # if not user_can_search: 
    #     return jsonify({'error': 'user tried >1 prescription searches today'}), 401, headers

    # Push new search to db
    res, search_request_uuid, exc = util.db_add_search(request_data, verification_token, db)
    if not res:
        return jsonify({"error": "Internal posting error", "exception": str(exc)}), 500, headers
    
    ## ----------------- MVP **magic** ------------------------ ##
    # get users location and convert to lon and lat for mvp
    user_location = request_data["user_location"]
    global lat, lon
    lat, lon = 0.00, 0.00
    if user_location == "Troy, NY":
        lat, lon = 42.7298, -73.6789 # RPI (lat, lon)

    if user_location == "Boston, MA":
        lat, lon = 42.3399, -71.0899 # Northeastern (lat, lon)

    if user_location == "test":
        lat, lon = 0.00, 0.00 # Northeastern (lat, lon)
    ## --------------------------------------------------------- ##

    # calls pharmacies
    prescription = request_data["prescription"]
    success, out, exc = util.call_all_pharmacies(db, twilio_client, search_request_uuid, prescription, lat, lon)
    if not success:
        return jsonify({'error': 'Calling pharmacies Failed', 'exception': str(exc)}), 500, headers
    
    
    # update user doc with search information
    util.update_user_with_search(db=db, phone_number=phone_number, search_request_uuid=search_request_uuid)

    util.send_sms(twilio_client, "+12032248444", f"A new user has searched for a medication: {search_request_uuid}")
    util.send_sms(twilio_client, "+12037674296", f"A new user has searched for a medication: {search_request_uuid}")
    
    # return success message
    return jsonify({'message': 'Request is valid'}), 200, headers





        